"""弹道/技能特效"""
import math
from utils import dist


class Projectile:
    def __init__(self, x, y, target, color, speed, ptype, extra=None):
        self.x, self.y = x, y
        self.target = target
        self.color = color
        self.speed = speed
        self.type = ptype
        self.extra = extra or {}
        self.alive = True
        self.trail = []
        self.max_age = 1.0
        # 物理属性
        self.knockback = self.extra.get('knockback', 0)
        self.pierce = self.extra.get('pierce', 1)
        self.aoe_radius = self.extra.get('aoeRadius', 0)
        self.straight = self.extra.get('straight', False)
        self.vx = self.extra.get('vx', 0)
        self.vy = self.extra.get('vy', 0)
        self.owner = self.extra.get('owner', None)
        self.hit_targets = []
        # 射程限制 — 超过此距离弹道消失
        self.origin_x = x
        self.origin_y = y
        self.max_range = self.extra.get('maxRange', 0)
        # 直线弹道预计算方向
        if self.straight and self.target:
            tx = self.target.x if hasattr(self.target, 'x') else self.target['x']
            ty = self.target.y if hasattr(self.target, 'y') else self.target['y']
            dx, dy = tx - self.x, ty - self.y
            d = math.hypot(dx, dy)
            if d > 0:
                self.vx = (dx / d) * self.speed
                self.vy = (dy / d) * self.speed

    def update(self, dt):
        if not self.alive:
            return
        self.max_age -= dt
        if self.max_age <= 0:
            self.alive = False
            return


        if self.type == 'slash':
            if 'startX' not in self.extra:
                self.extra['startX'] = self.x
                self.extra['life'] = self.extra.get('duration', 1.92)
                self.extra['maxLife'] = self.extra['life']
            self.extra['life'] -= dt
            if self.extra['life'] <= 0:
                self.alive = False
            return

        if self.type == 'beam':
            if 'startX' not in self.extra:
                self.extra['startX'] = self.x
                self.extra['life'] = self.extra.get('duration', 2.72)
                self.extra['maxLife'] = self.extra['life']
            self.extra['life'] -= dt
            if self.extra['life'] <= 0:
                self.alive = False
            return

        if self.type == 'burst_particle':
            if 'life' not in self.extra:
                self.extra['life'] = self.extra.get('duration', 3.0)
                self.extra['maxLife'] = self.extra['life']
            ang = self.extra.get('angle', 0)
            spd = self.extra.get('speed', 100)
            self.x += math.cos(ang) * spd * dt
            self.y += math.sin(ang) * spd * dt
            self.extra['life'] -= dt
            if self.extra['life'] <= 0:
                self.alive = False
            return

        if self.type == 'dash':
            if 'startX' not in self.extra:
                self.extra['startX'] = self.x
                self.extra['startY'] = self.y
                self.extra['life'] = 0.35
                self.extra['maxLife'] = 0.35
            self.extra['life'] -= dt
            if self.extra['life'] <= 0:
                self.alive = False
            return

        if self.type == 'aoe':
            if 'startX' not in self.extra:
                self.extra['startX'] = self.x
                self.extra['life'] = self.extra.get('duration', 2.28)
                self.extra['maxLife'] = self.extra['life']
            self.extra['life'] -= dt
            if self.extra['life'] <= 0:
                self.alive = False
            return

        # 直线弹道
        if self.straight:
            self.trail.append({'x': self.x, 'y': self.y, 'life': 0.12})
            self.x += self.vx * dt
            self.y += self.vy * dt
            if self.x < -100 or self.x > 3100 or self.y < -100 or self.y > 1900:
                self.alive = False
            # 射程限制
            if self.max_range > 0 and dist((self.origin_x, self.origin_y), (self.x, self.y)) > self.max_range:
                self.alive = False
        # 追踪弹道
        elif self.target:
            target_alive = getattr(self.target, 'alive', True)
            if not target_alive:
                self.alive = False
                return
            self.trail.append({'x': self.x, 'y': self.y, 'life': 0.12})
            tx = self.target.x if hasattr(self.target, 'x') else self.target['x']
            ty = self.target.y if hasattr(self.target, 'y') else self.target['y']
            dx = tx - self.x
            dy = ty - self.y
            d = math.hypot(dx, dy)
            step = self.speed * dt
            if step >= d:
                self.alive = False
                return
            self.x += (dx / d) * step
            self.y += (dy / d) * step
            # 射程限制
            if self.max_range > 0 and dist((self.origin_x, self.origin_y), (self.x, self.y)) > self.max_range:
                self.alive = False
        else:
            self.alive = False
            return

        self.trail = [t for t in self.trail if t['life'] > 0]
        for t in self.trail:
            t['life'] -= dt