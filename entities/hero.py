"""英雄 (8职业)"""
import random
import math
import pygame as pg
from .entity import Entity
from config import HERO_TYPES, LANES, BLUE_BASE, RED_BASE
from utils import dist, rnd, get_font


class Hero(Entity):
    def __init__(self, x, y, team, lane_idx, name, is_player, type_id):
        t = HERO_TYPES.get(type_id, HERO_TYPES['warrior'])
        super().__init__(x, y, t['hp'], t['hp'], team, 22)
        self.name = name
        self.lane_idx = lane_idx
        self.lane_y = LANES[lane_idx]['y']
        self.is_player = is_player
        self.hero_type = t['id']
        self.type_name = t['name']
        self.type_icon = t['icon']
        self.attack_dmg = t['atk']
        self.attack_range = t['range']
        self.attack_speed = 1.2
        self.move_speed = t['speed']
        self.weapon = t['weapon']
        self.body_color = t['bodyColor']
        self.head_color = t['headColor']
        # 物理属性
        self.mass = 3.0
        self.solid = True
        self.vx = 0.0
        self.vy = 0.0

        self.gold = 0
        self.exp = 0
        self.max_exp = 100
        self.level = 1
        self.ability_power = 1.0  # 技能伤害等级倍率
        self.kills = 0
        self.deaths = 0
        self._kill_spree = 0

        # 技能深拷贝
        self.abilities = {}
        for k, v in t['abilities'].items():
            self.abilities[k] = dict(v, cur_cd=0)

        # 技能连击/重铸系统（刺客影袭等）
        self._recast_data = {}  # {slot: {'count': N, 'max': M, 'timer': s, 'cd': s}}
        self._recast_heal_pct = {}  # {slot: pct} 连击技能吸血比例

        self.waypoints = []
        self.ai_state = 'idle'
        self.respawn_timer = 0
        self.walk_cycle = 0.0
        self.idle_bob = 0.0
        self.cast_anim = 0.0
        self.death_timer = 0.0
        self.ult_flash = 0.0
        self.weapon_trail = []
        self.breath_anim = 0.0
        self._prev_x = x  # 用于判断行走朝向
        self._prev_y = y
        self.facing = 1 if team == 'blue' else -1  # 面朝方向: 1=右, -1=左
        self._face_angle = 0.0 if team == 'blue' else math.pi  # 360°面朝角度(弧度)
        self._want_attack = False  # 空格强制普攻
        self._combo_count = 0  # 圣骑士普攻连击计数
        self._combo_timer = 0.0  # 连击窗口倒计时

    @property
    def type_data(self):
        return HERO_TYPES[self.hero_type]

    def gain_exp(self, amt):
        self.exp += amt
        if self.exp >= self.max_exp:
            self.exp -= self.max_exp
            self._level_up()

    def _level_up(self):
        self.level += 1
        self.max_exp = int(self.max_exp * 1.3)
        self.max_hp = int(self.max_hp * 1.15)
        self.hp = self.max_hp
        self.attack_dmg = int(self.attack_dmg * 1.10)
        self.attack_speed *= 1.05
        self.ability_power *= 1.08  # 技能伤害随等级+8%
        self.move_speed = int(self.move_speed * 1.03)  # 移速+3%
        self.attack_range = int(self.attack_range * 1.02)  # 攻击范围+2%
        # 技能冷却缩减: 每个技能CD -4%
        for ab in self.abilities.values():
            ab['cd'] = max(1.0, ab['cd'] * 0.96)

    # ========== 技能系统 ==========

    def use_ability(self, slot, game, target_x=None, target_y=None):
        ab = self.abilities.get(slot)
        if not ab:
            return

        # 重铸窗口检查（刺客三段影袭等）
        rd = self._recast_data.get(slot)
        if rd and rd['timer'] > 0 and rd['count'] < rd['max']:
            # 在重铸窗口内，允许再次释放
            if ab['cur_cd'] > 0:
                ab['cur_cd'] = 0  # 临时解除冷却
        elif ab['cur_cd'] > 0:
            return

        # 默认朝英雄面朝方向发射
        if target_x is None or target_y is None:
            target_x = self.x + math.cos(self._face_angle) * 300
            target_y = self.y + math.sin(self._face_angle) * 300

        slot_map = {
            'warrior': self._cast_warrior,
            'mage': self._cast_mage,
            'archer': self._cast_archer,
            'assassin': self._cast_assassin,
            'paladin': self._cast_paladin,
            'necromancer': self._cast_necromancer,
            'druid': self._cast_druid,
            'berserker': self._cast_berserker,
        }
        fn = slot_map.get(self.hero_type)
        if fn:
            fn(slot, game, ab, target_x, target_y)

        # 重铸逻辑：重新读取（_cast_xxx 可能在内部创建了 recast_data）
        rd2 = self._recast_data.get(slot)
        if rd2 and rd2['timer'] > 0 and rd2['count'] < rd2['max']:
            rd2['count'] += 1
            if rd2['count'] >= rd2['max']:
                # 用完次数，进入完整冷却
                ab['cur_cd'] = rd2['cd']
                del self._recast_data[slot]
                if slot in self._recast_heal_pct:
                    del self._recast_heal_pct[slot]
            else:
                # 还有次数，刷新窗口
                rd2['timer'] = 5.0
        else:
            # 普通技能（无重铸窗口），直接进入冷却
            ab['cur_cd'] = ab['cd']

        self.cast_anim = 2.28
        if slot == 'e':
            self.ult_flash = 1.0
            if hasattr(game, 'screen_shake'):
                game.screen_shake = 0.3

    def _admg(self, ab):
        """返回技能基础伤害×等级倍率"""
        return int(ab['dmg'] * self.ability_power)

    def _get_enemies_in_range(self, game, radius):
        return [e for e in game.get_all_entities()
                if e.alive and e.team != self.team
                and dist((self.x, self.y), (e.x, e.y)) < radius]

    # ---- 战士 ----
    def _cast_warrior(self, slot, game, ab, target_x=None, target_y=None):
        if slot == 'q':
            dx = target_x - self.x
            dy = target_y - self.y
            d = math.hypot(dx, dy)
            if d < 5:
                d = 1 if self.team == 'blue' else -1
                dx, dy = d, 0
            cx = self.x + (dx / d) * 150
            cy = self.y + (dy / d) * 150
            for e in game.get_all_enemies(self.team):
                if e.alive and dist((cx, cy), (e.x, e.y)) < 80:
                    e.take_damage(self._admg(ab) + self.total_attack_dmg * 0.5, self)
            game.add_projectile(self.x, self.y, None, '#e53935', 0,
                                'dash', {'endX': cx, 'endY': cy, 'color': '#e53935'})
            ang = math.atan2(dy, dx)
            game.add_slash_effect(cx, cy, ang, 1.5, 90, '#e53935')
            game.add_burst_effect(cx, cy, 60, '#ff1744', 10)
            self.x, self.y = cx, cy
            self.add_buff('shield_buff', 2, {'pct': 0.3})
        elif slot == 'w':
            for e in self._get_enemies_in_range(game, 140):
                e.take_damage(self._admg(ab) + self.total_attack_dmg * 0.3, self)
                if hasattr(e, 'add_buff'):
                    e.add_buff('slow', ab.get('slowDur', 2), {'pct': ab.get('slowPct', 0.5)})
                if hasattr(e, 'knockback'):
                    ang = math.atan2(e.y - self.y, e.x - self.x)
                    e.knockback(math.cos(ang) * 180, math.sin(ang) * 180)
            for i in range(4):
                ang = (i / 4) * math.pi * 2
                game.add_beam_effect(self.x, self.y,
                                     self.x + math.cos(ang) * 120,
                                     self.y + math.sin(ang) * 120, '#e53935', 0.2)
            game.add_burst_effect(self.x, self.y, 100, '#ff5252', 10)
        elif slot == 'e':
            r = ab.get('radius', 180)
            for e in self._get_enemies_in_range(game, r):
                e.take_damage(self._admg(ab) + self.total_attack_dmg * 0.8, self)
                if hasattr(e, 'add_buff'):
                    e.add_buff('slow', 2, {'pct': 0.5})
            base_ang = math.atan2(target_y - self.y, target_x - self.x)
            # 三重斩击弧
            for i in range(2):
                a = base_ang + (i - 0.5) * 0.6
                game.add_delayed_effect(i * 0.06, lambda g=game, ag=a: (
                    g.add_slash_effect(self.x, self.y, ag, 1.8, 130, '#ff1744')
                ) if not g.game_over else None)
            # 冲击波 — 双层扩散环
            for i in range(2):
                delay = 0.15 + i * 0.1
                ring_r = int(r * (0.5 + i * 0.3))
                game.add_delayed_effect(delay, lambda g=game, rr=ring_r: (
                    g.add_aoe_effect(self.x, self.y, rr, '#ff5252', 0.25)
                ) if not g.game_over else None)
            # 地面裂纹 — 放射状光束
            for i in range(5):
                ang = base_ang + (i / 8) * math.pi * 2
                ex = self.x + math.cos(ang) * r * rnd(0.4, 1.0)
                ey = self.y + math.sin(ang) * r * rnd(0.4, 1.0)
                game.add_delayed_effect(i * 0.04, lambda g=game, ax=ex, ay=ey: (
                    g.add_beam_effect(self.x, self.y, ax, ay, '#e53935', 0.3)
                ) if not g.game_over else None)
            game.add_burst_effect(self.x, self.y, r, '#ff1744', 30)
            game.add_ultimate_effect(self.x, self.y, r, '#ff1744')
            self.add_buff('shield_buff', 3, {'pct': 0.25})
    def _cast_mage(self, slot, game, ab, target_x=None, target_y=None):
        if slot == 'q':
            tx, ty = target_x, target_y
            game.add_projectile(self.x, self.y, {'x': tx, 'y': ty, 'alive': True},
                                '#ff6d00', 320, 'mage_fireball',
                                {'aoeRadius': 50, 'knockback': 80, 'owner': self,
                                 'onHit': lambda e, owner, g: (
                                     g.add_burst_effect(e.x, e.y, 50, '#ff6d00', 12, 0.3),
                                     g.add_aoe_effect(e.x, e.y, 45, '#ff8f00', 0.2)
                                 )})
            for e in self._get_enemies_in_range(game, 100):
                e.take_damage(self._admg(ab) + self.total_attack_dmg * 0.4, self)
                if hasattr(e, 'add_buff'):
                    e.add_buff('burn', 3, {'dmgPct': 0.03})
            game.add_burst_effect(self.x, self.y, 50, '#ff6d00', 8)
        elif slot == 'w':
            for e in self._get_enemies_in_range(game, 130):
                e.take_damage(self._admg(ab) + self.total_attack_dmg * 0.2, self)
                if hasattr(e, 'add_buff'):
                    e.add_buff('slow', ab.get('slowDur', 2.5), {'pct': ab.get('slowPct', 0.7)})
            for i in range(5):
                ang = (i / 5) * math.pi * 2
                game.add_beam_effect(self.x, self.y,
                                     self.x + math.cos(ang) * 110,
                                     self.y + math.sin(ang) * 110, '#4fc3f7', 0.2)
            game.add_burst_effect(self.x, self.y, 110, '#80deea', 12)
            self.add_buff('shield_buff', 2, {'pct': 0.25})
            r = ab.get('radius', 200)
            for e in self._get_enemies_in_range(game, r):
                e.take_damage(self._admg(ab) + self.total_attack_dmg, self)
                if hasattr(e, 'add_buff'):
                    e.add_buff('slow', 3, {'pct': 0.4})
                    e.add_buff('burn', 3, {'dmgPct': 0.02})
            # 陨石坠落 — 从天而降的火球
            for i in range(4):
                ox = self.x + rnd(-r * 0.8, r * 0.8)
                oy = self.y + rnd(-r * 0.8, r * 0.8)
                game.add_delayed_effect(i * 0.06, lambda g=game, x=ox, y=oy: (
                    g.add_beam_effect(x, y - 120, x, y, '#ff6d00', 0.2),
                    g.add_burst_effect(x, y, 40, '#ff6d00', 8, 0.2)
                ) if not g.game_over else None)
            # 中央大爆炸
            game.add_delayed_effect(0.3, lambda g=game: (
                g.add_burst_effect(self.x, self.y, int(r * 0.7), '#ff8f00', 14, 0.25)
            ) if not g.game_over else None)
            # 火焰冲击波 — 双层扩散环
            for i in range(2):
                delay = 0.2 + i * 0.1
                game.add_delayed_effect(delay, lambda g=game, rr=int(r*(0.5+i*0.3)): (
                    g.add_aoe_effect(self.x, self.y, rr, '#ff6d00', 0.22)
                ) if not g.game_over else None)
            game.add_burst_effect(self.x, self.y, r, '#ff6d00', 25)
            game.add_ultimate_effect(self.x, self.y, r, '#ff6d00')

    # ---- 射手 ----
    def _cast_archer(self, slot, game, ab, target_x=None, target_y=None):
        if slot == 'q':
            hits = ab.get('hits', 3)
            for i in range(hits):
                off_x = (i - 1) * 15
                off_y = (i - 1) * 8
                game.add_delayed_effect(i * 0.08, lambda g=game, ox=off_x, oy=off_y, owner=self: (
                    g.add_projectile(self.x, self.y,
                                     {'x': target_x + ox, 'y': target_y + oy, 'alive': True},
                                     '#ff8f00', 400, 'hero', {
                                         'straight': True, 'weaponType': 'bow', 'owner': owner,
                                         'pierce': 1, 'maxRange': 420 + 30,
                                         'onHit': lambda e, own, g2: (
                                             e.add_buff('armor_break', 3, {'pct': 0.10}) if hasattr(e, 'add_buff') else None,
                                             g2.add_burst_effect(e.x, e.y, 20, '#ff8f00', 4, 0.1)
                                         )
                                     })
                ) if not g.game_over else None)
            game.add_burst_effect(self.x, self.y, 40, '#ff8f00', 8)
        elif slot == 'w':
            enemies = [e for e in game.get_all_enemies(self.team)
                       if e.alive and dist((self.x, self.y), (e.x, e.y)) < self.attack_range + 60]
            target = enemies[0] if enemies else None
            if target:
                target.take_damage(self._admg(ab) + self.total_attack_dmg * 0.5, self)
                if hasattr(target, 'add_buff'):
                    target.add_buff('root', 0.8, {})
                    target.add_buff('slow', ab.get('slowDur', 2), {'pct': ab.get('slowPct', 0.6)})
                game.add_projectile(self.x, self.y, target, '#4fc3f7', 350, 'hero',
                                    {'aoeRadius': 30, 'knockback': 40, 'owner': self})
        elif slot == 'e':
            r = ab.get('radius', 220)
            for e in self._get_enemies_in_range(game, r):
                e.take_damage(self._admg(ab) + self.total_attack_dmg * 0.6, self)
                if hasattr(e, 'add_buff'):
                    e.add_buff('slow', 1.5, {'pct': 0.3})
                    e.add_buff('armor_break', 3, {'pct': 0.15})
            # 箭雨 — 从天空射下的光束
            for i in range(6):
                ox = self.x + rnd(-r, r)
                oy = self.y + rnd(-r, r)
                game.add_delayed_effect(i * 0.04, lambda g=game, x=ox, y=oy: (
                    g.add_beam_effect(x, y - 80, x, y, '#ffab00', 0.15),
                    g.add_burst_effect(x, y, 25, '#ff8f00', 3, 0.1)
                ) if not g.game_over else None)
            # 中央箭矢风暴
            for i in range(4):
                ang = (i / 4) * math.pi * 2
                ex = self.x + math.cos(ang) * r * 0.5
                ey = self.y + math.sin(ang) * r * 0.5
                game.add_delayed_effect(0.2, lambda g=game, sx=self.x, sy=self.y, ax=ex, ay=ey: (
                    g.add_beam_effect(sx, sy, ax, ay, '#ffab00', 0.2)
                ) if not g.game_over else None)
            game.add_burst_effect(self.x, self.y, r, '#ff8f00', 22)
            game.add_ultimate_effect(self.x, self.y, r, '#ff8f00')

    # ---- 刺客 ----
    def _cast_assassin(self, slot, game, ab, target_x=None, target_y=None):
        if slot == 'q':
            # 影袭 — 固定距离冲刺，5秒内可连续释放最多3次，每次伤害均可吸血
            sx, sy = self.x, self.y
            dx = target_x - self.x
            dy = target_y - self.y
            d = math.hypot(dx, dy)
            max_r = ab.get('range', 200)
            if d < 5:
                d = 1 if self.facing > 0 else -1
                dx, dy = d, 0
            # 始终冲锋固定距离 max_r，方向朝目标
            dx = (dx / d) * max_r
            dy = (dy / d) * max_r
            self.x += dx
            self.y += dy
            ex, ey = self.x, self.y
            # 首次释放时设置重铸窗口
            rd = self._recast_data.get('q')
            if not rd or rd['timer'] <= 0:
                self._recast_data['q'] = {'count': 0, 'max': 3, 'timer': 5.0, 'cd': ab['cd']}
                self._recast_heal_pct['q'] = 1.0  # 影袭造成伤害的100%吸血
            dmg_val = int(self._admg(ab) + self.total_attack_dmg * 0.5)
            total_dmg_dealt = 0
            # 伤害路径上所有敌人 — 点到线段距离判定
            seg_dx, seg_dy = ex - sx, ey - sy
            seg_len2 = seg_dx * seg_dx + seg_dy * seg_dy
            hit_r = 55
            for e in game.get_all_enemies(self.team):
                if not e.alive:
                    continue
                # 点到线段最近距离
                if seg_len2 < 1:
                    d = dist((sx, sy), (e.x, e.y))
                else:
                    t = max(0, min(1, ((e.x - sx) * seg_dx + (e.y - sy) * seg_dy) / seg_len2))
                    proj_x = sx + t * seg_dx
                    proj_y = sy + t * seg_dy
                    d = dist((proj_x, proj_y), (e.x, e.y))
                if d < hit_r:
                    hp_before = e.hp
                    e.take_damage(dmg_val, self)
                    actual_dmg = max(0, hp_before - e.hp)
                    total_dmg_dealt += actual_dmg
            # 回血 = 所有敌人受到的总伤害
            if total_dmg_dealt > 0:
                self.heal(total_dmg_dealt)
            # 视觉效果 — 流星冲刺
            game.add_projectile(sx, sy, None, '#00bcd4', 0,
                                'dash', {'endX': ex, 'endY': ey, 'color': '#00bcd4'})
            # 沿路径散射粒子 — 拖尾光点
            n_trail = 8
            for ti in range(n_trail):
                frac = (ti + 1) / (n_trail + 1)
                tx = sx + (ex - sx) * frac
                ty = sy + (ey - sy) * frac
                game.add_delayed_effect(ti * 0.015, lambda g=game, ax=tx, ay=ty: (
                    g.add_burst_effect(ax, ay, 25, '#00e5ff', 3, 0.12),
                    g.add_burst_effect(ax + rnd(-8, 8), ay + rnd(-8, 8), 12, '#80deea', 2, 0.08)
                ) if not g.game_over else None)
            # 起点/终点爆发
            game.add_burst_effect(sx, sy, 50, '#00bcd4', 12)
            game.add_burst_effect(ex, ey, 60, '#00e5ff', 14)
            game.add_burst_effect(ex, ey, 30, '#ffffff', 5, 0.08)
            rd2 = self._recast_data.get('q', {})
            cnt = rd2.get('count', 0) + 1
            game.add_floating_text(ex, ey - 20, f'影袭·{cnt}/3', False, '#00e5ff')
            if total_dmg_dealt > 0:
                game.add_floating_text(self.x, self.y - 30, f'+{total_dmg_dealt}HP', False, '#2ecc71')
        elif slot == 'w':
            # 烟幕 — 光柱 + 击退 + 减速3秒 + 3秒吸血+攻速buff
            total_heal = 0
            for e in self._get_enemies_in_range(game, 130):
                dmg_dealt = int(self._admg(ab) + self.total_attack_dmg * 0.2)
                e.take_damage(dmg_dealt, self)
                total_heal += int(dmg_dealt * 0.5)
                if hasattr(e, 'add_buff'):
                    e.add_buff('slow', 3, {'pct': 0.4})
                if hasattr(e, 'knockback'):
                    ang = math.atan2(e.y - self.y, e.x - self.x)
                    e.knockback(math.cos(ang) * 200, math.sin(ang) * 200)
            self.heal(total_heal)
            # 3秒吸血+攻速buff
            self.add_buff('lifesteal_buff', 3, {'pct': 0.3})
            self.add_buff('atk_speed_buff', 3, {'pct': 0.5})
            game.add_floating_text(self.x, self.y - 30, '嗜血+急速 3秒!', False, '#e91e63')
            # 8道光束 + 烟幕圈
            game.add_burst_effect(self.x, self.y, 110, '#26c6da', 16)
            game.add_aoe_effect(self.x, self.y, 130, '#00bcd4', 0.4)
            for i in range(8):
                ang = (i / 8) * math.pi * 2
                ex = self.x + math.cos(ang) * 120
                ey = self.y + math.sin(ang) * 120
                game.add_beam_effect(self.x, self.y, ex, ey, '#00bcd4', 0.3)
                game.add_delayed_effect(i * 0.02, lambda g=game, ax=ex, ay=ey: (
                    g.add_burst_effect(ax, ay, 20, '#00e5ff', 3, 0.08)
                ) if not g.game_over else None)
        elif slot == 'e':
            enemies = [e for e in game.get_all_enemies(self.team)
                       if e.alive and dist((self.x, self.y), (e.x, e.y)) < ab.get('range', 180)]
            target = enemies[0] if enemies else None
            if target and target.alive:
                dmg = self._admg(ab) + self.total_attack_dmg
                target.take_damage(dmg, self)
                # 影分身环绕 — 多个暗影斩击
                for i in range(5):
                    ang = (i / 5) * math.pi * 2
                    cx = target.x + math.cos(ang) * 40
                    cy = target.y + math.sin(ang) * 40
                    game.add_delayed_effect(i * 0.03, lambda g=game, ax=cx, ay=cy, a=ang: (
                        g.add_slash_effect(ax, ay, a, 1.5, 50, '#00e5ff'),
                        g.add_burst_effect(ax, ay, 20, '#00bcd4', 4, 0.1)
                    ) if not g.game_over else None)
                # 终结一击 — 暗影爆破
                game.add_delayed_effect(0.2, lambda g=game, t=target: (
                    g.add_beam_effect(self.x, self.y, t.x, t.y, '#00e5ff', 0.15),
                    g.add_burst_effect(t.x, t.y, 60, '#00bcd4', 10, 0.2)
                ) if not g.game_over else None)
            # 刺客消失/出现雾
            for i in range(3):
                ox = self.x + rnd(-40, 40)
                oy = self.y + rnd(-40, 40)
                game.add_delayed_effect(i * 0.04, lambda g=game, x=ox, y=oy: (
                    g.add_aoe_effect(x, y, 15, '#26c6da', 0.15)
                ) if not g.game_over else None)
            game.add_burst_effect(self.x, self.y, 100, '#00bcd4', 25)
            game.add_ultimate_effect(self.x, self.y, 120, '#00bcd4')

    # ---- 圣骑士 ----
    def _cast_paladin(self, slot, game, ab, target_x=None, target_y=None):
        if slot == 'q':
            # 圣光击 — 光柱绕身旋转一圈，造成物理冲击，摧毁敌方弹道
            r = ab.get('radius', 140)
            dmg_val = self._admg(ab)
            sx, sy = self.x, self.y
            # 伤害 + 击退周围敌人
            for e in self._get_enemies_in_range(game, r):
                e.take_damage(dmg_val + self.total_attack_dmg * 0.55, self)
                if hasattr(e, 'knockback'):
                    ang_to = math.atan2(e.y - sy, e.x - sx)
                    e.knockback(math.cos(ang_to) * 220, math.sin(ang_to) * 220)
            # 摧毁周围敌方弹道（抵挡攻击）
            for ep in game.projectiles:
                if not ep.alive or ep.type in ('slash', 'beam', 'aoe', 'burst_particle', 'dash'):
                    continue
                ep_owner = getattr(ep, 'owner', None)
                if ep_owner and getattr(ep_owner, 'team', None) == self.team:
                    continue
                if dist((sx, sy), (ep.x, ep.y)) < r:
                    ep.alive = False
            # 旋转光柱 — 10 道光束绕身一圈
            n_beams = 10
            for i in range(n_beams):
                ang = (i / n_beams) * math.pi * 2
                ex = sx + math.cos(ang) * r
                ey = sy + math.sin(ang) * r
                game.add_delayed_effect(i * 0.025, lambda g=game, ax=ex, ay=ey, a=ang, rr=r: (
                    g.add_beam_effect(sx, sy, ax, ay, '#fff176', 0.25),
                    g.add_burst_effect(ax, ay, 25, '#fdd835', 5, 0.12),
                    g.add_aoe_effect(ax, ay, 20, '#ffffff', 0.15),
                    [e.take_damage(int(dmg_val * 0.25), self)
                     for e in g.get_all_enemies(self.team)
                     if e.alive and dist((ax, ay), (e.x, e.y)) < 30]
                    or True
                ) if not g.game_over else None)
            game.add_burst_effect(sx, sy, r, '#fdd835', 16)
            game.add_aoe_effect(sx, sy, r, '#fff176', 0.45)
            # 自身回复
            self.heal(int(dmg_val * 0.2))
        elif slot == 'w':
            r = ab.get('radius', 150)
            for e in game.get_all_entities():
                if e.alive and e.team == self.team and dist((self.x, self.y), (e.x, e.y)) < r:
                    if hasattr(e, 'add_buff'):
                        e.add_buff('shield_buff', 3, {'pct': 0.3})
                    e.heal(int(e.max_hp * 0.3))
            game.add_burst_effect(self.x, self.y, r, '#ffee58', 20)
            game.add_aoe_effect(self.x, self.y, r, '#fff176', 0.5)
        elif slot == 'e':
            r = ab.get('radius', 240)
            # 天罚方向 — 360° 任意方向，朝鼠标/面朝方向
            base_ang = math.atan2(target_y - self.y, target_x - self.x)
            cone_half = 0.55
            # 锥形范围伤害 + 物理击退
            for e in game.get_all_enemies(self.team):
                if not e.alive:
                    continue
                d = dist((self.x, self.y), (e.x, e.y))
                if d > r:
                    continue
                ang_to = math.atan2(e.y - self.y, e.x - self.x)
                ang_diff = abs(((ang_to - base_ang + math.pi) % (2 * math.pi)) - math.pi)
                if ang_diff < cone_half:
                    e.take_damage(self._admg(ab) + self.total_attack_dmg * 0.9, self)
                    if hasattr(e, 'add_buff'):
                        e.add_buff('slow', 2.5, {'pct': 0.6})
                    if hasattr(e, 'knockback'):
                        kb_str = 300 * (1 - d / r)
                        e.knockback(math.cos(base_ang) * kb_str,
                                    math.sin(base_ang) * kb_str)
            # 天罚光柱 — 密集从天而降 + 每道光柱触碰造成额外伤害
            for i in range(5):
                ang_col = base_ang + rnd(-cone_half, cone_half)
                dist_out = r * rnd(0.2, 0.9)
                ox = self.x + math.cos(ang_col) * dist_out
                oy = self.y + math.sin(ang_col) * dist_out
                game.add_delayed_effect(i * 0.05, lambda g=game, x=ox, y=oy, dmg=self._admg(ab), owner=self: (
                    g.add_beam_effect(x, y - 180, x, y + 25, '#fff176', 0.35),
                    g.add_aoe_effect(x, y, 28, '#fdd835', 0.2),
                    g.add_burst_effect(x, y, 25, '#fdd835', 4, 0.12),
                    [e.take_damage(int(dmg * 0.3), owner)
                     for e in g.get_all_enemies(owner.team)
                     if e.alive and dist((x, y), (e.x, e.y)) < 35] or True
                ) if not g.game_over else None)
            # 圣光审判 — 中央巨大光柱朝目标方向射出
            end_x = self.x + math.cos(base_ang) * r * 1.1
            end_y = self.y + math.sin(base_ang) * r * 1.1
            game.add_delayed_effect(0.35, lambda g=game, ex=end_x, ey=end_y: (
                g.add_beam_effect(self.x, self.y, ex, ey, '#ffffff', 0.5),
                g.add_aoe_effect(ex, ey, 45, '#ffffff', 0.3)
            ) if not g.game_over else None)
            # 扩散冲击波 — 快速推进
            for i in range(2):
                delay = 0.15 + i * 0.1
                ring_r = r * (0.35 + i * 0.3)
                game.add_delayed_effect(delay, lambda g=game, rr=ring_r, ba=base_ang: (
                    g.add_aoe_effect(
                        self.x + math.cos(ba) * rr * 0.3,
                        self.y + math.sin(ba) * rr * 0.3,
                        int(rr), '#fff176', 0.35)
                ) if not g.game_over else None)
            game.add_burst_effect(self.x, self.y, r, '#fdd835', 8)
            game.add_ultimate_effect(self.x, self.y, r, '#fdd835')

    # ---- 死灵法师 ----
    def _cast_necromancer(self, slot, game, ab, target_x=None, target_y=None):
        if slot == 'q':
            enemies = [e for e in game.get_all_enemies(self.team)
                       if e.alive and dist((self.x, self.y), (e.x, e.y)) < 300]
            target = enemies[0] if enemies else None
            if target:
                game.add_projectile(self.x, self.y, target, '#7b1fa2', 300, 'dark_orb',
                                    {'aoeRadius': 40, 'knockback': 60, 'owner': self,
                                     'onHit': lambda e, owner, g: (
                                         g.add_burst_effect(e.x, e.y, 35, '#7b1fa2', 6, 0.2)
                                     )})
                target.take_damage(self._admg(ab) + self.total_attack_dmg * 0.4, self)
            game.add_burst_effect(self.x, self.y, 35, '#7b1fa2', 5)
        elif slot == 'w':
            for e in self._get_enemies_in_range(game, 150):
                e.take_damage(self._admg(ab) + self.total_attack_dmg * 0.3, self)
                if hasattr(e, 'add_buff'):
                    e.add_buff('root', 0.8, {})
                    e.add_buff('slow', ab.get('slowDur', 2), {'pct': ab.get('slowPct', 0.8)})
            for i in range(4):
                ang = (i / 4) * math.pi * 2
                ex = self.x + math.cos(ang) * 130
                ey = self.y + math.sin(ang) * 130
                game.add_beam_effect(ex, ey - 30, ex, ey + 10, '#7b1fa2', 0.2)
            game.add_burst_effect(self.x, self.y, 110, '#9c27b0', 8)
        elif slot == 'e':
            r = ab.get('radius', 220)
            total_dmg_dealt = 0
            for e in self._get_enemies_in_range(game, r):
                hp_before = e.hp
                e.take_damage(self._admg(ab) + self.total_attack_dmg * 0.7, self)
                total_dmg_dealt += max(0, hp_before - e.hp)
                if hasattr(e, 'add_buff'):
                    e.add_buff('poison', 3, {'dmgPct': 0.04})
            self.heal(int(total_dmg_dealt * 0.25))
            # 亡灵天灾 — 从地面升起的灵魂
            for i in range(6):
                ox = self.x + rnd(-r, r)
                oy = self.y + rnd(-r, r)
                # 从地面向上升起的光束（灵魂升天）
                game.add_delayed_effect(i * 0.05, lambda g=game, x=ox, y=oy: (
                    g.add_beam_effect(x, y + 10, x, y - 40, '#9c27b0', 0.2),
                    g.add_aoe_effect(x, y, 25, '#7b1fa2', 0.15),
                    g.add_burst_effect(x, y, 20, '#ba68c8', 4, 0.1)
                ) if not g.game_over else None)
            # 中央暗影漩涡
            for i in range(3):
                delay = 0.2 + i * 0.06
                game.add_delayed_effect(delay, lambda g=game, rr=int(60+i*30): (
                    g.add_aoe_effect(self.x, self.y, rr, '#4a148c', 0.2)
                ) if not g.game_over else None)
            # 灵魂吸收
            game.add_delayed_effect(0.35, lambda g=game: (
                g.add_burst_effect(self.x, self.y, int(r * 0.6), '#7b1fa2', 12, 0.25)
            ) if not g.game_over else None)
            game.add_burst_effect(self.x, self.y, r, '#7b1fa2', 25)
            game.add_ultimate_effect(self.x, self.y, r, '#7b1fa2')

    # ---- 德鲁伊 ----
    def _cast_druid(self, slot, game, ab, target_x=None, target_y=None):
        if slot == 'q':
            for e in self._get_enemies_in_range(game, 170):
                e.take_damage(self._admg(ab) + self.total_attack_dmg * 0.3, self)
                if hasattr(e, 'add_buff'):
                    e.add_buff('root', 0.8, {})
                    e.add_buff('slow', 2, {'pct': 0.5})
                    e.add_buff('poison', ab.get('dur', 3), {'dmgPct': 0.03})
            for i in range(4):
                ang = (i / 4) * math.pi * 2
                game.add_beam_effect(self.x, self.y,
                                     self.x + math.cos(ang) * 150,
                                     self.y + math.sin(ang) * 150, '#66bb6a', 0.2)
            game.add_burst_effect(self.x, self.y, 130, '#81c784', 10)
        elif slot == 'w':
            r = ab.get('radius', 160)
            for e in game.get_all_entities():
                if e.alive and e.team == self.team and dist((self.x, self.y), (e.x, e.y)) < r:
                    e.heal(self._admg(ab) * 0.5 + self.total_attack_dmg * 0.3)
                    if hasattr(e, 'add_buff'):
                        e.add_buff('shield_buff', 3, {'pct': 0.25})
            for i in range(5):
                ang = (i / 5) * math.pi * 2
                game.add_beam_effect(self.x, self.y,
                                     self.x + math.cos(ang) * r,
                                     self.y + math.sin(ang) * r, '#a5d6a7', 0.2)
            game.add_burst_effect(self.x, self.y, r, '#81c784', 12)
        elif slot == 'e':
            r = ab.get('radius', 240)
            for e in self._get_enemies_in_range(game, r):
                e.take_damage(self._admg(ab) + self.total_attack_dmg * 0.8, self)
                if hasattr(e, 'add_buff'):
                    e.add_buff('slow', 3, {'pct': 0.6})
            for e in game.get_all_entities():
                if e.alive and e.team == self.team and dist((self.x, self.y), (e.x, e.y)) < r:
                    e.heal(int(e.max_hp * 0.15))
            # 自然之怒 — 藤蔓从中心向外扩散
            for i in range(8):
                ang = (i / 8) * math.pi * 2 + rnd(-0.15, 0.15)
                dist_out = r * rnd(0.3, 1.0)
                ex = self.x + math.cos(ang) * dist_out
                ey = self.y + math.sin(ang) * dist_out
                game.add_delayed_effect(i * 0.03, lambda g=game, sx=self.x, sy=self.y, ax=ex, ay=ey: (
                    g.add_beam_effect(sx, sy, ax, ay, '#66bb6a', 0.22)
                ) if not g.game_over else None)
            # 叶片爆炸
            for i in range(6):
                ox = self.x + rnd(-r, r)
                oy = self.y + rnd(-r, r)
                game.add_delayed_effect(i * 0.04, lambda g=game, x=ox, y=oy: (
                    g.add_burst_effect(x, y, 35, '#43a047', 4, 0.15),
                    g.add_aoe_effect(x, y, 20, '#81c784', 0.15)
                ) if not g.game_over else None)
            # 生命绽放 — 绿色光环
            for i in range(2):
                delay = 0.2 + i * 0.12
                game.add_delayed_effect(delay, lambda g=game, rr=int(r*(0.5+i*0.3)): (
                    g.add_aoe_effect(self.x, self.y, rr, '#66bb6a', 0.25)
                ) if not g.game_over else None)
            game.add_burst_effect(self.x, self.y, r, '#43a047', 25)
            game.add_ultimate_effect(self.x, self.y, r, '#43a047')

    # ---- 狂战士 ----
    def _cast_berserker(self, slot, game, ab, target_x=None, target_y=None):
        if slot == 'q':
            hit_count = 0
            for e in [e for e in game.get_all_enemies(self.team)
                      if e.alive and dist((self.x, self.y), (e.x, e.y)) < self.attack_range + 30]:
                e.take_damage(self._admg(ab) + self.total_attack_dmg * 0.6, self)
                hit_count += 1
            if hit_count > 0:
                self.add_buff('shield_buff', 2, {'pct': min(0.4, 0.2 * hit_count)})
            ang = math.atan2(target_y - self.y, target_x - self.x)
            for i in range(2):
                a = ang + (i - 0.5) * 0.5
                game.add_slash_effect(self.x, self.y, a, 1.2, 70, '#ff6d00')
            game.add_burst_effect(self.x, self.y, 50, '#ff6d00', 6)
        elif slot == 'w':
            total_dmg = 0
            for e in self._get_enemies_in_range(game, 130):
                e.take_damage(self._admg(ab) + self.total_attack_dmg * 0.3, self)
                total_dmg += self._admg(ab)
            heal_amt = total_dmg * ab.get('healPct', 0.3)
            self.heal(heal_amt)
            self.add_buff('atk_speed_buff', 3, {'pct': 0.4})
            for i in range(4):
                ang = (i / 4) * math.pi * 2
                game.add_beam_effect(self.x, self.y,
                                     self.x + math.cos(ang) * 110,
                                     self.y + math.sin(ang) * 110, '#ff1744', 0.2)
            game.add_burst_effect(self.x, self.y, 110, '#ff1744', 10)
        elif slot == 'e':
            r = ab.get('radius', 180)
            # 清除自身所有负面效果
            self.buffs = [b for b in self.buffs if b.type in ('atk_speed_buff', 'lifesteal_buff', 'shield_buff')]
            self.add_buff('shield_buff', 3, {'pct': 0.3})
            for e in self._get_enemies_in_range(game, r):
                bonus = 1.5 if self.hp < self.max_hp * 0.3 else 1.0
                final_dmg = (self._admg(ab) + self.total_attack_dmg) * bonus
                e.take_damage(final_dmg, self)
                if hasattr(e, 'add_buff'):
                    e.add_buff('slow', 1.5, {'pct': 0.3})
            # 狂暴旋风 — 双层旋转斩击
            for layer in range(2):
                ang_offset = layer * 0.3
                for i in range(5):
                    ang = (i / 5) * math.pi * 2 + ang_offset
                    slash_r = r * (0.3 + layer * 0.2)
                    game.add_delayed_effect(layer * 0.08 + i * 0.03, lambda g=game, a=ang, sr=slash_r: (
                        g.add_slash_effect(
                            self.x + math.cos(a) * sr * 0.3,
                            self.y + math.sin(a) * sr * 0.3,
                            a, 1.6, 90, '#ff6d00')
                    ) if not g.game_over else None)
            # 血怒脉冲 — 红色脉冲波
            for i in range(2):
                delay = 0.15 + i * 0.1
                pulse_r = r * (0.4 + i * 0.3)
                game.add_delayed_effect(delay, lambda g=game, pr=pulse_r: (
                    g.add_aoe_effect(self.x, self.y, int(pr), '#ff1744', 0.22)
                ) if not g.game_over else None)
            # 地面爆裂
            for i in range(5):
                ang = (i / 5) * math.pi * 2
                ex = self.x + math.cos(ang) * r * rnd(0.5, 1.0)
                ey = self.y + math.sin(ang) * r * rnd(0.5, 1.0)
                game.add_delayed_effect(0.2 + i * 0.03, lambda g=game, ax=ex, ay=ey: (
                    g.add_beam_effect(self.x, self.y, ax, ay, '#ff5252', 0.18),
                    g.add_burst_effect(ax, ay, 20, '#ff6d00', 3, 0.1)
                ) if not g.game_over else None)
            game.add_burst_effect(self.x, self.y, r, '#ff6d00', 25)
            game.add_ultimate_effect(self.x, self.y, r, '#ff6d00')

    def use_ability_ui(self, slot, game, target_x=None, target_y=None):
        ab = self.abilities.get(slot)
        if ab and ab['cur_cd'] <= 0:
            self.use_ability(slot, game, target_x, target_y)

    def _update_abilities(self, dt):
        for ab in self.abilities.values():
            ab['cur_cd'] = max(0, ab['cur_cd'] - dt)
        # 重铸窗口倒计时
        expired = []
        for slot, rd in self._recast_data.items():
            rd['timer'] -= dt
            if rd['timer'] <= 0:
                # 窗口过期，进入冷却
                ab = self.abilities.get(slot)
                if ab:
                    ab['cur_cd'] = rd['cd']
                expired.append(slot)
        for slot in expired:
            del self._recast_data[slot]
            if slot in self._recast_heal_pct:
                del self._recast_heal_pct[slot]

    # ========== 主更新 ==========

    def update(self, dt, game):
        if not self.alive:
            self.death_timer += dt
            if self.respawn_timer > 0:
                self.respawn_timer -= dt
                if self.respawn_timer <= 0:
                    self._respawn(game)
            return

        self.anim_time += dt
        self.breath_anim += dt * 1.5
        self.idle_bob = math.sin(self.breath_anim) * 0.8
        self.hit_flash = max(0, self.hit_flash - dt * 4)
        self.attack_anim = max(0, self.attack_anim - dt * 20)
        self.cast_anim = max(0, self.cast_anim - dt * 6)
        self.ult_flash = max(0, self.ult_flash - dt * 2)
        self.update_effects()
        self._update_abilities(dt)
        self.attack_cd = max(0, self.attack_cd - dt)
        # 普攻连击窗口倒计时
        self._combo_timer = max(0, self._combo_timer - dt)
        if self._combo_timer <= 0:
            self._combo_count = 0

        # 水晶附近回血
        self._heal_near_crystal(dt, game)

        # 武器拖尾
        self.weapon_trail = [t for t in self.weapon_trail if t['life'] > 0]
        for t in self.weapon_trail:
            t['life'] -= dt
        if self.attack_anim > 0.5 or self.cast_anim > 0.3:
            self.weapon_trail.append({'x': self.x, 'y': self.y, 'life': 0.2})

        if self.is_player:
            self._update_player_movement(dt, game)
        else:
            self._update_ai(dt, game)

        # 记录移动方向 + 更新360°面朝角度
        if self.is_player and self.waypoints:
            # 玩家：朝鼠标点击方向（路点方向），不受物理碰撞干扰
            wx, wy = self.waypoints[0]
            dx_wp = wx - self.x
            dy_wp = wy - self.y
            if abs(dx_wp) > 1 or abs(dy_wp) > 1:
                self._face_angle = math.atan2(dy_wp, dx_wp)
                self.facing = 1 if math.cos(self._face_angle) >= 0 else -1
        else:
            # AI / 无路点时：用实际位移方向
            dx_move = self.x - self._prev_x
            dy_move = self.y - self._prev_y
            if abs(dx_move) > 0.3 or abs(dy_move) > 0.3:
                self._face_angle = math.atan2(dy_move, dx_move)
                self.facing = 1 if math.cos(self._face_angle) >= 0 else -1
            self._prev_x = self.x
            self._prev_y = self.y

        moving = len(self.waypoints) > 0 or (not self.is_player and not self.target)
        self.walk_cycle += dt * 8 if moving else self.walk_cycle * -0.08

    def _update_player_movement(self, dt, game):
        range_buf = self.attack_range + 30

        # 空格强制普攻（有目标则打目标，无目标则朝面朝方向空挥）
        if self._want_attack and self.attack_cd <= 0:
            self._want_attack = False
            if self.target and self.target.alive:
                d = dist((self.x, self.y), (self.target.x, self.target.y))
                if d <= self.attack_range + 30:
                    self._attack_target(self.target, game)
                else:
                    self._attack_blank(game, self.target.x, self.target.y)
            else:
                tx = self.x + math.cos(self._face_angle) * 150
                ty = self.y + math.sin(self._face_angle) * 150
                self._attack_blank(game, tx, ty)
            self.attack_cd = self.attack_interval
            self.attack_anim = 1.0

        if self.target and self.target.alive:
            d = dist((self.x, self.y), (self.target.x, self.target.y))
            # 面朝目标
            self._face_angle = math.atan2(self.target.y - self.y, self.target.x - self.x)
            # 必须在攻击范围内才能打出普攻
            if d <= self.attack_range + 20 and self.attack_cd <= 0:
                self._attack_target(self.target, game)
                self.attack_cd = self.attack_interval
                self.attack_anim = 1.0
            if d <= self.attack_range:
                self.waypoints.clear()
            else:
                if not self.waypoints or dist(
                        (self.waypoints[0][0], self.waypoints[0][1]),
                        (self.target.x, self.target.y)) > 40:
                    self.waypoints = [(self.target.x, self.target.y)]
        else:
            self.target = None

        if self.waypoints:
            wx, wy = self.waypoints[0]
            self.move_toward(wx, wy, dt)
            if dist((self.x, self.y), (wx, wy)) < 10:
                self.waypoints.pop(0)

        # 玩家不自动索敌 — 只有点击敌人时才会设置 target
        if self.target and not self.target.alive:
            self.target = None

    # ========== 职业专属普攻 ==========

    def _attack_blank(self, game, target_x, target_y):
        """空挥普攻 — 朝面朝方向，纯视觉效果，不造成伤害"""
        ang = self._face_angle
        w = self.weapon
        r = self.attack_range + 20
        if w == 'sword':
            game.add_slash_effect(self.x, self.y, ang, 1.2, r * 0.6, '#c0c0d0')
            game.add_burst_effect(self.x + math.cos(ang) * r * 0.5,
                                  self.y + math.sin(ang) * r * 0.5, 18, '#d0d0e0', 3)
        elif w == 'mace':
            tip_x = self.x + math.cos(ang) * r
            tip_y = self.y + math.sin(ang) * r
            game.add_beam_effect(self.x, self.y, tip_x, tip_y, '#fdd835', 0.15)
            game.add_burst_effect(tip_x, tip_y, 20, '#fff176', 6, 0.1)
            game.add_aoe_effect(tip_x, tip_y, 14, '#fdd835', 0.1)
        elif w == 'claw':
            for i in range(3):
                a = ang + (i - 1) * 0.22
                game.add_slash_effect(self.x, self.y, a, 0.8, r * 0.35, '#81c784')
            game.add_burst_effect(self.x + math.cos(ang) * r * 0.5,
                                  self.y + math.sin(ang) * r * 0.5, 15, '#a5d6a7', 3)
        elif w == 'axe':
            game.add_slash_effect(self.x, self.y, ang, 1.5, r * 0.5, '#ff6d00')
            game.add_burst_effect(self.x + math.cos(ang) * r * 0.5,
                                  self.y + math.sin(ang) * r * 0.5, 22, '#ff8f00', 4)
        elif w == 'scythe':
            game.add_slash_effect(self.x, self.y, ang, 1.4, r * 0.5, '#9c27b0')
            game.add_aoe_effect(self.x + math.cos(ang) * r * 0.5,
                                self.y + math.sin(ang) * r * 0.5, 16, '#7b1fa2', 0.1)
        else:
            # 远程：朝面朝方向发射弹道
            color = '#00bcd4' if w == 'dagger' else self.body_color
            tx = self.x + math.cos(ang) * 200
            ty = self.y + math.sin(ang) * 200
            game.add_projectile(self.x, self.y, {'x': tx, 'y': ty, 'alive': True},
                                color, 400, 'hero',
                                {'straight': True, 'maxRange': self.attack_range + 30})

    def _attack_target(self, target, game):
        weapon_map = {
            'sword': lambda: self._atk_melee_cleave(target, game),
            'staff': lambda: self._atk_magic_bolt(target, game),
            'bow': lambda: self._atk_piercing(target, game),
            'dagger': lambda: self._atk_fast_dagger(target, game),
            'mace': lambda: self._atk_holy_light(target, game),
            'scythe': lambda: self._atk_dark_orb(target, game),
            'claw': lambda: self._atk_nature_bolt(target, game),
            'axe': lambda: self._atk_axe_throw(target, game),
        }
        fn = weapon_map.get(self.weapon)
        if fn:
            fn()

    # ---- 普攻类型 ----

    def _atk_melee_cleave(self, target, game):
        """战士 — 剑横扫 (朝面朝方向弧形斩击，碰撞检测)"""
        dmg = self._calc_dmg()
        ang = self._face_angle
        r = self.attack_range + 20
        half = 0.96  # 55° 半角
        for e in game.get_all_enemies(self.team):
            if not e.alive:
                continue
            d = dist((self.x, self.y), (e.x, e.y))
            if d > r:
                continue
            a = math.atan2(e.y - self.y, e.x - self.x)
            diff = abs(((a - ang + math.pi) % (2 * math.pi)) - math.pi)
            if diff < half:
                self._apply_dmg(e, dmg, game)
                e.knockback(math.cos(ang) * 120, math.sin(ang) * 40)

    def _atk_magic_bolt(self, target, game):
        """法师 — 魔法飞弹 (直线爆炸)"""
        dmg = self._calc_dmg()
        self._fire_straight(target, game, '#7c4dff', 380, 'staff', {
            'aoeRadius': 45, 'knockback': 80,
            'onHit': lambda e, owner, g: (
                self._apply_dmg(e, dmg, g),
                g.add_burst_effect(e.x, e.y, 30, '#7c4dff', 8, 0.2)
            )
        })

    def _atk_piercing(self, target, game):
        """射手 — 穿透箭"""
        dmg = self._calc_dmg() * 0.95
        self._fire_straight(target, game, '#ff8f00', 460, 'bow', {
            'pierce': 3, 'knockback': 40,
            'onHit': lambda e, owner, g: self._apply_dmg(e, dmg, g)
        })

    def _atk_fast_dagger(self, target, game):
        """刺客 — 飞刀 (流血)"""
        dmg = self._calc_dmg() * 0.9
        self._fire_straight(target, game, '#00bcd4', 500, 'dagger', {
            'pierce': 1, 'knockback': 30,
            'onHit': lambda e, owner, g: (
                self._apply_dmg(e, dmg, g),
                e.add_buff('poison', 2, {'dmgPct': 0.02}) if hasattr(e, 'add_buff') else None
            )
        })

    def _atk_holy_light(self, target, game):
        """圣骑士 — 锥刺 (朝面朝方向直线穿刺，碰撞检测) + 3击后横扫"""
        ang = self._face_angle
        r = self.attack_range + 20
        dx_dir = math.cos(ang)
        dy_dir = math.sin(ang)

        self._combo_count += 1
        self._combo_timer = 2.5
        is_sweep = self._combo_count >= 3

        if is_sweep:
            self._combo_count = 0
            dmg = int(self._calc_dmg() * 1.5)
            # 横扫 — 宽弧 80° 半角
            half = 1.4
            for e in game.get_all_enemies(self.team):
                if not e.alive:
                    continue
                d = dist((self.x, self.y), (e.x, e.y))
                if d > r:
                    continue
                a = math.atan2(e.y - self.y, e.x - self.x)
                diff = abs(((a - ang + math.pi) % (2 * math.pi)) - math.pi)
                if diff < half:
                    self._apply_dmg(e, dmg, game)
                    e.knockback(math.cos(a) * 220, math.sin(a) * 80)
            self.heal(int(dmg * 0.3))
            game.add_burst_effect(self.x, self.y, int(r * 0.7), '#fdd835', 14, 0.18)
            if self.is_player:
                game.add_floating_text(self.x, self.y - 30, '横扫!', False, '#fdd835')
        else:
            dmg = self._calc_dmg()
            # 直线穿刺 — 锥子沿攻击方向刺出，碰撞路径上的敌人
            end_x = self.x + dx_dir * r
            end_y = self.y + dy_dir * r
            hits = []
            for e in game.get_all_enemies(self.team):
                if not e.alive:
                    continue
                dex = e.x - self.x
                dey = e.y - self.y
                proj = dex * dx_dir + dey * dy_dir
                if 0 < proj < r:
                    perp = abs(-dex * dy_dir + dey * dx_dir)
                    if perp < 28:
                        hits.append((proj, e))
            hits.sort(key=lambda x: x[0])
            for _, e in hits[:2]:
                self._apply_dmg(e, dmg, game)
                e.knockback(dx_dir * 150, dy_dir * 50)
            self.heal(int(dmg * 0.2))

    def _atk_dark_orb(self, target, game):
        """死灵法师 — 暗影弹 (远程追踪，中毒+吸血)"""
        dmg = self._calc_dmg() * 1.05
        self._fire_straight(target, game, '#6a1b9a', 360, 'scythe', {
            'aoeRadius': 35, 'knockback': 50,
            'onHit': lambda e, owner, g: (
                owner._apply_dmg(e, dmg, g),
                e.add_buff('poison', 3, {'dmgPct': 0.03}) if hasattr(e, 'add_buff') else None,
                g.add_burst_effect(e.x, e.y, 25, '#9c27b0', 6, 0.15)
            )
        })

    def _atk_nature_bolt(self, target, game):
        """德鲁伊 — 爪击 (朝面朝方向横扫，碰撞检测，中毒减速)"""
        dmg = self._calc_dmg() * 0.9
        ang = self._face_angle
        r = self.attack_range + 20
        half = 0.87  # 50° 半角
        for e in game.get_all_enemies(self.team):
            if not e.alive:
                continue
            d = dist((self.x, self.y), (e.x, e.y))
            if d > r:
                continue
            a = math.atan2(e.y - self.y, e.x - self.x)
            diff = abs(((a - ang + math.pi) % (2 * math.pi)) - math.pi)
            if diff < half:
                self._apply_dmg(e, dmg, game)
                e.knockback(math.cos(ang) * 80, math.sin(ang) * 30)
                if hasattr(e, 'add_buff'):
                    e.add_buff('slow', 1.5, {'pct': 0.4})
                    e.add_buff('poison', 3, {'dmgPct': 0.025})

    def _atk_axe_throw(self, target, game):
        """狂战士 — 斧劈 (朝面朝方向重砍，碰撞检测，强击退+吸血)"""
        dmg = self._calc_dmg() * 1.15
        ang = self._face_angle
        r = self.attack_range + 20
        half = 0.79  # 45° 半角
        total_heal = 0
        for e in game.get_all_enemies(self.team):
            if not e.alive:
                continue
            d = dist((self.x, self.y), (e.x, e.y))
            if d > r:
                continue
            a = math.atan2(e.y - self.y, e.x - self.x)
            diff = abs(((a - ang + math.pi) % (2 * math.pi)) - math.pi)
            if diff < half:
                self._apply_dmg(e, dmg, game)
                e.knockback(math.cos(ang) * 180, math.sin(ang) * 60)
                total_heal += int(dmg * 0.15)
        self.heal(total_heal)

    # ---- 工具方法 ----

    def _calc_dmg(self):
        d = self.total_attack_dmg
        if self.has_crit and random.random() < self.crit_chance:
            d *= self.crit_mul
        return int(d)

    def _apply_dmg(self, target, dmg, game):
        dmg = int(dmg)
        target.take_damage(dmg, self)
        if self.life_steal_pct > 0:
            self.heal(int(dmg * self.life_steal_pct))
        if dmg > self.total_attack_dmg * 1.1 and hasattr(game, 'add_floating_text'):
            game.add_floating_text(target.x, target.y - 20, f'暴击! {dmg}', True, '#ff8f00')
        self._apply_item_effects(target, game)
        return True

    def _fire_straight(self, target, game, color, speed, wtype, opts):
        game.add_projectile(self.x, self.y, target, color, speed, 'hero', {
            'straight': True, 'weaponType': wtype, 'owner': self,
            'knockback': opts.get('knockback', 0),
            'pierce': opts.get('pierce', 1),
            'aoeRadius': opts.get('aoeRadius', 0),
            'onHit': opts.get('onHit', None),
            'maxRange': self.attack_range + 30,
        })

    def _apply_item_effects(self, target, game):
        for item in self.items:
            e = item['effect']
            if e['type'] == 'burn':
                target.add_buff('burn', e['dur'], {'dmgPct': e['dmgPct']})
            elif e['type'] == 'slow':
                target.add_buff('slow', e['dur'], {'pct': e['pct']})
            elif e['type'] == 'poison':
                target.add_buff('poison', e['dur'], {'dmgPct': e['dmgPct']})
            elif e['type'] == 'chain':
                enemies = [en for en in game.get_all_enemies(self.team)
                           if en.alive and en is not target
                           and dist((self.x, self.y), (en.x, en.y)) < 300]
                for i in range(min(e['targets'], len(enemies))):
                    enemies[i].take_damage(self.total_attack_dmg * e['dmgPct'], self)
                    game.add_projectile(target.x, target.y, enemies[i], '#ffeb3b', 350, 'chain')

    # ========== AI ==========

    def _update_ai(self, dt, game):
        is_llm = game.llm_ai and game.llm_ai.enabled and game.llm_ai.should_control_hero(self)

        if is_llm:
            game.llm_ai.apply_directive_to_hero(self, game)
            # LLM 已处理撤退（含 priority 调整），检查是否正在撤退
            directive = game.llm_ai.get_directive(self)
            # 更新头顶指令文字
            if directive:
                action = directive.get('action', '')
                reason = directive.get('reason', '')
                # 截断到最多10字
                text = f"{action}:{reason}" if reason else action
                self._llm_directive_text = text[:12]
            else:
                self._llm_directive_text = ''
            if directive:
                retreat_hp = directive.get('retreat_hp_pct', 0.2)
                priority = directive.get('priority', 'damage')
                if priority == 'survival':
                    retreat_hp = min(0.5, retreat_hp + 0.1)
                elif priority == 'damage':
                    retreat_hp = max(0.1, retreat_hp - 0.05)
                hp_pct = self.hp / self.max_hp if self.max_hp > 0 else 1.0
                if hp_pct < retreat_hp:
                    self.ai_state = 'retreat'
                # 撤退状态下：HP未回满(85%)前不出去
                if self.ai_state == 'retreat':
                    if hp_pct < 0.85:
                        if self.waypoints:
                            wx, wy = self.waypoints[0]
                            self.move_toward(wx, wy, dt)
                        return
                    else:
                        self.ai_state = 'idle'

        hp_pct = self.hp / self.max_hp
        if not is_llm and hp_pct < 0.2:
            rx = BLUE_BASE[0] if self.team == 'blue' else RED_BASE[0]
            self.move_toward(rx, LANES[self.lane_idx]['y'], dt)
            self.ai_state = 'retreat'
            return
        # 非LLM英雄撤退中：HP未回满(80%)前不出去
        if not is_llm and self.ai_state == 'retreat' and hp_pct < 0.8:
            rx = BLUE_BASE[0] if self.team == 'blue' else RED_BASE[0]
            self.move_toward(rx, LANES[self.lane_idx]['y'], dt)
            return
        if not is_llm and self.ai_state == 'retreat' and hp_pct >= 0.8:
            self.ai_state = 'idle'

        enemies = [e for e in game.get_all_enemies(self.team)
                   if e.alive and dist((self.x, self.y), (e.x, e.y)) < self.attack_range + 50]
        pt = None
        heroes = [e for e in enemies if hasattr(e, 'is_player')]
        if heroes:
            pt = min(heroes, key=lambda e: e.hp / e.max_hp)
        if not pt:
            ms = [e for e in enemies if hasattr(e, 'lane_y')
                  and abs(e.lane_y - LANES[self.lane_idx]['y']) < 60]
            if ms:
                pt = min(ms, key=lambda e: e.hp)
        if not pt:
            ts = [e for e in enemies if hasattr(e, 'tier')
                  and abs(e.lane_y - LANES[self.lane_idx]['y']) < 60]
            if ts:
                pt = ts[0]
        if not pt:
            cs = [e for e in enemies if e.__class__.__name__ == 'Crystal' and not e.shielded]
            if cs:
                pt = cs[0]
        if not pt:
            ns = [e for e in enemies if e.team == 'neutral']
            if ns:
                pt = min(ns, key=lambda e: e.hp)

        if pt and dist((self.x, self.y), (pt.x, pt.y)) < self.attack_range + 20:
            self.target = pt
            if self.attack_cd <= 0:
                self._attack_target(pt, game)
                self.attack_cd = self.attack_interval
                self.attack_anim = 1.0
            self._use_ai_abilities(game)
        else:
            # LLM 控制且有路点时，沿路点移动而非默认推线
            if is_llm and self.waypoints:
                wx, wy = self.waypoints[0]
                self.move_toward(wx, wy, dt)
                if dist((self.x, self.y), (wx, wy)) < 15:
                    self.waypoints.pop(0)
            elif not is_llm or not self.waypoints:
                self.target = None
                dx = RED_BASE[0] if self.team == 'blue' else BLUE_BASE[0]
                self.move_toward(dx, LANES[self.lane_idx]['y'] + rnd(-12, 12), dt)
            ce = [e for e in game.get_all_enemies(self.team)
                  if e.alive and dist((self.x, self.y), (e.x, e.y)) < 200]
            if ce:
                self._use_ai_abilities(game)

    def _use_ai_abilities(self, game):
        # LLM 控制时，由 LLM 指令决定技能使用
        if game.llm_ai and game.llm_ai.enabled and game.llm_ai.should_control_hero(self):
            self._use_llm_abilities(game)
            return
        # 原有硬编码逻辑
        ab = self.abilities
        nearby = [e for e in game.get_all_enemies(self.team)
                  if e.alive and dist((self.x, self.y), (e.x, e.y)) < 180]
        if self.hp / self.max_hp < 0.35 and 'e' in ab and ab['e']['cur_cd'] <= 0:
            self.use_ability('e', game)
            return
        if len(nearby) >= 3 and 'e' in ab and ab['e']['cur_cd'] <= 0:
            self.use_ability('e', game)
            return
        if len(nearby) >= 2 and 'w' in ab and ab['w']['cur_cd'] <= 0:
            self.use_ability('w', game)
            return
        eh = next((e for e in game.get_all_enemies(self.team)
                   if hasattr(e, 'is_player') and e.alive
                   and dist((self.x, self.y), (e.x, e.y)) < 250), None)
        if eh and 'q' in ab and ab['q']['cur_cd'] <= 0:
            self.use_ability('q', game)
            return

    def _use_llm_abilities(self, game):
        """LLM 控制的英雄技能使用 — 根据 LLM 指令的 abilities 字段"""
        for slot in ('q', 'w', 'e'):
            ab = self.abilities.get(slot)
            if not ab or ab['cur_cd'] > 0:
                continue
            should = game.llm_ai.should_use_ability(self, slot, game)
            if should:
                self.use_ability(slot, game)

    def _heal_near_crystal(self, dt, game):
        """在己方存活水晶附近时缓慢回血"""
        if self.hp >= self.max_hp:
            return
        from config import CRYSTAL_HEAL_RANGE, CRYSTAL_HEAL_RATE
        crystals = getattr(game, 'blue_crystals', []) if self.team == 'blue' else getattr(game, 'red_crystals', [])
        for c in crystals:
            if not c.alive:
                continue
            if dist((self.x, self.y), (c.x, c.y)) < CRYSTAL_HEAL_RANGE:
                heal = int(self.max_hp * CRYSTAL_HEAL_RATE * dt)
                self.heal(heal)
                break

    def _respawn(self, game):
        self.hp = self.max_hp
        self.alive = True
        self.death_timer = 0
        self.respawn_timer = 0
        d = 1 if self.team == 'blue' else -1
        base = BLUE_BASE if self.team == 'blue' else RED_BASE
        self.x = base[0] + d * 120
        self.y = LANES[self.lane_idx]['y']
        self.waypoints = [(self.x + d * 80, self.y)]
        self.target = None
        # 重新注册物理
        if hasattr(game, 'physics'):
            game.physics.register(self)
        if hasattr(game, 'add_ultimate_effect'):
            game.add_ultimate_effect(self.x, self.y, 60, self.body_color)
            game.add_floating_text(self.x, self.y - 40, '复活!', False, '#2ecc71')

    # ========== 渲染 ==========

    def render(self, surface, ox, oy):
        x, y = self.x + ox, self.y + oy
        if not self.alive:
            if self.death_timer < 1:
                a = int(255 * (1 - self.death_timer))
                self._render_body(surface, int(x), int(y), alpha=a)
            return

        self._render_body(surface, int(x), int(y))

    def _render_body(self, surface, x, y, alpha=255):
        bob = self.idle_bob
        moving = self.is_player and len(self.waypoints) > 0
        wp = self.walk_cycle if moving else 0
        leg_phase = math.sin(wp)

        d = 1 if math.cos(self._face_angle) >= 0 else -1
        if self.is_player and self.waypoints:
            dx = self.waypoints[0][0] - self.x
            if abs(dx) > 5:
                d = 1 if dx > 0 else -1
        elif not self.is_player:
            # AI/小兵: 根据实际移动方向决定朝向
            dx = self.x - self._prev_x
            if abs(dx) > 0.3:
                d = 1 if dx > 0 else -1

        bc = (255, 255, 255) if self.hit_flash > 0 else self.body_color
        hc = (255, 255, 255) if self.hit_flash > 0 else self.head_color
        lp = lambda p: (int(p[0]), int(p[1]))

        # 攻击范围圈 — 中心圆，仅玩家英雄
        if self.is_player and self.alive:
            pg.draw.circle(surface, (100, 140, 180, 22), (x, y), self.attack_range, 1)

        # ---- 动态底层（阴影） ----

        # 阴影（行走时随步频缩小放大）
        shadow_scale = 1 - abs(leg_phase) * 0.08 if moving else 1
        sw = int(30 * shadow_scale)
        pg.draw.ellipse(surface, (0, 0, 0), (x - sw // 2, y + 2, sw, 8))

        # ---- CACHED 身体基部（body rect + 盔甲 + 头 + 帽子） ----

        from systems.sprite_cache import get_cache
        cache = get_cache()
        body_surf = cache.get_hero_body(self.hero_type)
        head_r = 9 if self.hero_type in ('paladin', 'warrior', 'berserker') else 8
        body_top = head_r * 2 + 4  # 缓存 surface 中 body rect 的 top
        blit_y = int(y - 10 + bob - body_top)
        blit_x = x - body_surf.get_width() // 2
        surface.blit(body_surf, (blit_x, blit_y))
        # 命中闪白
        if self.hit_flash > 0:
            white = pg.Surface(body_surf.get_size(), pg.SRCALPHA)
            white.fill((255, 255, 255, 40))
            surface.blit(white, (blit_x, blit_y))

        # ---- 动态上层 ----

        # 腰胯 — 连接躯干与腿部（简洁填充，无边框）
        waist_w = 16
        waist_top = y + bob
        pg.draw.rect(surface, bc, (x - waist_w // 2, waist_top, waist_w, 5), border_radius=3)

        # 腿 — 粗线绘制，行走时有自然摆动
        leg_swing = leg_phase * 6
        leg_lift = abs(math.sin(wp * 1.2)) * 3 if moving else 0
        # 左腿
        hip_x_l = x - 5
        knee_x_l = hip_x_l + leg_swing * 0.4
        foot_x_l = hip_x_l + leg_swing
        hip_y = max(waist_top + 3, y + 3 + bob)
        knee_y_l = y + 12 + bob + leg_lift
        foot_y = y + 20 + bob
        # 腿 — 粗线绘制，无边框，简洁自然
        # 左腿
        pg.draw.line(surface, bc, (hip_x_l, hip_y), (knee_x_l, knee_y_l), 6)
        pg.draw.line(surface, bc, (knee_x_l, knee_y_l), (foot_x_l, foot_y), 4)
        # 脚
        shoe_c = (60, 50, 40) if bc[0] > 200 else (int(bc[0]*0.5), int(bc[1]*0.5), int(bc[2]*0.5))
        pg.draw.ellipse(surface, shoe_c, (foot_x_l - 4, foot_y, 8, 4))

        # 右腿（反向相位）
        hip_x_r = x + 5
        knee_x_r = hip_x_r - leg_swing * 0.4
        foot_x_r = hip_x_r - leg_swing
        knee_y_r = y + 12 + bob - leg_lift
        pg.draw.line(surface, bc, (hip_x_r, hip_y), (knee_x_r, knee_y_r), 6)
        pg.draw.line(surface, bc, (knee_x_r, knee_y_r), (foot_x_r, foot_y), 4)
        pg.draw.ellipse(surface, shoe_c, (foot_x_r - 4, foot_y, 8, 4))

        # 手臂 — 行走时自然摆动（与腿反向）
        is_casting = self.cast_anim > 0
        is_attacking = self.attack_anim > 0
        if moving and not is_casting and not is_attacking:
            # 行走摆臂：左臂与左腿反向
            walk_arm = -leg_phase * 5 * d
            arm_lift = 3 + abs(leg_phase) * 2  # 抬臂随步幅变化
        else:
            walk_arm = 0
            arm_lift = -14 if is_casting else (-10 if is_attacking else 2)
        arm_ang = d * 18 if is_casting else (d * 15 if is_attacking else walk_arm)

        # 左手（支撑臂，反向摆动）
        left_arm_extra = -walk_arm * 0.4 if moving and not is_casting and not is_attacking else 0
        pg.draw.line(surface, bc, (x - 8, y - 4 + bob),
                     (x - 15 + left_arm_extra, y + 2 + arm_lift + bob * 0.5), 3)
        # 右手（武器臂）
        pg.draw.line(surface, bc, (x + 8, y - 4 + bob),
                     (x + 16 + arm_ang, y - 4 + arm_lift + bob), 3)
        pg.draw.circle(surface, hc, (x + 16 + arm_ang, y - 4 + arm_lift + bob), 3)

        # 武器（全部动态，保持原样）
        self._render_weapon(surface, x, y, bob, d, arm_ang, arm_lift)

        # 眼睛（动态覆在缓存头部之上）
        eye_sq = 0.7 if self.attack_anim > 0.5 or self.cast_anim > 0.3 else 0
        eye_r = max(1, 2 - eye_sq * 0.3)
        pg.draw.circle(surface, (255, 255, 255), (x - 3 + d * 2, y - 20 + bob), eye_r)
        pg.draw.circle(surface, (255, 255, 255), (x + 3 + d * 2, y - 20 + bob), eye_r)
        pg.draw.circle(surface, (44, 62, 80), (x - 3 + d * 2 + d * 0.5, y - 20 + bob), 1)
        pg.draw.circle(surface, (44, 62, 80), (x + 3 + d * 2 + d * 0.5, y - 20 + bob), 1)

        # 职业图标
        icon_s = get_font(11).render(self.type_icon, True, (25, 35, 50))
        surface.blit(icon_s, (x - icon_s.get_width() / 2, y - 30 + bob))

        # 血条（自己绿 / 队友蓝 / 敌方红）
        bw, bh = 38, 5
        bx, by = x - bw / 2, y - 40 + bob
        pg.draw.rect(surface, (20, 20, 30), (bx - 1, by - 1, bw + 2, bh + 2), border_radius=2)
        pg.draw.rect(surface, (220, 220, 240), (bx - 1, by - 1, bw + 2, bh + 2), 1, border_radius=2)
        pct = max(0, self.hp / self.max_hp)
        if self.is_player:
            if pct > 0.5:
                hp_c = (46, 204, 113)
            elif pct > 0.25:
                hp_c = (39, 174, 96)
            else:
                hp_c = (30, 132, 73)
        elif self.team == 'blue':
            if pct > 0.5:
                hp_c = (52, 152, 219)
            elif pct > 0.25:
                hp_c = (41, 128, 185)
            else:
                hp_c = (28, 110, 164)
        else:
            if pct > 0.5:
                hp_c = (231, 76, 60)
            elif pct > 0.25:
                hp_c = (192, 57, 43)
            else:
                hp_c = (146, 43, 33)
        if pct > 0:
            pg.draw.rect(surface, hp_c, (bx + 1, by + 1, (bw - 2) * pct, bh - 2))

        # 经验条 — 所有英雄
        exp_bh = 2
        exp_by = by + bh + 3
        exp_pct = min(1, self.exp / self.max_exp)
        pg.draw.rect(surface, (30, 30, 40), (bx - 1, exp_by - 1, bw + 2, exp_bh + 2), border_radius=1)
        if exp_pct > 0:
            exp_c = (100, 150, 220) if self.is_player else (140, 140, 170)
            pg.draw.rect(surface, exp_c, (bx, exp_by, bw * exp_pct, exp_bh))

        # 护盾 / buff 光环
        if self.shield_active:
            pg.draw.circle(surface, (52, 152, 219), (x, y), self.radius + 5, 2)
        if self.is_shield_buffed:
            pg.draw.circle(surface, (253, 216, 53), (x, y), self.radius + 7, 2)
        if self.is_burning:
            pg.draw.circle(surface, (255, 87, 34), (x, y), self.radius + 6)
        if self.is_poisoned:
            pg.draw.circle(surface, (123, 31, 162), (x, y), self.radius + 6)

        # 等级
        lvl_s = get_font(10, bold=True).render(f'Lv{self.level}', True, (20, 30, 44))
        surface.blit(lvl_s, (x - lvl_s.get_width() / 2, by - 13))

        # 职业名
        type_s = get_font(10).render(self.type_name, True, (22, 32, 50))
        surface.blit(type_s, (x - type_s.get_width() / 2, by - 24))

        # LLM 指令文字（非玩家 + LLM 控制时显示）
        if not self.is_player and hasattr(self, '_llm_directive_text'):
            directive_s = get_font(10).render(self._llm_directive_text, True, (160, 160, 180))
            surface.blit(directive_s, (x - directive_s.get_width() / 2, by - 36))

        # 大招闪光
        if self.ult_flash > 0:
            flash_r = int(self.radius + 24 * self.ult_flash)
            flash_surf = pg.Surface((flash_r * 2 + 10, flash_r * 2 + 10), pg.SRCALPHA)
            pg.draw.circle(flash_surf, (255, 255, 200, int(self.ult_flash * 90)),
                           (flash_r + 5, flash_r + 5), flash_r)
            pg.draw.circle(flash_surf, (255, 255, 200, int(self.ult_flash * 90)),
                           (flash_r + 5, flash_r + 5), int(self.radius + 16 * self.ult_flash), 3)
            surface.blit(flash_surf, (x - flash_r - 5, y - flash_r - 5))

    def _render_weapon(self, surface, x, y, bob, d, arm_ang, arm_lift):
        atk = self.attack_anim
        cast = self.cast_anim
        w = self.weapon
        lp = lambda p: (int(p[0]), int(p[1]))

        if w == 'sword':
            ext = 10 if atk > 0 else 0
            sx, sy = x + 20 + arm_ang, y - 2 + bob
            ex, ey = x + 30 + arm_ang + d * ext, y - 15 + arm_lift * 0.5 + bob
            pg.draw.line(surface, (200, 200, 220), (sx, sy), (ex, ey), 2)
            pg.draw.line(surface, (100, 100, 120), (sx - 3, sy + 1), (sx + 3, sy - 1), 2)
            if atk > 0:
                pg.draw.circle(surface, (200, 220, 255), (int(ex + d * 4), int(ey)), int(6 + atk * 4))

        elif w == 'staff':
            pg.draw.line(surface, (138, 109, 255), (x + 18 + arm_ang, y - 4 + bob),
                         (x + 32 + arm_ang, y - 20 + bob), 2)
            sr = 7 + cast * 4 if cast > 0 else 3
            c = (255, 150, 50) if cast > 0 else (138, 109, 255)
            pg.draw.circle(surface, c, (x + 32 + arm_ang, y - 20 + bob), sr)

        elif w == 'bow':
            pg.draw.arc(surface, (196, 154, 108),
                        (x + 18 + arm_ang, y - 10 + bob, 14, 14), -1.0, 1.0, 2)
            pg.draw.line(surface, (196, 154, 108),
                         (x + 22 + arm_ang, y - 12 + bob), (x + 22 + arm_ang, y + 3 + bob), 1)
            if atk > 0:
                pg.draw.circle(surface, (255, 143, 0),
                               (int(x + 28 + arm_ang + d * 7), int(y - 6 + bob)), 4)

        elif w == 'dagger':
            ext = 8 if atk > 0 else 0
            pg.draw.line(surface, (77, 208, 225), (x + 18 + arm_ang, y - 2 + bob),
                         (x + 24 + arm_ang + d * ext, y - 10 + arm_lift * 0.5 + bob), 2)
            if atk > 0:
                pg.draw.circle(surface, (77, 208, 225),
                               (int(x + 24 + arm_ang + d * ext), int(y - 10 + bob)), 4)

        elif w == 'mace':
            # 大锥子 — 圣骑士武器，攻击时朝攻击方向刺出
            hx = x + 16 + arm_ang
            hy = y - 4 + arm_lift + bob
            # 锥柄
            handle_len = 8
            pg.draw.line(surface, (180, 150, 50), (hx, hy),
                         (hx + d * handle_len, hy - 2), 3)
            # 锥头三角形 — 攻击时伸长至攻击范围
            spike_len = 12 + atk * self.attack_range * 0.45
            base_x = hx + d * handle_len
            base_y = hy - 2
            tip_x = base_x + d * spike_len
            tip_y = base_y - 3
            pts = [
                (base_x, base_y - 6),
                (base_x, base_y + 6),
                (tip_x, tip_y),
            ]
            spike_c = (253, 216, 53) if atk > 0.2 else (200, 175, 55)
            pg.draw.polygon(surface, spike_c, [lp(p) for p in pts])
            # 锥尖高亮
            if atk > 0.3:
                pg.draw.circle(surface, (255, 255, 220), (int(tip_x), int(tip_y)), int(3 + atk * 5))
            if cast > 0:
                pg.draw.circle(surface, (255, 255, 150), (int(tip_x), int(tip_y)), 8)

        elif w == 'scythe':
            ext = 6 if atk > 0 else 0
            pg.draw.line(surface, (123, 31, 162), (x + 18 + arm_ang, y - 2 + bob),
                         (x + 26 + arm_ang + d * ext, y - 14 + arm_lift * 0.5 + bob), 2)
            pg.draw.arc(surface, (206, 147, 216),
                        (x + 22 + arm_ang + d * ext, y - 22 + bob, 16, 16), -2.2, 2.2, 2)

        elif w == 'claw':
            ext = 6 if atk > 0 else 0
            pg.draw.line(surface, (67, 160, 71), (x + 18 + arm_ang, y - 2 + bob),
                         (x + 24 + arm_ang + d * ext, y - 10 + arm_lift * 0.5 + bob), 2)
            for i in range(3):
                cx = x + 26 + arm_ang + d * ext + i * 3
                cy = y - 12 + arm_lift * 0.3 + bob + i * 2
                pg.draw.circle(surface, (129, 199, 132) if atk > 0 else (102, 187, 106), (cx, cy), 2)

        elif w == 'axe':
            ext = 8 if atk > 0 else 0
            pg.draw.line(surface, (230, 81, 0), (x + 18 + arm_ang, y - 2 + bob),
                         (x + 26 + arm_ang + d * ext, y - 12 + arm_lift * 0.5 + bob), 3)
            ax, ay = x + 28 + arm_ang + d * ext, y - 14 + arm_lift * 0.3 + bob
            pts = [(ax - 5, ay + 4), (ax + 5, ay + 4), (ax + 2, ay - 6), (ax - 2, ay - 6)]
            pg.draw.polygon(surface, (255, 109, 0), [lp(p) for p in pts])
            if atk > 0:
                pg.draw.circle(surface, (255, 109, 0), (int(ax + d * 4), int(ay - 2)), 6)