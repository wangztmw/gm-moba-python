"""物理系统 — 碰撞检测 / 重叠分离 / 惯性

管理实体之间的固态碰撞，阻止对象彼此穿透。
"""
import math

# 默认物理参数
DEFAULT_MASS = 1.0
BOUNCE = 0.15       # 碰撞回弹系数 (0=无弹, 1=完全弹性)
FRICTION_RATE = 8.0  # 每秒速度衰减率（越高越快停）
PUSH_FACTOR = 0.6   # 分离力推挤强度


class PhysicsSystem:
    """轻量 2D 物理引擎，圆形碰撞"""

    def __init__(self):
        self._entities = []  # 注册了物理的实体列表

    def register(self, entity):
        """将实体注册到物理系统"""
        if entity not in self._entities:
            self._entities.append(entity)

    def unregister(self, entity):
        if entity in self._entities:
            self._entities.remove(entity)

    def clear(self):
        self._entities.clear()

    @property
    def count(self):
        return len(self._entities)

    def update(self, dt):
        """主更新：处理所有实体之间的碰撞"""
        alive = [e for e in self._entities
                 if getattr(e, 'alive', True) and e.solid]
        n = len(alive)

        # 遍历所有配对，解决重叠
        for i in range(n):
            a = alive[i]
            for j in range(i + 1, n):
                b = alive[j]
                # 同队非英雄非玩家单位间不碰撞 (避免小兵堆挤)
                if a.team == b.team and not (
                    getattr(a, 'is_player', False) or getattr(b, 'is_player', False)
                ):
                    # 但英雄之间（包括AI）保持碰撞
                    if not (hasattr(a, 'hero_type') and hasattr(b, 'hero_type')):
                        continue

                self._resolve_pair(a, b, dt)

        # 速度衰减 + 位置更新（惯性）
        for e in self._entities:
            if not getattr(e, 'alive', True):
                continue
            if hasattr(e, 'apply_friction'):
                e.apply_friction(dt, FRICTION_RATE)
            elif hasattr(e, 'vx') and hasattr(e, 'vy'):
                decay = math.exp(-FRICTION_RATE * dt)
                e.vx *= decay
                e.vy *= decay
                if abs(e.vx) > 0.5 or abs(e.vy) > 0.5:
                    e.x += e.vx * dt
                    e.y += e.vy * dt

    def _resolve_pair(self, a, b, dt):
        """解析两个实体之间的碰撞"""
        dx = a.x - b.x
        dy = a.y - b.y
        dist = math.hypot(dx, dy)
        min_dist = (a.radius + b.radius) * 0.85  # 碰撞半径（稍微重叠允许）

        if dist >= min_dist or dist < 0.001:
            return

        # 归一化方向
        nx = dx / dist
        ny = dy / dist

        # 重叠量
        overlap = min_dist - dist

        # 质量
        mass_a = getattr(a, 'mass', DEFAULT_MASS)
        mass_b = getattr(b, 'mass', DEFAULT_MASS)
        total_mass = mass_a + mass_b

        # 质量加权分离
        push_a = overlap * (mass_b / total_mass) * PUSH_FACTOR
        push_b = overlap * (mass_a / total_mass) * PUSH_FACTOR

        a.x += nx * push_a
        a.y += ny * push_a
        b.x -= nx * push_b
        b.y -= ny * push_b

        # 回弹/惯性：给对方一个速度脉冲
        safe_dt = max(dt, 1.0 / 60)
        bounce_impulse = overlap * BOUNCE / safe_dt

        if hasattr(a, 'vx'):
            a.vx += nx * bounce_impulse * (mass_b / total_mass)
            a.vy += ny * bounce_impulse * (mass_b / total_mass)
        if hasattr(b, 'vx'):
            b.vx -= nx * bounce_impulse * (mass_a / total_mass)
            b.vy -= ny * bounce_impulse * (mass_a / total_mass)
