"""实体基类"""
import time
import math
import pygame as pg
from buff import Buff


class Entity:
    def __init__(self, x, y, hp, max_hp, team, radius=20):
        self.x, self.y = float(x), float(y)
        self.hp = hp
        self.max_hp = max_hp
        self.team = team          # 'blue' | 'red' | 'neutral'
        self.radius = radius
        self.alive = True
        self.death_processed = False
        self.target = None
        self.attack_cd = 0.0
        self.attack_speed = 1.0
        self.attack_dmg = 10
        self.attack_range = 150
        self.move_speed = 100
        self.buffs = []
        self.items = []
        self.last_shield_time = 0
        self.shield_active = False
        self.level = 1
        # 动画
        self.anim_time = 0.0
        self.attack_anim = 0.0
        self.hit_flash = 0.0
        # DOT 缓存
        self._has_dmg_buff = None
        # 物理属性
        self.mass = 1.0           # 质量，越大越难被推动
        self.vx = 0.0             # 速度 X (惯性)
        self.vy = 0.0             # 速度 Y (惯性)
        self.solid = False        # 是否参与物理碰撞

    # ---- 伤害/治疗 ----

    def take_damage(self, dmg, source=None):
        si = next((i for i in self.items if i['id'] == 'shield'), None)
        if si and self.shield_active:
            self.shield_active = False
            self.last_shield_time = time.time()
            return
        if self.is_shield_buffed:
            dmg *= 0.6
        ab = self.armor_break_pct
        if ab > 0:
            dmg = int(dmg * (1 + ab))
        self.hp -= dmg
        self.hit_flash = 1.0
        if self.hp <= 0 and self.alive:
            self.hp = 0
            self.alive = False
            self.death_processed = False

    def heal(self, amt):
        self.hp = min(self.max_hp, self.hp + amt)

    # ---- Buff ----

    def add_buff(self, btype, dur, data=None):
        self.buffs.append(Buff(btype, time.time() + dur, data))
        self._has_dmg_buff = None

    def update_effects(self):
        now = time.time()
        self.buffs = [b for b in self.buffs if not b.expired]
        self._has_dmg_buff = None
        si = next((i for i in self.items if i['id'] == 'shield'), None)
        if si and not self.shield_active and now - self.last_shield_time >= si['effect']['cd']:
            self.shield_active = True

    # ---- 属性 ----

    @property
    def attack_interval(self):
        base = self.attack_speed
        b = next((b for b in self.buffs if b.type == 'atk_speed_buff' and not b.expired), None)
        if b:
            base *= (1 + b.data.get('pct', 0))
        return max(0.3, 1.0 / base)

    def _buff_active(self, btype):
        return any(b.type == btype and not b.expired for b in self.buffs)

    @property
    def is_burning(self): return self._buff_active('burn')

    @property
    def is_slowed(self): return self._buff_active('slow')

    @property
    def is_poisoned(self): return self._buff_active('poison')

    @property
    def is_shield_buffed(self): return self._buff_active('shield_buff')

    @property
    def is_rooted(self): return self._buff_active('root')

    @property
    def armor_break_pct(self):
        b = next((b for b in self.buffs if b.type == 'armor_break' and not b.expired), None)
        return b.data.get('pct', 0.15) if b else 0

    @property
    def slow_pct(self):
        b = next((b for b in self.buffs if b.type == 'slow' and not b.expired), None)
        return b.data.get('pct', 0.5) if b else 0

    @property
    def has_crit(self): return any(i['id'] == 'crit' for i in self.items)

    @property
    def crit_chance(self):
        i = next((i for i in self.items if i['id'] == 'crit'), None)
        return i['effect']['chance'] if i else 0

    @property
    def crit_mul(self):
        i = next((i for i in self.items if i['id'] == 'crit'), None)
        return i['effect']['mul'] if i else 2

    @property
    def life_steal_pct(self):
        # 装备吸血 + buff吸血（取最大值）
        item_pct = 0
        i = next((i for i in self.items if i['id'] == 'vampire'), None)
        if i:
            item_pct = i['effect']['pct']
        buff_pct = 0
        b = next((b for b in self.buffs if b.type == 'lifesteal_buff' and not b.expired), None)
        if b:
            buff_pct = b.data.get('pct', 0)
        return max(item_pct, buff_pct)

    @property
    def extra_speed_pct(self):
        i = next((i for i in self.items if i['id'] == 'wind'), None)
        return i['effect']['pct'] if i else 0

    @property
    def berserk_active(self):
        i = next((i for i in self.items if i['id'] == 'berserk'), None)
        return i and (self.hp / self.max_hp) < i['effect']['threshold']

    @property
    def extra_dmg(self):
        i = next((i for i in self.items if i['id'] == 'holy'), None)
        return i['effect']['bonus'] if i else 0

    @property
    def total_attack_dmg(self):
        d = self.attack_dmg + self.extra_dmg
        if self.berserk_active:
            i = next(i for i in self.items if i['id'] == 'berserk')
            d = int(d * (1 + i['effect']['bonus']))
        return int(d)

    @property
    def effective_speed(self):
        s = self.move_speed * (1 + self.extra_speed_pct)
        if self.is_slowed:
            s *= (1 - self.slow_pct)
        return s

    # ---- 移动 ----

    def move_toward(self, tx, ty, dt):
        if self.is_rooted:
            return
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        if d < 2:
            return
        step = self.effective_speed * dt
        if step >= d:
            self.x, self.y = tx, ty
            return
        self.x += (dx / d) * step
        self.y += (dy / d) * step

    def knockback(self, vx, vy):
        """击退：给实体一个速度脉冲"""
        self.vx += vx
        self.vy += vy

    def apply_friction(self, dt, friction_rate=8.0):
        """物理衰减（dt 感知）— friction_rate 是每秒速度衰减比例"""
        if not self.vx and not self.vy:
            return
        decay = math.exp(-friction_rate * dt)
        self.vx *= decay
        self.vy *= decay
        if abs(self.vx) > 0.5 or abs(self.vy) > 0.5:
            self.x += self.vx * dt
            self.y += self.vy * dt
        else:
            self.vx = 0
            self.vy = 0

    def separate(self, others, min_dist, max_range=None):
        for other in others:
            if other is self or not other.alive:
                continue
            dx = self.x - other.x
            dy = self.y - other.y
            if max_range and (abs(dx) > max_range or abs(dy) > max_range):
                continue
            d = math.hypot(dx, dy)
            if d < min_dist and d > 0.1:
                force = (min_dist - d) / min_dist * 0.5
                self.x += (dx / d) * force
                self.y += (dy / d) * force

    # ---- 基础渲染 ----

    def render(self, surface, ox, oy):
        """默认渲染：画一个圆形代表实体"""
        x, y = int(self.x + ox), int(self.y + oy)
        color_map = {'blue': (52, 152, 219), 'red': (231, 76, 60), 'neutral': (142, 68, 173)}
        c = (200, 200, 200) if self.hit_flash > 0 else color_map.get(self.team, (200, 200, 200))
        pg.draw.circle(surface, c, (x, y), int(self.radius))
        self._render_hp_bar(surface, ox, oy)

    def _render_hp_bar(self, surface, ox, oy, bw=28, bh=4, team=None, is_player=False):
        x, y = self.x + ox, self.y + oy
        bx, by = x - bw / 2, y - self.radius - 14
        pct = max(0, self.hp / self.max_hp)
        # 背景
        pg.draw.rect(surface, (20, 20, 30), (bx - 1, by - 1, bw + 2, bh + 2), border_radius=2)
        pg.draw.rect(surface, (220, 220, 240), (bx - 1, by - 1, bw + 2, bh + 2), 1, border_radius=2)
        # 颜色细分
        if is_player:
            if pct > 0.5:
                c = (46, 204, 113)
            elif pct > 0.25:
                c = (39, 174, 96)
            else:
                c = (30, 132, 73)
        elif team == 'blue':
            if pct > 0.5:
                c = (52, 152, 219)
            elif pct > 0.25:
                c = (41, 128, 185)
            else:
                c = (28, 110, 164)
        elif team == 'red':
            if pct > 0.5:
                c = (231, 76, 60)
            elif pct > 0.25:
                c = (192, 57, 43)
            else:
                c = (146, 43, 33)
        else:
            if pct > 0.5:
                c = (243, 156, 18)
            elif pct > 0.25:
                c = (214, 137, 16)
            else:
                c = (183, 149, 11)
        if pct > 0:
            pg.draw.rect(surface, c, (bx + 1, by + 1, (bw - 2) * pct, bh - 2))
        # 低血量闪烁
        if pct < 0.25:
            flash = 0.3 + math.sin(self.anim_time * 6) * 0.2
            fl = pg.Surface((int((bw - 2) * pct), bh - 2), pg.SRCALPHA)
            fl.fill((255, 0, 0, int(flash * 255)))
            surface.blit(fl, (bx + 1, by + 1))
