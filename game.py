"""游戏主类"""
import time
import math
import random
import pygame as pg
import config as CFG
from utils import dist, rnd, get_font
from entities.entity import Entity
from entities.hero import Hero, HERO_TYPES
from entities.minion import Minion
from entities.tower import Tower
from entities.monster import Monster
from entities.crystal import Crystal
from effects.projectile import Projectile
from effects.floating_text import FloatingText
from effects.loot_drop import LootDrop
from systems.camera import Camera
from systems.renderer import Renderer
from systems.input_handler import InputHandler
from systems.physics import PhysicsSystem
from ui.hud import HUD
from ui.minimap import Minimap


class Game:
    def __init__(self, hero_type=None, screen=None, llm_settings=None):
        self.cfg = CFG
        self.entities = []
        self.projectiles = []
        self.floating_texts = []
        self.loot_drops = []
        self.delayed_effects = []
        self.click_markers = []    # 点击指示器 [{x, y, life}]
        self.monster_respawns = []  # 野怪复活 [{monster, timer}]
        self.shop_open = False      # 装备商店是否打开
        self.shop_items = []        # 当前商店可选装备
        self.minion_timer = 0.0
        self.game_time = 0.0
        self.game_over = False
        self.winner = None
        self.player_hero = None
        self.screen_shake = 0.0
        self._started = False
        self._enemy_cache = None
        self._hero_type = hero_type
        self._llm_settings = llm_settings or {}
        self.llm_ai = None  # 稍后在 init() 中初始化

        # Pygame — 如果外部没有传入 screen，自己创建
        if screen is None:
            pg.init()
            self.screen = pg.display.set_mode((CFG.VIEW_W, CFG.VIEW_H), pg.RESIZABLE | pg.SCALED, vsync=1)
            pg.display.set_caption('三线对决 - MOBA (Python版) [F11 全屏]')
        else:
            self.screen = screen
        self.view_w, self.view_h = self.screen.get_size()
        self.clock = pg.time.Clock()

        # 子系统
        self.camera = Camera()
        self.renderer = Renderer()
        self.input_handler = InputHandler(self)
        self.physics = PhysicsSystem()
        self.hud = HUD(self)
        self.minimap = Minimap()

        # 初始化
        self.init()

    def init(self):
        # 防御塔
        for lane in range(3):
            for key, tier in [('blue_outer', 'outer'), ('blue_inner', 'inner'),
                              ('red_inner', 'inner'), ('red_outer', 'outer')]:
                x, y = CFG.TOWER_POS[key][lane]
                team = 'blue' if 'blue' in key else 'red'
                self.entities.append(Tower(x, y, team, lane, tier))

        # 水晶 (每队3个)
        self.blue_crystals = []
        self.red_crystals = []
        for cx, cy in CFG.CRYSTAL_POS['blue']:
            c = Crystal(cx, cy, 'blue')
            self.blue_crystals.append(c)
            self.entities.append(c)
        for cx, cy in CFG.CRYSTAL_POS['red']:
            c = Crystal(cx, cy, 'red')
            self.red_crystals.append(c)
            self.entities.append(c)

        # 野怪
        for x, y, mtype in CFG.JUNGLE_CAMPS:
            self.entities.append(Monster(x, y, mtype))

        # 英雄 — 如果外部指定了英雄类型，使用它
        type_list = list(CFG.HERO_TYPES.keys())
        if self._hero_type and self._hero_type in type_list:
            player_type = self._hero_type
            type_list.remove(player_type)
            random.shuffle(type_list)
            type_list.insert(0, player_type)
        else:
            random.shuffle(type_list)
            player_type = type_list[0]

        # 蓝方
        p = Hero(CFG.BLUE_BASE[0] + 80, CFG.LANES[1]['y'], 'blue', 1,
                 f'玩家·{CFG.HERO_TYPES[player_type]["name"]}', True, player_type)
        self.player_hero = p
        self.entities.append(p)
        self.camera.follow(p)

        for i, t in enumerate([type_list[1], type_list[2], type_list[3]]):
            lane = [0, 2, 1][i]
            y_off = -40 if i == 2 else 0
            self.entities.append(Hero(CFG.BLUE_BASE[0] + 80,
                                       CFG.LANES[lane]['y'] + y_off,
                                       'blue', lane,
                                       f'队友·{CFG.HERO_TYPES[t]["name"]}', False, t))

        # 红方
        for i, t in enumerate(type_list[4:8]):
            lane = [0, 1, 2, 1][i]
            y_off = 40 if i == 3 else 0
            self.entities.append(Hero(CFG.RED_BASE[0] - 80,
                                       CFG.LANES[lane]['y'] + y_off,
                                       'red', lane,
                                       f'敌方·{CFG.HERO_TYPES[t]["name"]}', False, t))

        # 注册所有实体到物理系统
        for e in self.entities:
            if e.solid:
                self.physics.register(e)

        # LLM AI 控制器初始化
        from systems.llm_ai import LLMAIController
        self.llm_ai = LLMAIController(self._llm_settings)

        self.spawn_minion_wave()

    # ---- 实体查询 ----

    def get_all_entities(self):
        return self.entities

    def get_all_enemies(self, team):
        if self._enemy_cache:
            return self._enemy_cache.get(team, [])
        return [e for e in self.entities if e.alive and e.team != team]

    # ---- 生成 ----

    def spawn_minion_wave(self):
        # 计算当前小兵强化倍率
        scale_hp, scale_dmg, scale_spd = 1.0, 1.0, 0
        for t, hp_m, dmg_m, spd_b in CFG.MINION_SCALING:
            if self.game_time >= t:
                scale_hp, scale_dmg, scale_spd = hp_m, dmg_m, spd_b
        use_super = self.game_time >= CFG.SUPER_MINION_TIME

        for lane in range(3):
            ly = CFG.LANES[lane]['y']
            mtype = 'super' if use_super else 'melee'
            for i in range(3):
                m = Minion(CFG.BLUE_BASE[0] + 100 + i * 25, ly + rnd(-10, 10),
                           'blue', lane, mtype, scale_hp, scale_dmg, scale_spd)
                self.entities.append(m)
            for i in range(3):
                m = Minion(CFG.BLUE_BASE[0] + 100 + i * 20, ly + rnd(-6, 6),
                           'blue', lane, 'ranged', scale_hp, scale_dmg, scale_spd)
                self.entities.append(m)
            mtype = 'super' if use_super else 'melee'
            for i in range(3):
                m = Minion(CFG.RED_BASE[0] - 100 - i * 25, ly + rnd(-10, 10),
                           'red', lane, mtype, scale_hp, scale_dmg, scale_spd)
                self.entities.append(m)
            for i in range(3):
                m = Minion(CFG.RED_BASE[0] - 100 - i * 20, ly + rnd(-6, 6),
                           'red', lane, 'ranged', scale_hp, scale_dmg, scale_spd)
                self.entities.append(m)

    # ---- 特效 ----

    def add_projectile(self, x, y, target, color, speed, ptype, extra=None):
        self.projectiles.append(Projectile(x, y, target, color, speed, ptype, extra))

    def add_floating_text(self, x, y, text, is_damage=False, color=None):
        self.floating_texts.append(FloatingText(x, y, text, is_damage, color))

    def add_aoe_effect(self, x, y, radius, color, dur):
        self.projectiles.append(Projectile(x, y, None, color, 0, 'aoe',
                                           {'radius': radius, 'duration': dur}))

    def add_ultimate_effect(self, x, y, radius, color):
        self.add_aoe_effect(x, y, radius, color, 0.35)
        self.add_aoe_effect(x, y, radius * 0.5, '#ffffff', 0.25)
        self.add_aoe_effect(x, y, radius * 0.2, color, 0.4)
        for i in range(6):
            ang = (i / 6) * math.pi * 2
            px = x + math.cos(ang) * radius * rnd(0.3, 0.9)
            py = y + math.sin(ang) * radius * rnd(0.3, 0.9)
            self.add_aoe_effect(px, py, rnd(6, 12), color, rnd(0.1, 0.2))
        self.screen_shake = 0.3

    def add_slash_effect(self, x, y, angle, width, length, color, dur=0.18):
        """弧形斩击"""
        self.projectiles.append(Projectile(x, y, None, color, 0, 'slash',
                                           {'angle': angle, 'width': width,
                                            'length': length, 'duration': dur}))

    def add_beam_effect(self, x, y, end_x, end_y, color, dur=0.2):
        """光束/射线"""
        self.projectiles.append(Projectile(x, y, None, color, 0, 'beam',
                                           {'endX': end_x, 'endY': end_y, 'duration': dur}))

    def add_burst_effect(self, x, y, radius, color, count=5, dur=0.2):
        """粒子爆发"""
        for i in range(count):
            ang = (i / count) * math.pi * 2 + rnd(-0.4, 0.4)
            spd = radius * rnd(0.5, 1.0)
            p_dur = dur * rnd(0.6, 1.0)
            self.projectiles.append(Projectile(x, y, None, color, 0, 'burst_particle',
                                               {'angle': ang, 'speed': spd,
                                                'radius': rnd(2, 6), 'duration': p_dur}))

    def add_delayed_effect(self, delay, callback):
        self.delayed_effects.append({'timer': delay, 'callback': callback, 'fired': False})

    def add_click_marker(self, wx, wy):
        """在世界坐标 (wx, wy) 添加一个点击指示器，持续约0.6秒"""
        self.click_markers.append({'x': wx, 'y': wy, 'life': 0.6})

    # ---- 拾取 ----

    def pickup_loot(self, hero, loot):
        if len(hero.items) >= CFG.ITEM_COUNT:
            self.add_floating_text(hero.x, hero.y - 30, '装备已满!', False, '#e74c3c')
            return
        hero.items.append(dict(loot.item))
        self.loot_drops = [l for l in self.loot_drops if l is not loot]
        self.add_floating_text(hero.x, hero.y - 30, f'获得: {loot.item["name"]}', False, '#f1c40f')
        if loot.item['id'] == 'shield':
            hero.last_shield_time = time.time()
            hero.shield_active = True

    # ---- 装备商店 ----

    def open_shop(self):
        """打开装备商店，根据游戏时间开放对应层级装备"""
        import random
        self.shop_open = True
        # 确定当前最高可用层级
        max_tier = 1
        for t, tier in CFG.SHOP_TIERS:
            if self.game_time >= t:
                max_tier = max(max_tier, tier)
        available = [it for it in CFG.ITEMS if it.get('tier', 1) <= max_tier]
        random.shuffle(available)
        self.shop_items = available[:4]  # 上架4件

    def close_shop(self):
        self.shop_open = False
        self.shop_items = []

    def buy_item(self, hero, item_idx):
        """购买商店中第 item_idx 件装备"""
        if not self.shop_open or item_idx >= len(self.shop_items):
            return
        if len(hero.items) >= CFG.ITEM_COUNT:
            self.add_floating_text(hero.x, hero.y - 30, '装备已满!', False, '#e74c3c')
            return
        item = self.shop_items[item_idx]
        cost = item.get('cost', 300)
        if hero.gold < cost:
            self.add_floating_text(hero.x, hero.y - 30, f'金币不足! 需要{cost}', False, '#e74c3c')
            return
        hero.gold -= cost
        hero.items.append(dict(item))
        self.add_floating_text(hero.x, hero.y - 30, f'购买: {item["name"]}', False, '#f1c40f')
        if item['id'] == 'shield':
            hero.last_shield_time = time.time()
            hero.shield_active = True
        # 购买后关闭商店
        self.close_shop()

    def sell_item(self, hero, item_idx):
        """出售英雄背包中第 item_idx 件装备，返回50%金币"""
        if item_idx < 0 or item_idx >= len(hero.items):
            return
        item = hero.items.pop(item_idx)
        refund = item.get('cost', 300) // 2
        hero.gold += refund
        self.add_floating_text(hero.x, hero.y - 30, f'出售: {item["name"]} +{refund}G', False, '#f39c12')

    # ---- 主循环 ----

    def update(self, dt):
        if self.game_over:
            return
        # 上限 dt 防止卡顿时实体跳跃
        dt = min(dt, 1.0 / 20)
        self.game_time += dt
        self.minion_timer += dt

        # 帧缓存
        self._enemy_cache = {team: [] for team in ('blue', 'red', 'neutral')}
        for e in self.entities:
            if not e.alive:
                continue
            if e.team != 'blue':
                self._enemy_cache['blue'].append(e)
            if e.team != 'red':
                self._enemy_cache['red'].append(e)
            if e.team != 'neutral':
                self._enemy_cache['neutral'].append(e)

        # 注册新实体到物理系统
        for e in self.entities:
            if e.solid and e not in self.physics._entities:
                self.physics.register(e)

        # 小兵
        if self.minion_timer >= CFG.MINION_SPAWN_INTERVAL:
            self.minion_timer = 0
            self.spawn_minion_wave()

        # 物理碰撞更新（替代旧的 entity.separate）
        self.physics.update(dt)

        # 延迟特效
        for de in self.delayed_effects:
            de['timer'] -= dt
            if de['timer'] <= 0 and not de['fired']:
                de['fired'] = True
                try:
                    de['callback']()
                except Exception:
                    pass
        self.delayed_effects = [de for de in self.delayed_effects if not de['fired']]

        # 实体更新
        update_types = (Hero, Minion, Tower, Monster, Crystal)
        for e in self.entities:
            if isinstance(e, update_types):
                e.update(dt, self)

        # LLM AI 战略决策更新
        if self.llm_ai and self.llm_ai.enabled:
            self.llm_ai.update(dt, self)

        # 特效
        for p in self.projectiles:
            p.update(dt)

        # 弹道碰撞检测（击退/穿透/AoE）
        for p in self.projectiles:
            if not p.alive or not getattr(p, 'owner', None):
                continue
            enemies = self.get_all_enemies(p.owner.team)
            for e in enemies:
                if not e.alive or p in getattr(e, '_hit_by', []):
                    continue
                if not hasattr(e, '_hit_by'):
                    e._hit_by = []
                d = dist((p.x, p.y), (e.x, e.y))
                if d < e.radius + 12:
                    # 击退
                    if getattr(p, 'knockback', 0) > 0 and hasattr(e, 'knockback'):
                        ang = math.atan2(e.y - p.owner.y, e.x - p.owner.x)
                        e.knockback(math.cos(ang) * p.knockback,
                                     math.sin(ang) * p.knockback)
                    e._hit_by.append(p)
                    # onHit 回调
                    on_hit = p.extra.get('onHit') if isinstance(p.extra, dict) else None
                    if on_hit:
                        on_hit(e, p.owner, self)
                    # AoE 爆炸
                    aoe_r = getattr(p, 'aoe_radius', 0) or p.extra.get('aoeRadius', 0)
                    if aoe_r:
                        self.add_aoe_effect(e.x, e.y, aoe_r, p.color, 0.2)
        # 物理衰减
        for e in self.entities:
            if e.alive and hasattr(e, 'apply_friction'):
                e.apply_friction(dt)

        self.projectiles = [p for p in self.projectiles if p.alive]
        for f in self.floating_texts:
            f.update(dt)
        self.floating_texts = [f for f in self.floating_texts if f.life > 0]
        for l in self.loot_drops:
            l.update(dt)
        self.loot_drops = [l for l in self.loot_drops if l.life > 0]
        for cm in self.click_markers:
            cm['life'] -= dt
        self.click_markers = [cm for cm in self.click_markers if cm['life'] > 0]

        self.screen_shake = max(0, self.screen_shake - dt * 2)

        # DOT
        for e in self.entities:
            if not e.alive or e.death_processed:
                continue
            if e._has_dmg_buff is None:
                e._has_dmg_buff = any(b.type in ('burn', 'poison') and not b.expired
                                      for b in e.buffs)
            if not e._has_dmg_buff:
                continue
            for b in e.buffs:
                if b.expired:
                    continue
                if b.type == 'burn':
                    e.hp -= e.max_hp * b.data.get('dmgPct', 0.03) * dt
                    if e.hp <= 0:
                        e.hp = 0
                        e.alive = False
                if b.type == 'poison':
                    e.hp -= e.max_hp * b.data.get('dmgPct', 0.03) * dt
                    if e.hp <= 0:
                        e.hp = 0
                        e.alive = False

        # 死亡处理
        for e in self.entities:
            if e.alive or e.death_processed:
                continue
            e.death_processed = True
            if isinstance(e, Hero):
                e.deaths += 1
                # 重置连杀
                e._kill_spree = 0
                killer = next((h for h in self.entities
                               if isinstance(h, Hero) and h.alive and h.team != e.team
                               and dist((h.x, h.y), (e.x, e.y)) < 600), None)
                if killer:
                    # 击杀奖励 = 基础 + 等级差奖励 + 连杀奖励
                    level_diff = max(0, e.level - killer.level)
                    spree_bonus = getattr(killer, '_kill_spree', 0) * CFG.KILL_SPREE_BONUS
                    gold_reward = CFG.KILL_BASE_GOLD + level_diff * CFG.KILL_LEVEL_BONUS + spree_bonus
                    exp_reward = CFG.KILL_BASE_EXP + level_diff * 20
                    killer.gain_exp(exp_reward)
                    killer.gold += gold_reward
                    killer.kills += 1
                    killer._kill_spree = getattr(killer, '_kill_spree', 0) + 1
                    spree_text = f' 连杀x{killer._kill_spree}!' if killer._kill_spree >= 3 else ''
                    self.add_floating_text(e.x, e.y - 40,
                                           f'击杀! +{gold_reward}G{spree_text}', True, '#f1c40f')
                e.respawn_timer = 8
            elif isinstance(e, Monster):
                item = e.drop_loot()
                self.loot_drops.append(LootDrop(e.x + rnd(-15, 15), e.y + rnd(-15, 15), item))
                # 加入复活队列
                e.respawn_timer_cur = e.respawn_time
                self.monster_respawns.append(e)
            elif isinstance(e, Minion):
                for h in self.entities:
                    if isinstance(h, Hero) and h.alive and h.team != e.team \
                            and dist((h.x, h.y), (e.x, e.y)) < 400:
                        h.gain_exp(10)
                        h.gold += e.reward

        # 清理
        self.entities = [e for e in self.entities
                         if isinstance(e, (Tower, Hero, Crystal)) or e.alive]

        # 野怪复活
        for mr in self.monster_respawns[:]:
            mr.respawn_timer_cur -= dt
            if mr.respawn_timer_cur <= 0:
                mr.hp = mr.max_hp
                mr.alive = True
                mr.death_processed = False
                mr.x, mr.y = mr.spawn_x, mr.spawn_y
                if mr.solid and hasattr(self, 'physics'):
                    self.physics.register(mr)
                self.monster_respawns.remove(mr)

        # 尸体归位 (仅移动，不强制定时器，避免干扰复活倒计时)
        for e in self.entities:
            if isinstance(e, Hero) and not e.alive:
                is_blue = e.team == 'blue'
                bx = CFG.BLUE_BASE[0] + 100 if is_blue else CFG.RED_BASE[0] - 100
                dst = (bx, CFG.LANES[e.lane_idx]['y'])
                if dist((e.x, e.y), dst) > 60:
                    e.move_toward(dst[0], dst[1], dt * 2)

        # 相机
        self.camera.update(dt)

        # 胜负
        self._check_win()

    def _check_win(self):
        # 全部3个水晶被摧毁才算获胜
        blue_dead = all(not c.alive for c in self.blue_crystals)
        red_dead = all(not c.alive for c in self.red_crystals)
        if blue_dead:
            self._end_game('red')
        elif red_dead:
            self._end_game('blue')

    def _end_game(self, winner):
        self.game_over = True
        self.winner = winner
        print(f'游戏结束! {winner} 获胜!')

    def render(self):
        self.screen.fill((245, 247, 250))

        # 屏幕震动
        if self.screen_shake > 0:
            sx = (random.random() - 0.5) * self.screen_shake * 12
            sy = (random.random() - 0.5) * self.screen_shake * 12
            # Simple approach: we'll modify renderer later if needed

        # 主渲染
        self.renderer.render(self, self.screen)

        # UI
        mx, my = pg.mouse.get_pos()
        self.hud.render(self.screen, mx, my)
        self.minimap.render(self, self.screen)

        # Overlay 信息
        font = get_font(14)
        vw = self.view_w
        time_surf = font.render(f'{int(self.game_time)}s', True, (30, 40, 55))
        self.screen.blit(time_surf, (vw // 2 - time_surf.get_width() // 2, 10))

        bk = sum(h.kills for h in self.entities if isinstance(h, Hero) and h.team == 'blue')
        rk = sum(h.kills for h in self.entities if isinstance(h, Hero) and h.team == 'red')
        blue_s = font.render(f'蓝 {bk}', True, (30, 120, 200))
        red_s = font.render(f'{rk} 红', True, (200, 50, 40))
        self.screen.blit(blue_s, (vw // 2 - 40, 28))
        self.screen.blit(red_s, (vw // 2 + 10, 28))

        pg.display.flip()

    def run(self):
        import traceback
        running = True
        while running:
            try:
                if not self.input_handler.handle_events():
                    break
                dt = self.clock.tick(CFG.FPS) / 1000.0
                self.update(dt)
                self.render()
                # 游戏结束后短暂停留，返回 main.py 处理结束菜单
                if self.game_over:
                    pg.time.wait(500)
                    running = False
            except Exception as e:
                traceback.print_exc()
                print(f'⚠️ 游戏出错: {e}')
                pg.time.wait(500)
        # 不调用 pg.quit() — 让 main.py 决定