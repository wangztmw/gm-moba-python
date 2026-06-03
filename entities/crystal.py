"""基地水晶 — 攻击+回血光环+瞄准锁定+时间强化"""
import math
import pygame as pg
from utils import get_font, dist
from .entity import Entity


class Crystal(Entity):
    def __init__(self, x, y, team):
        super().__init__(x, y, 4000, 4000, team, 38)
        self.shielded = True
        self.anim_phase = 0.0
        # 攻击属性
        self.attack_dmg = 150
        self.attack_range = 260
        self.attack_speed = 0.5
        self.attack_cd = 0.0
        self.attack_target = None
        # 锁定目标机制
        self._focus_target = None
        self._focus_hits = 0
        # 回血光环
        self.heal_range = 200
        self.heal_pct = 0.03          # 每秒回复3%最大生命
        # 物理
        self.mass = 200.0
        self.solid = True

    def knockback(self, vx, vy):
        pass

    def apply_friction(self, dt, friction_rate=8.0):
        self.vx = 0.0
        self.vy = 0.0

    def check_shield(self, game):
        inner = [e for e in game.get_all_entities()
                 if e.__class__.__name__ == 'Tower'
                 and e.team == self.team and e.tier == 'inner' and e.alive]
        if not inner:
            self.shielded = False

    def take_damage(self, dmg, source=None):
        if self.shielded:
            return
        super().take_damage(dmg, source)
        if self.alive and self.hp < self.max_hp * 0.3:
            self.hit_flash = 1.0

    def update(self, dt, game):
        if not self.alive:
            return
        self.anim_time += dt
        self.anim_phase += dt * 2
        self.hit_flash = max(0, self.hit_flash - dt * 4)
        self.check_shield(game)

        # 攻击冷却
        self.attack_cd = max(0, self.attack_cd - dt)

        # ── 攻击逻辑 ──
        game_time = getattr(game, 'game_time', 0)
        time_scale = 1.0 + game_time / 180.0
        self.attack_target = None

        enemies = game.get_all_enemies(self.team)
        in_range = [e for e in enemies if e.alive
                    and dist((self.x, self.y), (e.x, e.y)) < self.attack_range]

        if in_range:
            # 优先攻击英雄
            target = next((e for e in in_range if hasattr(e, 'hero_type')), None)
            if not target:
                target = in_range[0]
            self.attack_target = target

            # 锁定目标逻辑：目标改变时重置连续攻击计数
            if target is not self._focus_target:
                self._focus_target = target
                self._focus_hits = 0

            if self.attack_cd <= 0:
                self._focus_hits += 1
                # 基础伤害 × 时间强化 × 连续攻击递增（每次+12%，最多叠10层）
                bonus = 1.0 + (self._focus_hits - 1) * 0.12
                dmg = self.attack_dmg * time_scale * min(bonus, 2.5)
                target.take_damage(dmg, self)
                # 减速效果 — 越塔时被减速
                if hasattr(target, 'add_buff'):
                    target.add_buff('slow', 1.5, {'pct': 0.3})
                # 追踪弹道 — 发射后必中
                game.add_projectile(self.x, self.y, target, '#ff5252', 400, 'tower')
                game.add_beam_effect(self.x, self.y, target.x, target.y, '#ff5252', 0.12)
                self.attack_cd = self.attack_interval
        else:
            self._focus_target = None
            self._focus_hits = 0

        # ── 回血光环 ──
        for e in game.get_all_entities():
            if not e.alive or e.team != self.team:
                continue
            if not hasattr(e, 'hp'):
                continue
            if dist((self.x, self.y), (e.x, e.y)) < self.heal_range:
                heal_amt = e.max_hp * self.heal_pct * dt
                e.heal(heal_amt)

    # ---- 渲染（缓存 body） ----

    def render(self, surface, ox, oy):
        x, y = int(self.x + ox), int(self.y + oy)
        bob = math.sin(self.anim_phase) * 3

        if not self.alive:
            pg.draw.circle(surface, (80, 80, 80), (x, y), 12)
            s = get_font(16).render('X', True, (200, 50, 50))
            surface.blit(s, (x - s.get_width() / 2, y - s.get_height() / 2))
            return

        from systems.sprite_cache import get_cache
        cache = get_cache()
        crys_surf = cache.get_crystal(self.team)
        surface.blit(crys_surf, (x - 40, y - 85 + int(bob)))

        vw = surface.get_width()
        vh = surface.get_height()

        # 仅在视口内时显示范围圈
        in_view = -self.heal_range < x < vw + self.heal_range and -self.heal_range < y < vh + self.heal_range
        if in_view:
            # 回血光环（淡绿色脉冲圆圈）
            heal_surf = pg.Surface((self.heal_range * 2, self.heal_range * 2), pg.SRCALPHA)
            pulse = int(25 + math.sin(self.anim_time * 2) * 10)
            pg.draw.circle(heal_surf, (100, 255, 100, pulse),
                           (self.heal_range, self.heal_range), self.heal_range, 2)
            surface.blit(heal_surf, (x - self.heal_range, y - self.heal_range + int(bob)))

            # 攻击范围圈（淡红色）
            atk_surf = pg.Surface((self.attack_range * 2, self.attack_range * 2), pg.SRCALPHA)
            pg.draw.circle(atk_surf, (255, 80, 80, 30),
                           (self.attack_range, self.attack_range), self.attack_range, 1)
            surface.blit(atk_surf, (x - self.attack_range, y - self.attack_range + int(bob)))

        # 攻击目标连线
        if self.attack_target and self.attack_target.alive:
            tx = int(self.attack_target.x + ox)
            ty = int(self.attack_target.y + oy)
            intensity = min(255, 80 + self._focus_hits * 25)
            line_surf = pg.Surface((abs(tx - x) + 20, abs(ty - y) + 20), pg.SRCALPHA)
            lx = min(x, tx) - 10
            ly = min(y, ty) - 10
            pg.draw.line(line_surf, (255, intensity, intensity, 150),
                         (x - lx, y - ly + int(bob)),
                         (tx - lx, ty - ly), 2)
            surface.blit(line_surf, (lx, ly))

        # 连续攻击层数
        if self._focus_hits > 0 and self._focus_target and self._focus_target.alive:
            hits_s = pg.font.SysFont(None, 16).render(f'×{self._focus_hits}', True, (255, 120, 120))
            surface.blit(hits_s, (x - hits_s.get_width() // 2, y - 95 + int(bob)))

        # 护盾
        if self.shielded:
            s = get_font(16).render('盾', True, (200, 200, 200, 180))
            surface.blit(s, (x - s.get_width() / 2, y + 50 + bob))
            pg.draw.circle(surface, (100, 200, 255), (x, y + int(bob)), 44, 2)

        # 低血量闪烁
        if self.hp < self.max_hp * 0.2 and math.sin(self.anim_time * 10) > 0:
            pg.draw.circle(surface, (255, 0, 0), (x, y + int(bob)), 40)

        # 血条
        self._render_hp_bar(surface, ox, oy, 44, 4, team=self.team)
