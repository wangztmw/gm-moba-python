"""小地图"""
import pygame as pg
from config import W, H


class Minimap:
    def __init__(self):
        self.w, self.h = 170, 100
        self.surf = pg.Surface((self.w, self.h))
        self.rect = pg.Rect(0, 0, self.w, self.h)

    def render(self, game, surface):
        mw, mh = self.w, self.h
        # 背景：浅绿色
        self.surf.fill((175, 200, 150))

        # 丛林区域（暗绿色斑块）
        from config import JUNGLE_CAMPS
        for cx, cy, _ in JUNGLE_CAMPS:
            jx = int(cx / game.cfg.W * mw)
            jy = int(cy / game.cfg.H * mh)
            pg.draw.circle(self.surf, (140, 175, 120), (jx, jy), 5)

        # 兵线（灰色道路，更粗）
        for lane in game.cfg.LANES:
            my = int(lane['y'] / game.cfg.H * mh)
            pg.draw.line(self.surf, (190, 180, 160), (0, my), (mw, my), 2)

        # 河流（蓝色带）
        rx = int((game.cfg.W // 2 - 22) / game.cfg.W * mw)
        rw = max(3, int(44 / game.cfg.W * mw))
        pg.draw.rect(self.surf, (85, 150, 195), (rx, 10, rw, mh - 20))

        # 基地标记
        from config import BLUE_BASE, RED_BASE
        bx = int(BLUE_BASE[0] / game.cfg.W * mw)
        by = int(BLUE_BASE[1] / game.cfg.H * mh)
        pg.draw.circle(self.surf, (30, 100, 200), (bx, by), 5)
        pg.draw.circle(self.surf, (60, 140, 230), (bx, by), 5, 1)
        rx = int(RED_BASE[0] / game.cfg.W * mw)
        ry = int(RED_BASE[1] / game.cfg.H * mh)
        pg.draw.circle(self.surf, (200, 45, 40), (rx, ry), 5)
        pg.draw.circle(self.surf, (230, 80, 75), (rx, ry), 5, 1)

        # 实体
        llm_heroes = set()
        if game.llm_ai and game.llm_ai.enabled:
            for e in game.entities:
                if hasattr(e, 'hero_type') and game.llm_ai.should_control_hero(e):
                    llm_heroes.add(id(e))

        for e in game.entities:
            if not e.alive and not (hasattr(e, 'tier') or e.__class__.__name__ == 'Crystal'):
                continue
            mx = int(e.x / game.cfg.W * mw)
            my = int(e.y / game.cfg.H * mh)

            if e.__class__.__name__ == 'Crystal':
                # 水晶：菱形
                if e.alive:
                    c = (52, 152, 219) if e.team == 'blue' else (231, 76, 60)
                else:
                    c = (100, 100, 100)
                r = 4
                pts = [(mx, my - r), (mx + r, my), (mx, my + r), (mx - r, my)]
                pg.draw.polygon(self.surf, c, pts)
                pg.draw.polygon(self.surf, (255, 255, 255), pts, 1)
            elif hasattr(e, 'tier'):
                # 防御塔：方形+边框
                if e.alive:
                    c = (41, 128, 185) if e.team == 'blue' else (192, 57, 43)
                    border_c = (80, 170, 240) if e.team == 'blue' else (240, 100, 90)
                else:
                    c = (150, 150, 150)
                    border_c = (120, 120, 120)
                s = 4
                pg.draw.rect(self.surf, c, (mx - s, my - s, s * 2, s * 2))
                pg.draw.rect(self.surf, border_c, (mx - s, my - s, s * 2, s * 2), 1)
            elif hasattr(e, 'is_player'):
                # 英雄：更大圆圈
                if e.is_player:
                    # 玩家英雄：黄色外圈高亮
                    pg.draw.circle(self.surf, (255, 235, 59), (mx, my), 5)
                    pg.draw.circle(self.surf, (255, 193, 7), (mx, my), 5, 1)
                    inner_c = (46, 204, 113) if e.team == 'blue' else (231, 76, 60)
                    pg.draw.circle(self.surf, inner_c, (mx, my), 3)
                else:
                    c = (46, 204, 113) if e.team == 'blue' else (231, 76, 60)
                    pg.draw.circle(self.surf, c, (mx, my), 3)
                    # LLM 控制英雄：小钻石标记
                    if id(e) in llm_heroes:
                        dm = 2
                        pts = [(mx, my - dm - 3), (mx + dm, my - 3),
                               (mx, my + dm - 3), (mx - dm, my - 3)]
                        pg.draw.polygon(self.surf, (100, 200, 255), pts)
            elif hasattr(e, 'lane_idx'):
                # 小兵：单像素
                c = (39, 174, 96) if e.team == 'blue' else (231, 76, 60)
                if 0 <= mx < mw and 0 <= my < mh:
                    self.surf.set_at((mx, my), c)
            elif e.team == 'neutral':
                # 野怪：小紫点
                pg.draw.circle(self.surf, (142, 68, 173), (mx, my), 2)

        # 视口框（加粗）
        vx = (game.camera.x - game.camera.view_w / 2) / game.cfg.W * mw
        vy = (game.camera.y - game.camera.view_h / 2) / game.cfg.H * mh
        vw = game.camera.view_w / game.cfg.W * mw
        vh = game.camera.view_h / game.cfg.H * mh
        pg.draw.rect(self.surf, (50, 60, 80), (vx, vy, vw, vh), 2)

        # 边框
        pg.draw.rect(self.surf, (80, 90, 110), (0, 0, mw, mh), 1)

        surface.blit(self.surf, (game.view_w - mw - 12, 12))
