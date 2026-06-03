"""LLM AI 控制器 — 分层控制：LLM 负责战略决策，算法负责战术执行"""
import json
import math
import re
import threading
import urllib.request
import urllib.error
from config import LANES, BLUE_BASE, RED_BASE
from systems.llm_config import (
    LLM_PROVIDERS, SYSTEM_PROMPT, SNAPSHOT_TEMPLATE, DEFAULT_LLM_SETTINGS,
    HERO_STRATEGY_HINTS
)


class LLMAIController:
    """LLM AI 控制器 — 为每个 LLM 控制的英雄定期获取战略指令"""

    def __init__(self, settings=None):
        self.settings = dict(DEFAULT_LLM_SETTINGS)
        if settings:
            self.settings.update(settings)
        self._timers = {}       # {hero_id: timer_until_next_decision}
        self._pending = {}      # {hero_id: bool} 是否有正在进行的请求
        self._directives = {}   # {hero_id: directive_dict}
        self._callbacks = {}    # {hero_id: callback_fn} 请求完成后的回调
        self._lane_switch_cooldown = {}  # {hero_id: cooldown_timer} 换线冷却
        self._history = {}      # {hero_id: [(role, content), ...]} 最近2轮对话历史
        self._events = {}       # {hero_id: [str, ...]} 最近8条事件
        self._event_timer = 0.0 # 事件扫描计时器
        self._prev_kills = {}   # {hero_id: kills} 上一帧击杀数
        self._prev_deaths = {}  # {hero_id: deaths} 上一帧死亡数
        self._prev_tower_count = {}  # {team: count} 上一帧存活塔数
        self._prev_crystal_count = {}  # {team: count} 上一帧存活水晶数
        self._hero_map = {}      # {hid: hero} 英雄引用映射
        self._retry_delay = {}   # {hid: float} 指数退避延迟（秒）
        self._directive_time = {}  # {hid: game_time} 指令创建时间

    @property
    def enabled(self):
        return self.settings.get('enabled', False)

    def should_control_hero(self, hero):
        """判断是否应该用 LLM 控制这个英雄"""
        if not self.enabled:
            return False
        if hero.is_player:
            return False
        team = hero.team
        control_team = self.settings.get('control_team', 'red')
        if control_team != 'both' and control_team != team:
            return False
        positions = self.settings.get('control_positions', ['all'])
        if 'all' in positions:
            return True
        # 根据兵线判断位置
        lane_name = {0: 'top', 1: 'mid', 2: 'bottom'}.get(hero.lane_idx, 'mid')
        return lane_name in positions

    def get_directive(self, hero):
        """获取英雄当前的 LLM 指令，如果没有则返回 None"""
        hid = id(hero)
        return self._directives.get(hid, None)

    def get_ability_directive(self, hero, slot):
        """获取英雄某个技能槽的 LLM 使用策略，返回 (use_mode, condition) 或 None"""
        d = self.get_directive(hero)
        if not d:
            return None
        abilities = d.get('abilities', {})
        slot_cfg = abilities.get(slot)
        if not slot_cfg:
            return None
        return (slot_cfg.get('use', 'aggressive'), slot_cfg.get('condition', 'always'))

    def update(self, dt, game):
        """每帧调用 — 检查是否需要为英雄请求新指令"""
        if not self.enabled:
            return

        # 每2秒扫描一次事件
        self._event_timer -= dt
        if self._event_timer <= 0:
            self._event_timer = 2.0
            self._collect_events(game)

        interval = self.settings.get('interval', 8.0)

        # 清理死亡英雄的指令
        all_heroes = [e for e in game.entities if hasattr(e, 'hero_type') and self.should_control_hero(e)]
        for hero in all_heroes:
            hid = id(hero)
            if not hero.alive:
                # 死亡时清除指令和相关状态
                self._directives.pop(hid, None)
                self._directive_time.pop(hid, None)
                self._pending.pop(hid, None)
                self._retry_delay.pop(hid, None)
                # 复活后2秒内请求新指令（通过重置计时器）
                if hero.respawn_timer > 0 and hero.respawn_timer <= 2.0:
                    self._timers[hid] = 0.0
                continue

        # 指令过期检查：超过2个决策间隔的指令视为过期
        for hid, t in list(self._directive_time.items()):
            if game.game_time - t > interval * 2:
                self._directives.pop(hid, None)
                self._directive_time.pop(hid, None)

        heroes = [e for e in all_heroes if e.alive]

        # 并发限制：最多同时3个请求
        pending_count = sum(1 for v in self._pending.values() if v)

        for hero in heroes:
            hid = id(hero)
            # 初始化计时器（错开各英雄请求时间）
            if hid not in self._timers:
                idx = heroes.index(hero)
                self._timers[hid] = idx * 2.5
            self._timers[hid] -= dt

            # 换线冷却
            if hid in self._lane_switch_cooldown:
                self._lane_switch_cooldown[hid] -= dt
                if self._lane_switch_cooldown[hid] <= 0:
                    del self._lane_switch_cooldown[hid]

            # 到达决策间隔 & 没有正在进行的请求 & 并发未超限
            if self._timers[hid] <= 0 and not self._pending.get(hid, False) and pending_count < 3:
                # 指数退避：失败时延迟增加
                delay = self._retry_delay.get(hid, 0)
                if delay > 0:
                    self._retry_delay[hid] = delay - dt
                    continue
                self._timers[hid] = interval
                self._request_directive(hero, game)
                pending_count += 1

    # ====== 战场快照构建 ======

    def _build_snapshot(self, hero, game):
        """构建单个英雄视角的战场快照文本"""
        # 英雄自身信息
        ab_cd = {k: f"{v['cur_cd']:.1f}s" for k, v in hero.abilities.items()}
        hero_info = (
            f"职业:{hero.type_name}({hero.type_icon}) Lv{hero.level} "
            f"HP:{hero.hp:.0f}/{hero.max_hp} ATK:{hero.total_attack_dmg:.0f} "
            f"坐标:({hero.x:.0f},{hero.y:.0f}) 金币:{hero.gold} "
            f"技能CD:{ab_cd} 装备:{[i['name'] for i in hero.items]}"
        )

        # 己方信息
        allies = []
        for e in game.entities:
            if not e.alive:
                continue
            if hasattr(e, 'hero_type') and e.team == hero.team and e is not hero:
                allies.append(
                    f"  {e.type_name}({e.type_icon}) Lv{e.level} "
                    f"HP:{e.hp:.0f}/{e.max_hp} ({e.x:.0f},{e.y:.0f})"
                )
        allies_str = '\n'.join(allies) if allies else '  无其他队友'

        # 敌方信息
        enemies = []
        for e in game.entities:
            if not e.alive:
                continue
            if hasattr(e, 'hero_type') and e.team != hero.team:
                marker = ' [玩家]' if e.is_player else ''
                enemies.append(
                    f"  {e.type_name}({e.type_icon}) Lv{e.level} "
                    f"HP:{e.hp:.0f}/{e.max_hp} ({e.x:.0f},{e.y:.0f}){marker}"
                )
            elif hasattr(e, 'tier'):  # 防御塔
                if e.team != hero.team:
                    enemies.append(
                        f"  [{e.tier}塔] HP:{e.hp:.0f}/{e.max_hp} ({e.x:.0f},{e.y:.0f})"
                    )
            elif hasattr(e, 'lane_y') and not hasattr(e, 'hero_type'):  # 小兵
                if e.team != hero.team:
                    enemies.append(
                        f"  [小兵] HP:{e.hp:.0f} ({e.x:.0f},{e.y:.0f})"
                    )
        enemies_str = '\n'.join(enemies[:15]) if enemies else '  无敌方单位'
        if len(enemies) > 15:
            enemies_str += f'\n  ...还有{len(enemies)-15}个敌方单位'

        # 兵线态势
        lanes = []
        for li, lane in enumerate(LANES):
            blue_count = sum(1 for e in game.entities
                             if hasattr(e, 'lane_y') and not hasattr(e, 'hero_type')
                             and e.alive and e.team == 'blue'
                             and abs(e.lane_y - lane['y']) < 60)
            red_count = sum(1 for e in game.entities
                            if hasattr(e, 'lane_y') and not hasattr(e, 'hero_type')
                            and e.alive and e.team == 'red'
                            and abs(e.lane_y - lane['y']) < 60)
            lanes.append(f"  {lane['name']}(y={lane['y']}): 蓝方{blue_count}兵 vs 红方{red_count}兵")
        lanes_str = '\n'.join(lanes)

        # 防御塔
        towers = []
        for e in game.entities:
            if hasattr(e, 'tier') and e.alive:
                towers.append(
                    f"  [{e.team}{e.tier}塔] HP:{e.hp:.0f}/{e.max_hp} 射程:{e.attack_range} ({e.x:.0f},{e.y:.0f})"
                )
        towers_str = '\n'.join(towers) if towers else '  无防御塔'

        # 水晶（含护盾/攻击信息）
        crystals = []
        for attr in ('blue_crystals', 'red_crystals'):
            for c in getattr(game, attr, []):
                shield = '护盾' if c.shielded else '无盾'
                status = '存活' if c.alive else '已摧毁'
                crystals.append(
                    f"  [{c.team}水晶] {status} {shield} 攻击范围:{c.attack_range} 回血光环:{c.heal_range} ({c.x:.0f},{c.y:.0f})"
                )
        crystals_str = '\n'.join(crystals) if crystals else '  无水晶'

        # 野怪
        monsters = []
        for e in game.entities:
            if hasattr(e, 'monster_type') and e.alive:
                monsters.append(
                    f"  [{e.monster_type}] HP:{e.hp:.0f}/{e.max_hp} ({e.x:.0f},{e.y:.0f})"
                )
        monsters_str = '\n'.join(monsters[:6]) if monsters else '  无存活野怪'

        # 队伍击杀
        blue_kills = sum(h.kills for h in game.entities
                         if hasattr(h, 'hero_type') and h.team == 'blue')
        red_kills = sum(h.kills for h in game.entities
                        if hasattr(h, 'hero_type') and h.team == 'red')

        # 游戏阶段
        t = game.game_time
        if t < 120:
            game_phase = '前期(对线期)'
        elif t < 360:
            game_phase = '中期(游走期)'
        elif t < 600:
            game_phase = '后期(团战期)'
        else:
            game_phase = '大后期(决胜期)'

        # 当前指令
        cur_d = self._directives.get(id(hero), {})
        cur_str = cur_d.get('action', 'none') if cur_d else 'none'

        # 事件日志
        hid = id(hero)
        events_list = self._events.get(hid, [])
        if events_list:
            events_str = '## 近期事件\n' + '\n'.join(f'- {e}' for e in events_list[-8:]) + '\n\n'
        else:
            events_str = ''

        # KD 统计（所有英雄）
        kd_lines = []
        for e in game.entities:
            if hasattr(e, 'hero_type') and e.alive:
                kd_lines.append(f"  {e.type_name}({e.team}) K:{e.kills} D:{e.deaths}")
        kd_str = '\n'.join(kd_lines) if kd_lines else ''

        # 死亡英雄复活倒计时
        dead_lines = []
        for e in game.entities:
            if hasattr(e, 'hero_type') and not e.alive and e.respawn_timer > 0:
                dead_lines.append(f"  {e.type_name}({e.team}) 复活倒计时:{e.respawn_timer:.0f}秒")
        dead_str = '\n'.join(dead_lines) if dead_lines else ''

        # 将 KD 和死亡信息附加到全局信息
        extra_info = ''
        if kd_str:
            extra_info += f'\n## 击杀/死亡统计\n{kd_str}'
        if dead_str:
            extra_info += f'\n## 死亡英雄\n{dead_str}'

        return SNAPSHOT_TEMPLATE.format(
            hero_info=hero_info,
            allies=allies_str,
            enemies=enemies_str,
            lanes=lanes_str,
            towers=towers_str,
            crystals=crystals_str,
            monsters=monsters_str,
            game_time=game.game_time,
            blue_kills=blue_kills,
            red_kills=red_kills,
            game_phase=game_phase,
            current_directive=cur_str,
            events=events_str,
        ) + extra_info

    def _collect_events(self, game):
        """每2秒扫描一次战场，记录重要事件"""
        # 英雄击杀/死亡变化
        for e in game.entities:
            if not hasattr(e, 'hero_type'):
                continue
            hid = id(e)
            cur_kills = e.kills
            cur_deaths = e.deaths
            prev_kills = self._prev_kills.get(hid, 0)
            prev_deaths = self._prev_deaths.get(hid, 0)

            if cur_kills > prev_kills:
                event = f"{e.type_name}({e.team}) 击杀敌人"
                self._add_event_to_team(e.team, event)
            if cur_deaths > prev_deaths:
                event = f"{e.type_name}({e.team}) 阵亡"
                self._add_event_to_team(e.team, event)
                # 也通知敌方
                enemy_team = 'red' if e.team == 'blue' else 'blue'
                self._add_event_to_team(enemy_team, f"敌方{e.type_name}阵亡")

            self._prev_kills[hid] = cur_kills
            self._prev_deaths[hid] = cur_deaths

        # 防御塔被摧毁
        for team in ('blue', 'red'):
            alive_towers = sum(1 for e in game.entities
                               if hasattr(e, 'tier') and e.alive and e.team == team)
            prev_count = self._prev_tower_count.get(team, 999)
            if alive_towers < prev_count:
                event = f"{team}方防御塔被摧毁"
                self._add_event_to_team('blue', event)
                self._add_event_to_team('red', event)
            self._prev_tower_count[team] = alive_towers

        # 水晶被摧毁
        for team in ('blue', 'red'):
            attr = f'{team}_crystals'
            alive_crystals = sum(1 for c in getattr(game, attr, []) if c.alive)
            prev_count = self._prev_crystal_count.get(team, 999)
            if alive_crystals < prev_count:
                event = f"{team}方水晶被摧毁!"
                self._add_event_to_team('blue', event)
                self._add_event_to_team('red', event)
            self._prev_crystal_count[team] = alive_crystals

    def _add_event_to_team(self, team, event):
        """将事件添加到该队所有 LLM 控制英雄的事件列表"""
        # 需要通过 game 找到对应英雄的 hid
        # _hero_map: {hid: hero} 由 _request_directive 维护
        for hid, hero in self._hero_map.items():
            if hero.team == team:
                self._events.setdefault(hid, []).append(event)
                if len(self._events[hid]) > 8:
                    self._events[hid] = self._events[hid][-8:]

    # ====== URL 规范化 ======

    @staticmethod
    def _normalize_url(url):
        """自动修正不完整的 API URL — 补齐 /chat/completions 后缀"""
        if not url:
            return url
        # 已经是完整的 chat completions 端点
        if url.rstrip('/').endswith('/chat/completions'):
            return url
        # 去掉末尾斜杠
        url = url.rstrip('/')
        # 如果 URL 看起来像 base URL（以 /v1, /v4 等结尾，或以域名结尾），补齐路径
        if re.search(r'/(v\d+|api)$', url) or not re.search(r'/v\d+/', url):
            # 不以 /chat/completions 结尾 → 补齐
            if '/v1/' in url or '/v4/' in url or re.search(r'/v\d+$', url):
                # 已有版本号路径 → 直接追加
                return url + '/chat/completions'
            return url + '/chat/completions'
        return url

    # ====== LLM API 请求 ======

    def _request_directive(self, hero, game):
        """异步请求 LLM 获取战略指令"""
        hid = id(hero)
        self._pending[hid] = True
        self._hero_map[hid] = hero

        snapshot = self._build_snapshot(hero, game)
        provider_id = self.settings.get('provider', 'deepseek')
        provider = LLM_PROVIDERS.get(provider_id, LLM_PROVIDERS['deepseek'])
        api_key = self.settings.get('api_key', '')
        model = self.settings.get('model', '') or provider['default_model']
        max_tokens = self.settings.get('max_tokens', 300)
        timeout = self.settings.get('timeout', 10.0)

        # 构建 system prompt + 角色策略提示
        system_content = SYSTEM_PROMPT
        hint = HERO_STRATEGY_HINTS.get(hero.hero_type, '')
        if hint:
            system_content += '\n\n## 你的角色策略\n' + hint

        # 构建消息：system → 历史 → 当前快照
        messages = [{'role': 'system', 'content': system_content}]
        history = self._history.get(hid, [])
        for role, content in history:
            messages.append({'role': role, 'content': content})
        messages.append({'role': 'user', 'content': snapshot})

        body = provider['body'](model, messages, max_tokens)
        headers = provider['headers'](api_key)
        url = provider.get('api_url', '')
        url = self._normalize_url(url)
        if self.settings.get('api_url_override'):
            url = self.settings['api_url_override']
            url = self._normalize_url(url)

        # 在线程中执行 HTTP 请求
        t = threading.Thread(
            target=self._do_request,
            args=(hid, url, headers, body, timeout, hero, game, snapshot),
            daemon=True
        )
        t.start()

    def _do_request(self, hid, url, headers, body, timeout, hero, game, snapshot):
        """在线程中执行 HTTP 请求并解析结果（含自动重试）"""
        game_time = game.game_time  # 捕获当前时间，避免线程中访问 game
        max_retries = 2
        last_err = None

        try:
            for attempt in range(max_retries + 1):
                try:
                    import ssl
                    data = json.dumps(body).encode('utf-8')
                    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
                    ctx = ssl.create_default_context()
                    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                        result = json.loads(resp.read().decode('utf-8'))
                    content = result['choices'][0]['message']['content']
                    directive = self._parse_response(content, hero)
                    self._directives[hid] = directive
                    self._directive_time[hid] = game_time
                    self._retry_delay[hid] = 0
                    # 更新对话历史（保留最近2轮）
                    history = self._history.get(hid, [])
                    try:
                        summary = f"[快照] {hero.type_name} HP:{hero.hp:.0f}/{hero.max_hp:.0f} 位置:({hero.x:.0f},{hero.y:.0f})"
                    except Exception:
                        summary = "[快照]"
                    history.append(('user', summary))
                    history.append(('assistant', content[:200]))
                    self._history[hid] = history[-4:]
                    return  # 成功
                except urllib.error.HTTPError as e:
                    try:
                        body_text = e.read().decode('utf-8', errors='replace') if e.fp else ''
                        print(f'[LLM AI] HTTP {e.code} for {hero.name}: {body_text[:200]}')
                    except Exception:
                        print(f'[LLM AI] HTTP {e.code} for hero')
                    last_err = e
                    break  # HTTP 错误不重试
                except (urllib.error.URLError, OSError, ConnectionError) as e:
                    last_err = e
                    err_str = str(e).lower()
                    is_transient = any(kw in err_str for kw in
                        ('ssl', 'handshake', 'timed out', 'timeout', 'reset', 'connection', 'refused', 'eof'))
                    if is_transient and attempt < max_retries:
                        import time as _time
                        _time.sleep(1.0 * (attempt + 1))
                        continue
                    break
                except Exception as e:
                    last_err = e
                    break

            # 所有重试失败
            print(f'[LLM AI] 请求失败 for {hero.name}: {last_err}')
            try:
                self._directives[hid] = self._fallback_directive(hero, game)
            except Exception:
                self._directives[hid] = None
            cur = self._retry_delay.get(hid, 4)
            self._retry_delay[hid] = min(60, max(4, cur * 2))
        finally:
            self._pending[hid] = False

    # ====== 连接测试（静态方法，可在设置界面调用） ======

    @staticmethod
    def test_connection(provider_id, api_key, api_url_override='', model='', timeout=8.0):
        """测试 LLM API 连接是否正常。
        返回 (success: bool, message: str, model_used: str)
        """
        provider = LLM_PROVIDERS.get(provider_id, LLM_PROVIDERS['deepseek'])
        test_model = model or provider['default_model']

        # 构建测试消息
        test_messages = [
            {'role': 'user', 'content': '回复 OK（仅这两个字母）。'},
        ]
        test_body = provider['body'](test_model, test_messages, 10)
        test_body['max_tokens'] = 10
        test_headers = provider['headers'](api_key)

        # 确定 URL
        url = api_url_override if api_url_override else provider.get('api_url', '')
        url = LLMAIController._normalize_url(url)

        try:
            data = json.dumps(test_body).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=test_headers, method='POST')
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            model_used = result.get('model', test_model)
            if 'OK' in content.upper() or content.strip():
                return (True, f'连接成功! 模型: {model_used}', model_used)
            return (True, f'连接成功但响应异常: {content[:80]}', model_used)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode('utf-8', errors='replace') if e.fp else ''
            code = e.code
            if code == 401:
                return (False, f'认证失败 (HTTP 401) — API Key 无效或已过期', '')
            elif code == 404:
                return (False, f'端点不存在 (HTTP 404) — 请检查 API URL:\n{url}', '')
            elif code == 429:
                return (False, f'请求过于频繁 (HTTP 429) — 请稍后重试', '')
            else:
                return (False, f'HTTP {code}: {body_text[:150]}', '')
        except urllib.error.URLError as e:
            return (False, f'网络错误: 无法连接到服务器\n{str(e.reason)}', '')
        except Exception as e:
            return (False, f'连接失败: {str(e)[:200]}', '')

    def _parse_response(self, content, hero):
        """解析 LLM 返回的 JSON 指令"""
        try:
            # 尝试提取 JSON（可能包裹在 markdown 代码块中）
            content = content.strip()
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            directive = json.loads(content)
            # 验证必要字段
            valid_actions = {'push', 'retreat', 'gank', 'defend', 'jungle', 'group', 'idle'}
            if directive.get('action') not in valid_actions:
                directive['action'] = 'push'
            # 验证 abilities 结构
            if 'abilities' in directive:
                ab = directive['abilities']
                for slot in ('q', 'w', 'e'):
                    if slot in ab and isinstance(ab[slot], dict):
                        if ab[slot].get('use') not in ('aggressive', 'defensive', 'conditional', 'never', 'save'):
                            ab[slot]['use'] = 'aggressive'
            return directive
        except (json.JSONDecodeError, IndexError):
            return self._fallback_directive(hero, None)

    def _fallback_directive(self, hero, game):
        """LLM 请求失败时的后备指令 — 根据当前状态智能选择行动"""
        hp_pct = hero.hp / hero.max_hp if hero.max_hp > 0 else 1.0

        if hp_pct < 0.3:
            action = 'retreat'
            reason = 'HP太低，撤退回水晶回血'
            priority = 'survival'
            retreat_hp = 0.4
        elif game:
            # 检查附近是否有敌方英雄
            nearby_enemies = [e for e in game.get_all_enemies(hero.team)
                              if e.alive and hasattr(e, 'hero_type')
                              and abs(e.x - hero.x) + abs(e.y - hero.y) < 250]
            # 检查是否在敌方塔范围内（越塔危险）
            in_enemy_tower = any(hasattr(e, 'tier') and e.alive and e.team != hero.team
                                 and dist((e.x, e.y), (hero.x, hero.y)) < e.attack_range
                                 for e in game.entities)
            if in_enemy_tower and hp_pct < 0.6:
                action = 'retreat'
                reason = '在敌方塔范围内且HP不足，撤退'
                priority = 'survival'
                retreat_hp = 0.4
            elif nearby_enemies and hp_pct < 0.5:
                action = 'defend'
                reason = '有敌人且HP不足，防守'
                priority = 'survival'
                retreat_hp = 0.3
            else:
                action = 'push'
                reason = 'LLM不可用，默认推进'
                priority = 'damage'
                retreat_hp = 0.2
        else:
            action = 'push'
            reason = 'LLM不可用，默认推进'
            priority = 'damage'
            retreat_hp = 0.2

        return {
            'action': action,
            'target': 'none',
            'target_pos': None,
            'priority': priority,
            'lane': None,
            'abilities': {
                'q': {'use': 'aggressive'},
                'w': {'use': 'defensive' if hp_pct < 0.5 else 'aggressive'},
                'e': {'use': 'conditional', 'condition': 'group_3plus'},
            },
            'retreat_hp_pct': retreat_hp,
            'reason': reason,
        }

    # ====== 指令应用 ======

    def apply_directive_to_hero(self, hero, game):
        """将 LLM 指令转化为英雄的 target/waypoints/行为参数"""
        d = self.get_directive(hero)
        if not d:
            return

        action = d.get('action', 'push')
        retreat_hp = d.get('retreat_hp_pct', 0.2)
        priority = d.get('priority', 'damage')
        hp_pct = hero.hp / hero.max_hp if hero.max_hp > 0 else 1.0

        # priority 影响：survival 提高撤退积极性，damage 降低撤退阈值
        if priority == 'survival':
            retreat_hp = min(0.5, retreat_hp + 0.1)
        elif priority == 'damage':
            retreat_hp = max(0.1, retreat_hp - 0.05)

        # 换线处理
        self._apply_lane(hero, game, d)

        # 强制撤退（HP 太低）
        if hp_pct < retreat_hp:
            self._apply_retreat(hero, game)
            return

        # 按行动类型执行
        if action == 'push':
            self._apply_push(hero, game, d)
        elif action == 'retreat':
            self._apply_retreat(hero, game)
        elif action == 'gank':
            self._apply_gank(hero, game, d)
        elif action == 'defend':
            self._apply_defend(hero, game, d)
        elif action == 'jungle':
            self._apply_jungle(hero, game)
        elif action == 'group':
            self._apply_group(hero, game)
        # idle: 不做任何事

    def _apply_lane(self, hero, game, d):
        """处理换线指令"""
        lane = d.get('lane')
        if not lane:
            return
        hid = id(hero)
        # 换线冷却（2个决策间隔）
        if hid in self._lane_switch_cooldown:
            return
        lane_map = {'top': 0, 'mid': 1, 'bottom': 2}
        new_idx = lane_map.get(lane)
        if new_idx is not None and new_idx != hero.lane_idx:
            hero.lane_idx = new_idx
            hero.lane_y = LANES[new_idx]['y']
            interval = self.settings.get('interval', 8.0)
            self._lane_switch_cooldown[hid] = interval * 2

    def _apply_push(self, hero, game, d):
        """推进: 根据 target 选择目标推进"""
        target_type = d.get('target', 'none')
        target_pos = d.get('target_pos')

        if target_pos:
            hero.waypoints = [(target_pos[0], target_pos[1])]
            self._auto_target_by_priority(hero, game, target_type)
            return

        if target_type == 'tower':
            # 推进到最近残血敌方塔
            towers = [e for e in game.entities
                      if hasattr(e, 'tier') and e.alive and e.team != hero.team]
            if towers:
                target = min(towers, key=lambda t: t.hp / t.max_hp)
                hero.waypoints = [(target.x, hero.lane_y)]
                hero.target = target
                return
        elif target_type == 'crystal':
            # 推进到敌方水晶
            attr = 'red_crystals' if hero.team == 'blue' else 'blue_crystals'
            crystals = [c for c in getattr(game, attr, []) if c.alive]
            if crystals:
                target = min(crystals, key=lambda c: abs(c.x - hero.x) + abs(c.y - hero.y))
                hero.waypoints = [(target.x, target.y)]
                hero.target = target
                return
        elif target_type == 'hero':
            # 推进中优先攻击敌方英雄
            enemies = [e for e in game.get_all_enemies(hero.team)
                       if hasattr(e, 'hero_type') and e.alive]
            if enemies:
                target = min(enemies, key=lambda e: abs(e.x - hero.x) + abs(e.y - hero.y))
                hero.waypoints = [(target.x, target.y)]
                hero.target = target
                return
        elif target_type == 'minion':
            # 清兵模式
            minions = [e for e in game.get_all_enemies(hero.team)
                       if hasattr(e, 'lane_y') and not hasattr(e, 'hero_type') and e.alive
                       and abs(e.lane_y - hero.lane_y) < 60]
            if minions:
                target = min(minions, key=lambda m: abs(m.x - hero.x))
                hero.waypoints = [(target.x, target.y)]
                hero.target = target
                return

        # 默认：沿兵线推进
        dx = RED_BASE[0] if hero.team == 'blue' else BLUE_BASE[0]
        hero.waypoints = [(dx, hero.lane_y)]
        self._auto_target_nearest(hero, game)

    def _apply_retreat(self, hero, game):
        """撤退: 回到己方水晶（回血光环范围内）"""
        base = BLUE_BASE if hero.team == 'blue' else RED_BASE
        hero.target = None
        # 优先回到最近的存活水晶旁（回血光环200范围）
        attr = 'blue_crystals' if hero.team == 'blue' else 'red_crystals'
        crystals = [c for c in getattr(game, attr, []) if c.alive]
        if crystals:
            nearest = min(crystals, key=lambda c: abs(c.x - hero.x) + abs(c.y - hero.y))
            hero.waypoints = [(nearest.x, nearest.y)]
        else:
            hero.waypoints = [(base[0], hero.lane_y)]

    def _apply_gank(self, hero, game, d):
        """游走抓人: 根据target选择目标"""
        target_pos = d.get('target_pos')
        if target_pos:
            hero.waypoints = [(target_pos[0], target_pos[1])]

        target_type = d.get('target', 'hero')
        if target_type == 'hero':
            # 优先攻击玩家英雄
            enemies = [e for e in game.get_all_enemies(hero.team)
                       if hasattr(e, 'hero_type') and e.alive and e.is_player]
            if not enemies:
                enemies = [e for e in game.get_all_enemies(hero.team)
                           if hasattr(e, 'hero_type') and e.alive]
            if enemies:
                target = min(enemies, key=lambda e: e.hp / e.max_hp)
                hero.target = target
                hero.waypoints = [(target.x, target.y)]
        else:
            self._auto_target_by_priority(hero, game, target_type)

    def _apply_defend(self, hero, game, d):
        """防守: 根据 target 选择防守目标"""
        target_type = d.get('target', 'none')

        if target_type == 'tower':
            # 防守血量最低的己方塔
            towers = [e for e in game.entities
                      if hasattr(e, 'tier') and e.alive and e.team == hero.team]
            if towers:
                nearest = min(towers, key=lambda t: t.hp / t.max_hp)
                hero.waypoints = [(nearest.x, hero.lane_y)]
        elif target_type == 'crystal':
            # 防守己方水晶
            attr = 'blue_crystals' if hero.team == 'blue' else 'red_crystals'
            crystals = [c for c in getattr(game, attr, []) if c.alive]
            if crystals:
                nearest = min(crystals, key=lambda c: abs(c.x - hero.x) + abs(c.y - hero.y))
                hero.waypoints = [(nearest.x, nearest.y)]
        else:
            # 默认：找最近的己方塔
            towers = [e for e in game.entities
                      if hasattr(e, 'tier') and e.alive and e.team == hero.team]
            if towers:
                nearest = min(towers, key=lambda t: abs(t.x - hero.x) + abs(t.y - hero.y))
                hero.waypoints = [(nearest.x, hero.lane_y)]
        self._auto_target_nearest(hero, game)

    def _apply_jungle(self, hero, game):
        """打野: 找最近的野怪"""
        monsters = [e for e in game.entities
                    if hasattr(e, 'monster_type') and e.alive]
        if monsters:
            nearest = min(monsters, key=lambda m: abs(m.x - hero.x) + abs(m.y - hero.y))
            hero.target = nearest
            hero.waypoints = [(nearest.x, nearest.y)]

    def _apply_group(self, hero, game):
        """抱团: 移动到队友平均位置"""
        allies = [e for e in game.entities
                  if hasattr(e, 'hero_type') and e.team == hero.team
                  and e.alive and e is not hero]
        if allies:
            avg_x = sum(a.x for a in allies) / len(allies)
            avg_y = sum(a.y for a in allies) / len(allies)
            hero.waypoints = [(avg_x, avg_y)]
        self._auto_target_nearest(hero, game)

    def _auto_target_nearest(self, hero, game):
        """自动索敌：攻击范围内最近的敌人"""
        enemies = [e for e in game.get_all_enemies(hero.team)
                   if e.alive and hasattr(e, 'hp')]
        if enemies:
            nearest = min(enemies,
                          key=lambda e: abs(e.x - hero.x) + abs(e.y - hero.y))
            d = abs(nearest.x - hero.x) + abs(nearest.y - hero.y)
            if d < hero.attack_range + 80:
                hero.target = nearest

    def _auto_target_by_priority(self, hero, game, target_type):
        """根据目标类型优先索敌"""
        if target_type == 'hero':
            enemies = [e for e in game.get_all_enemies(hero.team)
                       if hasattr(e, 'hero_type') and e.alive
                       and abs(e.x - hero.x) + abs(e.y - hero.y) < hero.attack_range + 100]
            if enemies:
                hero.target = min(enemies, key=lambda e: e.hp / e.max_hp)
                return
        elif target_type == 'tower':
            towers = [e for e in game.get_all_enemies(hero.team)
                      if hasattr(e, 'tier') and e.alive
                      and abs(e.x - hero.x) + abs(e.y - hero.y) < hero.attack_range + 100]
            if towers:
                hero.target = towers[0]
                return
        elif target_type == 'minion':
            minions = [e for e in game.get_all_enemies(hero.team)
                       if hasattr(e, 'lane_y') and not hasattr(e, 'hero_type') and e.alive
                       and abs(e.x - hero.x) + abs(e.y - hero.y) < hero.attack_range + 80]
            if minions:
                hero.target = min(minions, key=lambda m: abs(m.x - hero.x))
                return
        # 回退到普通索敌
        self._auto_target_nearest(hero, game)

    # ====== 技能使用判断 ======

    def should_use_ability(self, hero, slot, game):
        """判断 LLM 控制的英雄是否应该使用指定技能。
        返回 True/False，无指令时返回 None（由原逻辑处理）。
        """
        if not self.should_control_hero(hero):
            return None
        ab_directive = self.get_ability_directive(hero, slot)
        if ab_directive is None:
            return None

        use_mode, condition = ab_directive
        ab = hero.abilities.get(slot)
        if not ab or ab['cur_cd'] > 0:
            return False

        nearby_enemies = [e for e in game.get_all_enemies(hero.team)
                          if e.alive and hasattr(e, 'hp')
                          and abs(e.x - hero.x) + abs(e.y - hero.y) < 250]
        hp_pct = hero.hp / hero.max_hp if hero.max_hp > 0 else 1.0

        if use_mode == 'never':
            return False
        elif use_mode == 'save':
            # 保留技能：只在团战或濒死时用
            if slot == 'e':
                return hp_pct < 0.2 or len(nearby_enemies) >= 3
            return hp_pct < 0.3 and len(nearby_enemies) >= 2
        elif use_mode == 'aggressive':
            return len(nearby_enemies) >= 1
        elif use_mode == 'defensive':
            return hp_pct < 0.5 or len(nearby_enemies) >= 2
        elif use_mode == 'conditional':
            # 仅 E 技能支持 conditional
            if condition == 'low_hp':
                return hp_pct < 0.35
            elif condition == 'group_3plus':
                return len(nearby_enemies) >= 3
            elif condition == 'enemy_player_near':
                player_near = any(hasattr(e, 'is_player') and e.is_player
                                  for e in nearby_enemies)
                return player_near
            elif condition == 'always':
                return len(nearby_enemies) >= 1
            return False
        return False
