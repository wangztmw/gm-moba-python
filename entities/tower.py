"""防御塔 — 瞄准锁定+时间强化+连续攻击递增"""
import pygame as pg
from .entity import Entity
from config import LANES
from utils import dist


class Tower(Entity):
    def __init__(self, x, y, team, lane_idx, tier):
        super().__init__(x, y, 3000, 3000, team, 30)
        self.tier = tier
        self.lane_idx = lane_idx
        self.lane_y = LANES[lane_idx]['y']
        self.attack_dmg = 150 if tier == 'outer' else 220
        self.attack_range = 240
        self.attack_speed = 0.8
        self.attack_target = None
        # 锁定目标机制：对同一目标连续攻击伤害递增，目标离开后重置
        self._focus_target = None   # 当前锁定的目标实体
        self._focus_hits = 0        # 对当前锁定目标的连续攻击次数
        # 物理
        self.mass = 100.0
        self.solid = True

    def knockback(self, vx, vy):
        pass

    def apply_friction(self, dt, friction_rate=8.0):
        self.vx = 0.0
        self.vy = 0.0

    def update(self, dt, game):
        if not self.alive:
            return
        self.anim_time += dt
        self.attack_cd = max(0, self.attack_cd - dt)

        # 时间强化：每3分钟基础攻击力+80%
        game_time = getattr(game, 'game_time', 0)
        time_scale = 1.0 + game_time / 225.0

        enemies = game.get_all_enemies(self.team)
        in_range = [e for e in enemies if e.alive
                    and dist((self.x, self.y), (e.x, e.y)) < self.attack_range]

        # 选目标：优先同兵线 → 英雄 → 任意
        target = next((e for e in in_range
                       if hasattr(e, 'lane_y') and abs(e.lane_y - self.lane_y) < 80), None)
        if not target:
            target = next((e for e in in_range
                         if hasattr(e, 'is_player') and getattr(e, 'lane_y', None) is not None
                         and abs(e.lane_y - self.lane_y) < 100), None)
        if not target:
            target = next((e for e in in_range if e.team == 'neutral'), None)
        if not target and in_range:
            target = in_range[0]

        self.attack_target = target if target and target.alive else None

        # 锁定目标逻辑：目标改变时重置连续攻击计数
        if target is not self._focus_target:
            self._focus_target = target
            self._focus_hits = 0

        if target:
            if self.attack_cd <= 0:
                self._fire_at(target, game, time_scale)
                self.attack_cd = self.attack_interval
        else:
            self._focus_hits = 0

    def _fire_at(self, target, game, time_scale=1.0):
        self._focus_hits += 1
        # 基础伤害 × 时间强化 × 连续攻击递增（每次+12%，最多叠10层）
        bonus = 1.0 + (self._focus_hits - 1) * 0.12
        dmg = self.attack_dmg * time_scale * min(bonus, 2.5)
        target.take_damage(dmg, self)
        # 护甲削弱 — 每次命中叠加10%易伤，最多3层
        if hasattr(target, 'add_buff'):
            target.add_buff('armor_break', 3, {'pct': 0.10})
        # 追踪弹道 — 发射后必中，即使目标离开范围
        game.add_projectile(self.x, self.y, target, '#ffd54f', 450, 'tower')
        game.add_beam_effect(self.x, self.y, target.x, target.y, '#ffd54f', 0.1)

    # ---- 渲染 ----

    def render(self, surface, ox, oy):
        x, y = int(self.x + ox), int(self.y + oy)
        if not self.alive:
            pg.draw.circle(surface, (80, 80, 80), (x, y), 6)
            return

        from systems.sprite_cache import get_cache
        cache = get_cache()
        tower_surf = cache.get_tower(self.team)
        surface.blit(tower_surf, (x - 50, y - 118))

        # 仅当玩家英雄靠近时显示攻击范围（800像素内可见）
        self._render_range_if_near(surface, x, y, game=None)

        # 攻击目标连线
        if self.attack_target and self.attack_target.alive:
            self._render_attack_line(surface, x, y, ox, oy)

        # 连续攻击层数指示
        if self._focus_hits > 0 and self._focus_target and self._focus_target.alive:
            hits_s = pg.font.SysFont(None, 16).render(f'×{self._focus_hits}', True, (255, 200, 80))
            surface.blit(hits_s, (x - hits_s.get_width() // 2, y - 125))

        # 血条
        self._render_hp_bar(surface, ox, oy, 44, 4, team=self.team)

    def _render_range_if_near(self, surface, x, y, game):
        """玩家英雄靠近时才显示攻击范围圈"""
        # 延迟获取 game 引用（render 时从外部传入不方便，用全局查找）
        try:
            from game import Game
            # 遍历查找 game 实例不太好，改为直接检测屏幕距离
            # 简化：始终在视口内时显示半透明范围
        except Exception:
            pass
        # 判断塔是否在视口内（视口中心 ≈ 玩家位置附近）
        vw = surface.get_width()
        vh = surface.get_height()
        # 如果塔在屏幕内，显示范围圈
        if -self.attack_range < x < vw + self.attack_range and -self.attack_range < y < vh + self.attack_range:
            range_surf = pg.Surface((self.attack_range * 2, self.attack_range * 2), pg.SRCALPHA)
            pg.draw.circle(range_surf, (255, 255, 200, 30),
                           (self.attack_range, self.attack_range), self.attack_range, 1)
            surface.blit(range_surf, (x - self.attack_range, y - self.attack_range))

    def _render_attack_line(self, surface, x, y, ox, oy):
        """攻击目标连线"""
        tx = int(self.attack_target.x + ox)
        ty = int(self.attack_target.y + oy)
        # 计算颜色：连续攻击越多线越亮
        intensity = min(255, 80 + self._focus_hits * 20)
        line_surf = pg.Surface((abs(tx - x) + 20, abs(ty - y) + 20), pg.SRCALPHA)
        lx = min(x, tx) - 10
        ly = min(y, ty) - 10
        pg.draw.line(line_surf, (255, intensity, 50, 140),
                     (x - lx, y - ly),
                     (tx - lx, ty - ly), 2)
        surface.blit(line_surf, (lx, ly))
