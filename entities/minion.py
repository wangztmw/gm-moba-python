"""小兵"""
import math
import pygame as pg
from .entity import Entity
from config import LANES, BLUE_BASE, RED_BASE
from utils import dist, rnd


class Minion(Entity):
    def __init__(self, x, y, team, lane_idx, mtype,
                 scale_hp=1.0, scale_dmg=1.0, scale_spd=0):
        if mtype == 'super':
            hp, atk, spd, r = 1200, 40, 55, 18
            reward = 80
        elif mtype == 'melee':
            hp, atk, spd, r = 600, 20, 70, 14
            reward = 50
        else:
            hp, atk, spd, r = 350, 25, 65, 11
            reward = 35
        # 应用时间缩放
        hp = int(hp * scale_hp)
        atk = int(atk * scale_dmg)
        spd = spd + scale_spd
        super().__init__(x, y, hp, hp, team, r)
        self.type = mtype
        self.lane_idx = lane_idx
        self.attack_dmg = atk
        self.attack_range = 40 if mtype in ('melee', 'super') else 120
        self.attack_speed = 1.0
        self.move_speed = spd
        self.reward = reward
        self.lane_y = LANES[lane_idx]['y']
        self.walk_cycle = 0.0
        self._prev_x = x  # 用于判断行走朝向
        # 物理 — 轻量单位（不参与物理碰撞，避免被建筑卡住）
        self.mass = 1.0
        self.solid = False
        self.vx = 0.0
        self.vy = 0.0

    def update(self, dt, game):
        if not self.alive:
            return
        self.anim_time += dt
        self.walk_cycle += dt * 6
        self.hit_flash = max(0, self.hit_flash - dt * 4)
        self.update_effects()
        self.attack_cd = max(0, self.attack_cd - dt)

        enemies = game.get_all_enemies(self.team)
        nearby = [e for e in enemies if e.alive and (
            (hasattr(e, 'lane_y') and abs(e.lane_y - self.lane_y) < 80
             and dist((self.x, self.y), (e.x, e.y)) < self.attack_range + 30)
            or (not hasattr(e, 'lane_y')
                and dist((self.x, self.y), (e.x, e.y)) < self.attack_range)
        )]
        t = next((e for e in nearby if hasattr(e, 'lane_idx') and e is not self), None)
        if not t:
            t = next((e for e in nearby if hasattr(e, 'tier')), None)
        if not t:
            t = next((e for e in nearby if hasattr(e, 'is_player')), None)
        if not t:
            t = next((e for e in nearby if e.team == 'neutral'), None)

        if t and dist((self.x, self.y), (t.x, t.y)) <= self.attack_range + 10:
            self.target = t
            if self.attack_cd <= 0:
                self._attack(t, game)
                self.attack_cd = self.attack_interval
                self.attack_anim = 1.0
        else:
            self.target = None
            dest_x = RED_BASE[0] if self.team == 'blue' else BLUE_BASE[0]
            self.move_toward(dest_x, self.lane_y + rnd(-8, 8), dt)

        # 与同队小兵保持间距，防止聚集
        allies = [e for e in game.get_all_entities()
                  if e is not self and e.alive and e.team == self.team
                  and hasattr(e, 'lane_idx')]
        self.separate(allies, (self.radius + 14) * 0.85, 60)

        self.attack_anim = max(0, self.attack_anim - dt * 5)

        # 记录移动朝向
        if abs(self.x - self._prev_x) > 0.3:
            self._prev_x = self.x

    def _attack(self, target, game):
        dmg = self.total_attack_dmg
        ad = dmg
        if self.has_crit and rnd(0, 1) < self.crit_chance:
            ad = dmg * self.crit_mul

        # 攻击可见特效 + 伤害（区分近战/远程）
        if self.type in ('melee', 'super'):
            # 近战挥砍 — 小范围AOE，攻击范围内所有敌人
            ang = math.atan2(target.y - self.y, target.x - self.x)
            cleave_r = self.attack_range + 20
            for e in game.get_all_enemies(self.team):
                if not e.alive:
                    continue
                d = dist((self.x, self.y), (e.x, e.y))
                if d > cleave_r:
                    continue
                a = math.atan2(e.y - self.y, e.x - self.x)
                if abs(((a - ang + math.pi) % (2 * math.pi)) - math.pi) < 1.0:
                    e.take_damage(ad, self)
                    if self.life_steal_pct > 0:
                        self.heal(int(ad * self.life_steal_pct))
                    self._apply_item_effects(e, game)
            game.add_slash_effect(self.x, self.y, ang, 0.7, 30,
                                  '#ffa726' if self.team == 'blue' else '#ef5350', 0.08)
        else:
            # 远程弹道 — 射程限制
            target.take_damage(ad, self)
            if self.life_steal_pct > 0:
                self.heal(int(ad * self.life_steal_pct))
            self._apply_item_effects(target, game)
            color = '#ffeb3b' if self.team == 'blue' else '#ff5252'
            game.add_projectile(self.x, self.y, target, color, 280, 'minion_arrow',
                                {'owner': self, 'maxRange': self.attack_range + 30})

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
                self._do_chain(target, e, game)

    def _do_chain(self, target, effect, game):
        enemies = [en for en in game.get_all_enemies(self.team)
                   if en.alive and en is not target
                   and dist((self.x, self.y), (en.x, en.y)) < 300]
        for i in range(min(effect['targets'], len(enemies))):
            enemies[i].take_damage(self.total_attack_dmg * effect['dmgPct'], self)

    # ---- 渲染（缓存 body） ----

    def render(self, surface, ox, oy):
        if not self.alive:
            return
        x, y = int(self.x + ox), int(self.y + oy)
        tc = (66, 165, 245) if self.team == 'blue' else (239, 83, 80)
        bc = (255, 255, 255) if self.hit_flash > 0 else tc
        bob_y = int(math.sin(self.walk_cycle) * 2)
        if self.type == 'super':
            bw, bh = 22, 24
        elif self.type == 'melee':
            bw, bh = 18, 20
        else:
            bw, bh = 14, 16

        # 根据移动方向决定朝向
        dx = self.x - self._prev_x
        facing = 1 if dx >= -0.1 else -1

        from systems.sprite_cache import get_cache
        cache = get_cache()
        minion_surf = cache.get_minion(self.team, self.type)
        sw = bw + 14
        sh = bh + 16
        if facing < 0:
            minion_surf = pg.transform.flip(minion_surf, True, False)
        surface.blit(minion_surf, (x - sw // 2, y - sh // 2 + bob_y))

        # 命中闪烁覆盖
        if self.hit_flash > 0:
            pg.draw.rect(surface, (255, 255, 255),
                         (x - bw // 2, y - bh // 2 + bob_y, bw, bh),
                         border_radius=4)
            pg.draw.circle(surface, (255, 255, 255), (x, y - bh // 2 - 6 + bob_y), 5)

        # 腿（动态，随朝向翻转）
        leg_swing = math.sin(self.walk_cycle) * 4 * facing
        is_moving = abs(self.x - self._prev_x) > 0.1
        leg_off = leg_swing if is_moving else 0
        fx = facing
        pg.draw.line(surface, bc, (x - 4 * fx, y + bh // 2 + bob_y),
                     (x - 5 * fx + leg_off, y + bh // 2 + 10 + bob_y), 2)
        pg.draw.line(surface, bc, (x + 4 * fx, y + bh // 2 + bob_y),
                     (x + 5 * fx - leg_off, y + bh // 2 + 10 + bob_y), 2)

        # 武器（动态，随朝向翻转）
        wa = 0.6 if self.attack_anim > 0 else 0.2
        if self.type == 'melee':
            pg.draw.line(surface, (200, 200, 220),
                         (x + (bw // 2 + 2) * fx, y - 2 + bob_y),
                         (x + (bw // 2 + 10) * fx + int(self.attack_anim * 5) * fx,
                          y - 10 + int(wa * 10) + bob_y), 2)
        else:
            arc_x = x + (bw // 2 + 2) * fx - (5 if fx < 0 else 0)
            pg.draw.arc(surface, (200, 200, 220),
                        (arc_x, y - 8 + bob_y, 10, 10),
                        -0.8, 0.8, 1)
            pg.draw.line(surface, (200, 200, 220),
                         (x + (bw // 2 + 6) * fx, y - 7 + bob_y),
                         (x + (bw // 2 + 6) * fx, y + 3 + bob_y), 1)

        # 血条（动态）
        self._render_hp_bar(surface, ox, oy, 28, 4, team=self.team)

        # 燃烧特效（动态）
        if self.is_burning:
            pg.draw.circle(surface, (255, 87, 34),
                           (x, y), int(self.radius + 5), 2)


class MeleeMinion(Minion):
    pass


class RangedMinion(Minion):
    pass
