"""野怪"""
import math
import pygame as pg
from .entity import Entity
from config import ITEMS, JUNGLE_RESPAWN
from utils import dist, rnd, rnd_int


class Monster(Entity):
    def __init__(self, x, y, mtype):
        stats = {
            'wolf': (800, 25, 0.8, 16),
            'golem': (1500, 40, 0.6, 24),
            'dragon': (3000, 60, 0.5, 32),
        }
        hp, atk, spd, r = stats.get(mtype, (1000, 30, 0.7, 20))
        super().__init__(x, y, hp, hp, 'neutral', r)
        self.type = mtype
        self.attack_dmg = atk
        self.attack_speed = spd
        self.attack_range = 50
        self.move_speed = 0
        self.respawn_time = JUNGLE_RESPAWN
        self.spawn_x, self.spawn_y = x, y
        self.body_sway = rnd(0, 6.28)
        # 物理
        self.mass = 5.0 if mtype == 'dragon' else (3.0 if mtype == 'golem' else 2.0)
        self.solid = True
        self.vx = 0.0
        self.vy = 0.0

    def update(self, dt, game):
        if not self.alive:
            return
        self.anim_time += dt
        self.body_sway += dt * 2
        self.hit_flash = max(0, self.hit_flash - dt * 4)
        self.update_effects()
        self.attack_cd = max(0, self.attack_cd - dt)

        enemies = [e for e in game.get_all_entities()
                   if e is not self and e.alive and e.team != 'neutral'
                   and dist((self.x, self.y), (e.x, e.y)) < self.attack_range + 40]
        target = enemies[0] if enemies else None
        if target:
            self.target = target
            if self.attack_cd <= 0:
                target.take_damage(self.attack_dmg, self)
                self.attack_cd = self.attack_interval
                game.add_projectile(self.x, self.y, target, '#ff7043', 280, 'monster')
        else:
            self.target = None

    def drop_loot(self):
        item = ITEMS[rnd_int(0, len(ITEMS) - 1)]
        return dict(**item)

    # ---- 渲染（缓存 body） ----

    def render(self, surface, ox, oy):
        if not self.alive:
            return
        x, y = int(self.x + ox), int(self.y + oy)
        sway = int(math.sin(self.body_sway) * 2)

        from systems.sprite_cache import get_cache
        cache = get_cache()
        body_surf = cache.get_monster(self.type)
        if body_surf is None:
            return

        # blit 缓存 body (surface 居中于 entity 位置)
        surf_w, surf_h = body_surf.get_width(), body_surf.get_height()
        surface.blit(body_surf, (x - surf_w // 2, y - surf_h // 2 + sway))

        # 命中闪白
        if self.hit_flash > 0:
            white_overlay = pg.Surface((surf_w, surf_h), pg.SRCALPHA)
            white_overlay.fill((255, 255, 255, 60))
            surface.blit(white_overlay, (x - surf_w // 2, y - surf_h // 2 + sway))

        # 动态部分（腿部动画、尾巴、翅膀等）
        if self.type == 'wolf':
            # 腿动画
            for i in range(4):
                lx = x - 8 + i * 8
                ly = y + 8 + sway
                pg.draw.line(surface, (120, 144, 156), (lx, ly),
                             (lx + math.sin(self.body_sway + i * 0.5) * 3, ly + 10), 3)
            # 尾巴摆动
            pg.draw.line(surface, (120, 144, 156), (x - 18, y + sway),
                         (x - 26, y - 6 + sway + math.sin(self.anim_time * 2) * 2), 2)
            self._render_hp_bar(surface, ox, oy, 24, 3.5, team='neutral')

        elif self.type == 'golem':
            # 发光
            pg.draw.circle(surface, (255, 235, 59), (x, y + sway), 30)
            self._render_hp_bar(surface, ox, oy, 28, 3.5, team='neutral')

        elif self.type == 'dragon':
            # 尾巴
            pg.draw.line(surface, (126, 87, 194), (x - 18, y + sway),
                         (x - 30, y - 6 + sway + math.sin(self.anim_time * 1.5) * 3), 5)
            pg.draw.line(surface, (126, 87, 194),
                         (x - 30, y - 6 + sway + math.sin(self.anim_time * 1.5) * 3),
                         (x - 38, y - 2 + sway + math.sin(self.anim_time * 1.5) * 4), 4)
            # 翅膀
            wing_c = (126, 87, 194, 128)
            pg.draw.polygon(surface, wing_c,
                            [(x - 10, y - 12 + sway), (x - 20, y - 40 + sway + math.sin(self.anim_time) * 6),
                             (x - 12, y - 32 + sway + math.sin(self.anim_time) * 4)])
            pg.draw.polygon(surface, wing_c,
                            [(x + 10, y - 12 + sway), (x + 20, y - 40 + sway - math.sin(self.anim_time) * 6),
                             (x + 12, y - 32 + sway - math.sin(self.anim_time) * 4)])
            # 火焰
            pg.draw.circle(surface, (255, 87, 34), (x + 30, y - 4 + sway), 5)
            self._render_hp_bar(surface, ox, oy, 36, 4, team='neutral')
