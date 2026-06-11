"""精灵缓存 — 预渲染静态元素为 Surface，避免每帧重复绘制

两种模式：
1. 磁盘模式（推荐）：从 assets/sprites/ 加载预生成的 PNG 文件，零 draw call
2. 构建模式：运行时用 pg.draw 绘制所有 Surface（首次或素材缺失时后备）

使用 bake_sprites.py 可生成所有 PNG 素材。
"""
import os
import math
import pygame as pg
from config import W, H, LANES, JUNGLE_CAMPS, BLUE_BASE, RED_BASE
from utils import get_font


def _get_sprite_dir():
    """assets/sprites/ 目录绝对路径（兼容 PyInstaller 打包）"""
    import sys
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后数据文件在 sys._MEIPASS 下
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'assets', 'sprites')


class SpriteCache:
    """预渲染并缓存所有静态游戏元素"""

    def __init__(self):
        self._surfaces = {}  # name -> pg.Surface

    def build_all(self):
        """构建所有缓存（启动时调用一次）"""
        self._build_map_bg()
        self._build_bushes()
        self._build_towers()
        self._build_crystals()
        self._build_hero_bodies()
        self._build_hero_weapons()
        self._build_minion_bodies()
        self._build_monster_bodies()
        self._build_projectile_bullet()
        self._build_loot_icons()

    def get(self, name):
        return self._surfaces.get(name)

    # ---- 地图背景 ----

    def _build_map_bg(self):
        """完整地图 (W×H) — 草地 / 石路兵线 / 河流 / 丛林 / 装饰"""
        import random as _rnd
        _rnd.seed(42)
        surf = pg.Surface((W, H))

        # ====== 1. 草地基底 + 自然色块（多层模拟 Perlin noise） ======
        grass_base = (148, 195, 118)
        surf.fill(grass_base)
        # 大块深浅斑块（低频）
        for _ in range(150):
            px, py = _rnd.randint(0, W), _rnd.randint(0, H)
            shade = _rnd.randint(-15, 15)
            r = _rnd.randint(60, 140)
            c = (max(0, min(255, grass_base[0] + shade)),
                 max(0, min(255, grass_base[1] + shade)),
                 max(0, min(255, grass_base[2] + shade)))
            pg.draw.circle(surf, c, (px, py), r)
        # 中等斑块（中频）
        for _ in range(400):
            px, py = _rnd.randint(0, W), _rnd.randint(0, H)
            shade = _rnd.randint(-12, 12)
            r = _rnd.randint(20, 50)
            c = (max(0, min(255, grass_base[0] + shade)),
                 max(0, min(255, grass_base[1] + shade)),
                 max(0, min(255, grass_base[2] + shade)))
            pg.draw.circle(surf, c, (px, py), r)
        # 细小纹理（高频）
        for _ in range(600):
            px, py = _rnd.randint(0, W), _rnd.randint(0, H)
            shade = _rnd.randint(-8, 8)
            r = _rnd.randint(5, 18)
            c = (max(0, min(255, grass_base[0] + shade)),
                 max(0, min(255, grass_base[1] + shade)),
                 max(0, min(255, grass_base[2] + shade)))
            pg.draw.circle(surf, c, (px, py), r)

        # ====== 2. 丛林暗绿色区域 ======
        jungle_color = (108, 155, 75)
        jungle_spots = [
            (280, 200, 70), (280, 400, 65), (280, 1400, 70), (280, 1600, 65),
            (500, 380, 80), (500, 1420, 80),
            (700, 200, 60), (700, 1600, 60),
            (1100, 380, 90), (1100, 1420, 90),
            (1500, 300, 75), (1500, 1500, 75),
            (1850, 400, 85), (1850, 1400, 85),
            (2100, 200, 70), (2100, 1600, 70),
            (2500, 350, 75), (2500, 1450, 75),
            (2700, 200, 65), (2700, 1600, 65),
        ]
        for jx, jy, jr in jungle_spots:
            pg.draw.circle(surf, jungle_color, (jx, jy), jr)
            pg.draw.circle(surf, (jungle_color[0]-15, jungle_color[1]-15, jungle_color[2]-10),
                           (jx, jy), jr, 2)

        # ====== 3. 农田式网格（细线） ======
        grid_c = (140, 185, 108)
        for x in range(0, W, 80):
            pg.draw.line(surf, grid_c, (x, 0), (x, H), 1)
        for y in range(0, H, 80):
            pg.draw.line(surf, grid_c, (0, y), (W, y), 1)

        # ====== 4. 三条石路兵线 ======
        lane_edge = (148, 135, 115)
        lane_fill = (198, 188, 165)
        lane_mid = (210, 202, 182)
        lane_center = (195, 187, 170)
        for lane in LANES:
            ly = lane['y']
            # 路基
            pg.draw.line(surf, lane_edge, (0, ly), (W, ly), 42)
            # 路面
            pg.draw.line(surf, lane_fill, (0, ly), (W, ly), 36)
            # 路面中线（虚线）
            for lx in range(0, W, 40):
                pg.draw.line(surf, lane_mid, (lx, ly - 2), (lx + 20, ly - 2), 3)
            # 路边石
            pg.draw.line(surf, lane_edge, (0, ly - 20), (W, ly - 20), 2)
            pg.draw.line(surf, lane_edge, (0, ly + 20), (W, ly + 20), 2)
            # 路面磨损纹理
            for _ in range(80):
                px = _rnd.randint(0, W)
                py = ly + _rnd.randint(-14, 14)
                pg.draw.circle(surf, lane_center, (px, py), _rnd.randint(1, 3))
            # 路名标签
            s = get_font(12).render(lane['name'], True, (100, 80, 60))
            surf.blit(s, (W // 2 - s.get_width() // 2, ly - 24))

        # ====== 5. 河流（微曲线 + 渐变 + 波纹） ======
        river_cx = W // 2
        river_w = 44
        water_c = (85, 150, 195)
        water_deep = (55, 110, 155)
        water_light = (115, 180, 220)
        bank_c = (120, 100, 70)
        # 河岸（微曲线）
        bank_pts_left = []
        bank_pts_right = []
        for ry in range(200, 1600, 8):
            # 微曲线偏移（正弦曲线模拟弯曲）
            curve = math.sin(ry / 300) * 15
            bank_pts_left.append((river_cx - river_w // 2 - 6 + curve, ry))
            bank_pts_right.append((river_cx + river_w // 2 + 6 + curve, ry))
        # 绘制河岸
        for i in range(len(bank_pts_left) - 1):
            pg.draw.line(surf, bank_c, bank_pts_left[i], bank_pts_left[i + 1], 8)
            pg.draw.line(surf, bank_c, bank_pts_right[i], bank_pts_right[i + 1], 8)
        # 绘制水面（微曲线+渐变效果）
        for ry in range(200, 1600, 2):
            curve = math.sin(ry / 300) * 15
            x_left = river_cx - river_w // 2 + curve
            x_right = river_cx + river_w // 2 + curve
            # 渐变色：中心深、边缘浅
            t = (ry - 200) / 1400
            depth_factor = 0.8 + 0.2 * math.sin(t * math.pi)
            wc = (int(water_c[0] * depth_factor + water_deep[0] * (1 - depth_factor)),
                  int(water_c[1] * depth_factor + water_deep[1] * (1 - depth_factor)),
                  int(water_c[2] * depth_factor + water_deep[2] * (1 - depth_factor)))
            pg.draw.line(surf, wc, (int(x_left), ry), (int(x_right), ry), 2)
        # 水面高光（微曲线）
        for ry in range(220, 1580, 30):
            curve = math.sin(ry / 300) * 15
            for rx_off in range(-river_w // 2 + 6, river_w // 2 - 6, 8):
                rx = river_cx + rx_off + curve
                offset = _rnd.randint(-2, 2)
                pg.draw.line(surf, water_light, (int(rx), ry + offset),
                             (int(rx + 4), ry + offset + _rnd.randint(-1, 1)), 1)
        # 水面边缘高光条
        for ry in range(200, 1600, 4):
            curve = math.sin(ry / 300) * 15
            hx = river_cx - river_w // 2 + 4 + curve
            pg.draw.line(surf, water_light, (int(hx), ry), (int(hx + 2), ry), 1)

        # ====== 6. 装饰：小石块、草簇 ======
        rock_c = (155, 148, 140)
        grass_tuft = (125, 170, 90)
        flower_c = [(235, 220, 100), (240, 170, 170), (210, 180, 240), (255, 230, 140)]
        for _ in range(300):
            px, py = _rnd.randint(0, W), _rnd.randint(0, H)
            # 避开道路和河流
            on_lane = any(abs(py - lane['y']) < 28 for lane in LANES)
            on_river = abs(px - W//2) < 30
            if on_lane or on_river:
                continue
            choice = _rnd.random()
            if choice < 0.45:
                # 小石块
                pg.draw.circle(surf, rock_c, (px, py), _rnd.randint(2, 5))
            elif choice < 0.75:
                # 草簇
                for _ in range(3):
                    gx = px + _rnd.randint(-3, 3)
                    gy = py + _rnd.randint(-2, 2)
                    pg.draw.line(surf, grass_tuft, (gx, gy), (gx, gy - _rnd.randint(3, 6)), 1)
            else:
                # 小花
                fc = _rnd.choice(flower_c)
                pg.draw.circle(surf, fc, (px, py), 2)
                pg.draw.circle(surf, (250, 250, 200), (px, py), 1)

        # ====== 环境装饰：蘑菇、树桩、水洼 ======
        # 蘑菇（丛林区域）
        for _ in range(30):
            mx = _rnd.randint(100, W - 100)
            my = _rnd.randint(100, H - 100)
            on_lane = any(abs(my - lane['y']) < 28 for lane in LANES)
            on_river = abs(mx - W // 2) < 40
            if on_lane or on_river:
                continue
            # 蘑菇柄
            pg.draw.rect(surf, (220, 210, 190), (mx - 1, my - 2, 3, 5))
            # 蘑菇帽
            mc = _rnd.choice([(180, 60, 60), (120, 80, 160), (200, 160, 50), (80, 140, 80)])
            pg.draw.ellipse(surf, mc, (mx - 4, my - 5, 9, 5))
            # 帽上白点
            if _rnd.random() < 0.5:
                pg.draw.circle(surf, (255, 255, 240), (mx + _rnd.randint(-2, 2), my - 4), 1)

        # 树桩（散落）
        for _ in range(15):
            sx = _rnd.randint(100, W - 100)
            sy = _rnd.randint(100, H - 100)
            on_lane = any(abs(sy - lane['y']) < 28 for lane in LANES)
            on_river = abs(sx - W // 2) < 40
            if on_lane or on_river:
                continue
            pg.draw.ellipse(surf, (110, 85, 55), (sx - 6, sy - 3, 12, 8))
            pg.draw.ellipse(surf, (130, 100, 65), (sx - 5, sy - 2, 10, 6))
            # 年轮
            pg.draw.ellipse(surf, (100, 75, 45), (sx - 3, sy - 1, 6, 3), 1)

        # 水洼（靠近河流的区域）
        for _ in range(8):
            wx = W // 2 + _rnd.randint(-80, 80)
            wy = _rnd.randint(300, 1500)
            on_lane = any(abs(wy - lane['y']) < 28 for lane in LANES)
            if on_lane:
                continue
            pg.draw.ellipse(surf, (100, 160, 200, 40) if isinstance(surf, pg.Surface) and surf.get_flags() & pg.SRCALPHA else (110, 165, 205),
                            (wx - 8, wy - 3, 16, 8))
            pg.draw.ellipse(surf, (130, 185, 220, 30) if isinstance(surf, pg.Surface) and surf.get_flags() & pg.SRCALPHA else (125, 180, 218),
                            (wx - 5, wy - 2, 10, 5))

        # ====== 7. 蓝色/红色 基地 ======
        for bx, by, team, bcolor, accent, glow_c in [
            (BLUE_BASE[0], BLUE_BASE[1], 'blue',
             (30, 120, 210), (60, 150, 235), (30, 100, 200)),
            (RED_BASE[0], RED_BASE[1], 'red',
             (200, 45, 40), (230, 80, 75), (200, 50, 40)),
        ]:
            # 发光边缘（外圈光晕）
            for r, a in [(110, 20), (100, 30), (92, 40)]:
                glow_surf = pg.Surface((r * 2, r * 2), pg.SRCALPHA)
                pg.draw.circle(glow_surf, (*glow_c, a), (r, r), r)
                surf.blit(glow_surf, (bx - r, by - r))
            # 脉冲圆环（静态模拟）
            for ring_r, ring_a in [(88, 25), (75, 18)]:
                ring_surf = pg.Surface((ring_r * 2 + 4, ring_r * 2 + 4), pg.SRCALPHA)
                pg.draw.circle(ring_surf, (*accent, ring_a), (ring_r + 2, ring_r + 2), ring_r, 2)
                surf.blit(ring_surf, (bx - ring_r - 2, by - ring_r - 2))
            # 外围石质地面
            pg.draw.circle(surf, (155, 148, 140), (bx, by), 95)
            pg.draw.circle(surf, (175, 168, 158), (bx, by), 85)
            # 石板缝
            for ang in range(0, 360, 30):
                rad = math.radians(ang)
                ex = bx + int(80 * math.cos(rad))
                ey = by + int(80 * math.sin(rad))
                pg.draw.line(surf, (150, 142, 135), (bx, by), (ex, ey), 1)
            # 内圈基地色
            pg.draw.circle(surf, bcolor, (bx, by), 55)
            pg.draw.circle(surf, accent, (bx, by), 55, 3)
            pg.draw.circle(surf, (255, 255, 255), (bx, by), 40, 1)
            # 中心徽记
            pg.draw.circle(surf, (255, 255, 255, 80) if isinstance(surf, pg.Surface) and surf.get_flags() & pg.SRCALPHA else (230, 230, 240),
                           (bx, by), 18)
            pg.draw.circle(surf, accent, (bx, by), 18, 2)
            # 名称
            name = '蓝方基地' if team == 'blue' else '红方基地'
            ns = get_font(12, bold=True).render(name, True, (255, 255, 255))
            surf.blit(ns, (bx - ns.get_width() // 2, by + 60))

        # ====== 8. 野怪营地标记 ======
        for cx, cy, mtype in JUNGLE_CAMPS:
            camp_c = (95, 140, 65) if 'wolf' in mtype else (
                     (120, 110, 85) if 'golem' in mtype else (130, 90, 140))
            pg.draw.circle(surf, camp_c, (int(cx), int(cy)), 58, 2)
            pg.draw.circle(surf, (*camp_c, 40), (int(cx), int(cy)), 50)

        # 转换为屏幕格式以加速 blit（消除每帧格式转换开销）
        try:
            surf = surf.convert()
        except pg.error:
            pass
        self._surfaces['map_bg'] = surf
        _rnd.seed()

    def get_map_bg(self):
        return self._surfaces['map_bg']

    # ---- 灌木 ----

    def _build_bushes(self):
        """灌木 / 树丛 / 岩石 — 合并到一张 SRCALPHA 上，带阴影"""
        import random as _rnd
        _rnd.seed(99)
        surf = pg.Surface((W, H), pg.SRCALPHA)
        bush_positions = [
            (200, 90), (200, 390), (200, 1390), (200, 1690),
            (400, 90), (400, 1690), (700, 90), (700, 1690),
            (1000, 90), (1000, 1690), (1600, 90), (1600, 1690),
            (2000, 90), (2000, 1690), (2300, 90), (2300, 1690),
            (2600, 90), (2600, 390), (2600, 1390), (2600, 1690),
            (350, 680), (350, 1080), (650, 680), (650, 1080),
            (950, 680), (950, 1080), (1550, 680), (1550, 1080),
            (1950, 680), (1950, 1080),
            # 额外丛林簇
            (400, 500), (400, 1300), (700, 500), (700, 1300),
            (1800, 500), (1800, 1300), (2200, 500), (2200, 1300),
        ]
        for bx, by in bush_positions:
            variant = _rnd.random()
            if variant < 0.4:
                # 圆形灌木丛（3-4团）
                for _ in range(_rnd.randint(3, 5)):
                    ox = bx + _rnd.randint(-8, 8)
                    oy = by + _rnd.randint(-6, 6)
                    r = _rnd.randint(8, 14)
                    pg.draw.circle(surf, (55, 110, 25, 180), (ox, oy), r)
                    pg.draw.circle(surf, (40, 90, 15, 140), (ox - 2, oy - 2), r - 2)
            elif variant < 0.7:
                # 树形（树干+树冠）
                # 阴影
                pg.draw.circle(surf, (0, 0, 0, 50), (bx + 2, by + 6), 16)
                # 树干
                pg.draw.rect(surf, (100, 70, 30, 200), (bx - 2, by, 4, 10))
                # 树冠（多层圆）
                pg.draw.circle(surf, (40, 90, 20, 190), (bx, by - 4), 14)
                pg.draw.circle(surf, (30, 70, 15, 170), (bx - 5, by - 1), 10)
                pg.draw.circle(surf, (30, 70, 15, 170), (bx + 4, by - 3), 9)
                pg.draw.circle(surf, (50, 110, 30, 140), (bx, by - 2), 8)
            else:
                # 岩石堆
                for _ in range(_rnd.randint(3, 6)):
                    ox = bx + _rnd.randint(-7, 7)
                    oy = by + _rnd.randint(-5, 5)
                    r = _rnd.randint(5, 10)
                    pg.draw.circle(surf, (120, 115, 108, 200), (ox, oy + 1), r)
                    pg.draw.circle(surf, (100, 95, 88, 180), (ox, oy), r - 1)
                    pg.draw.circle(surf, (140, 135, 128, 100), (ox - 1, oy - 1), r - 2)

        self._surfaces['bushes'] = surf
        _rnd.seed()

    def get_bushes(self):
        return self._surfaces['bushes']

    # ---- 防御塔 ----

    def _build_towers(self):
        import random as _rnd
        _rnd.seed(77)
        for team, base_c, mid_c, light_c, stone_c, trim_c, flag_c, glow_c in [
            ('blue',
             (25, 80, 160),     # 基色深蓝
             (40, 120, 210),    # 中色蓝
             (100, 180, 245),   # 亮蓝高光
             (90, 82, 72),      # 石材
             (200, 185, 140),   # 金饰
             (60, 140, 230),    # 旗帜
             (30, 100, 200, 80)),  # 窗光
            ('red',
             (170, 35, 30),     # 基色深红
             (210, 55, 50),     # 中色红
             (240, 120, 110),   # 亮红高光
             (90, 82, 72),      # 石材
             (200, 185, 140),   # 金饰
             (230, 80, 70),     # 旗帜
             (200, 50, 40, 80)),   # 窗光
        ]:
            # 100×130，中心 (50,118) 对应塔底
            surf = pg.Surface((100, 130), pg.SRCALPHA)
            cx, cy = 50, 118

            # ====== 地面阴影 ======
            pg.draw.ellipse(surf, (0, 0, 0, 70), (cx - 36, cy - 2, 72, 10))

            # ====== 第一层：宽大石砌地基（三层石板） ======
            # 最外层
            pg.draw.ellipse(surf, (65, 57, 50), (cx - 42, cy - 14, 84, 20))
            pg.draw.ellipse(surf, (75, 68, 60), (cx - 42, cy - 14, 84, 20), 1)
            # 砖石纹理
            for i in range(5):
                yy = cy - 12 + i * 4
                rx = 40 - i * 2
                ry = 8 - i
                pg.draw.ellipse(surf, (55, 48, 42), (cx - rx, yy, rx * 2, ry), 1)
            # 装饰石 — 团队色
            for ang in [0.3, 1.2, 2.0, 3.1, 4.0, 4.9, 5.8]:
                gx = cx + int(36 * math.cos(ang))
                gy = cy - 6 + int(8 * math.sin(ang))
                pg.draw.circle(surf, light_c, (gx, gy), 4)
                pg.draw.circle(surf, (255, 255, 255), (gx - 1, gy - 1), 1)
            # 放射状砖缝
            for ang in [0.15, 0.9, 1.65, 2.3, 3.2, 3.95, 4.7, 5.45, 6.1]:
                ex = cx + int(38 * math.cos(ang))
                ey = cy - 4 + int(9 * math.sin(ang))
                pg.draw.line(surf, (55, 48, 42), (cx, cy - 4), (ex, ey), 1)

            # 第二层：中层石台
            pg.draw.ellipse(surf, stone_c, (cx - 32, cy - 20, 64, 16))
            pg.draw.ellipse(surf, (110, 102, 95), (cx - 32, cy - 20, 64, 16), 1)
            # 砖块
            for i in range(10):
                ang = i * math.pi / 5 + _rnd.uniform(-0.1, 0.1)
                bx = cx + int(28 * math.cos(ang))
                by = cy - 14 + int(7 * math.sin(ang))
                pg.draw.rect(surf, (80, 73, 65), (bx - 4, by - 2, 8, 5))
                pg.draw.rect(surf, (105, 97, 88), (bx - 4, by - 2, 8, 5), 1)

            # ====== 魔能符文环（团队色） ======
            rune_r = 20
            pg.draw.ellipse(surf, base_c, (cx - rune_r, cy - 26, rune_r * 2, 10))
            pg.draw.ellipse(surf, trim_c, (cx - rune_r, cy - 26, rune_r * 2, 10), 1)
            # 符文小点
            for i in range(8):
                ang = i * math.pi / 4 + 0.2
                rx = cx + int((rune_r - 3) * math.cos(ang))
                ry = cy - 21 + int(4 * math.sin(ang))
                pg.draw.circle(surf, (255, 255, 200), (rx, ry), 2)
                pg.draw.circle(surf, light_c, (rx, ry), 1)

            # ====== 塔身（梯形砖石结构） ======
            body_bot = cy - 24
            body_top = cy - 58
            body_bot_w = 18
            body_top_w = 11
            pts = [(cx - body_bot_w, body_bot), (cx - body_top_w, body_top),
                   (cx + body_top_w, body_top), (cx + body_bot_w, body_bot)]
            pg.draw.polygon(surf, base_c, pts)
            pg.draw.polygon(surf, (255, 255, 255), pts, 1)
            # 水平砖缝
            for row in range(6):
                ry = body_bot - (row + 1) * 6
                prog = row / 5
                half_w = body_bot_w - prog * (body_bot_w - body_top_w) - 1
                pg.draw.line(surf, (base_c[0] // 3, base_c[1] // 3, base_c[2] // 3, 70),
                             (cx - half_w, ry), (cx + half_w, ry), 1)
            # 竖直中线
            pg.draw.line(surf, (255, 255, 255, 25), (cx, body_bot), (cx, body_top + 4), 1)

            # ====== 塔门（拱形） ======
            door_w, door_h = 8, 12
            door_x = cx - door_w // 2
            door_y = body_bot - door_h
            pg.draw.rect(surf, (30, 25, 20), (door_x, door_y, door_w, door_h))
            pg.draw.rect(surf, trim_c, (door_x, door_y, door_w, door_h), 1)
            # 拱形顶部
            door_arch_pts = [(door_x, door_y + 3), (door_x, door_y),
                             (cx, door_y - 3), (cx + door_w // 2, door_y),
                             (door_x + door_w, door_y + 3)]
            pg.draw.polygon(surf, trim_c, door_arch_pts, 1)

            # ====== 箭窗（发团队光） ======
            for sx in [-5, 5]:
                win_y = cy - 50
                pg.draw.rect(surf, (10, 10, 20), (cx + sx - 3, win_y, 6, 8))
                pg.draw.rect(surf, trim_c, (cx + sx - 3, win_y, 6, 8), 1)
                # 窗光
                pg.draw.rect(surf, (*glow_c[:3], 120), (cx + sx - 2, win_y + 1, 4, 3))
                pg.draw.rect(surf, (255, 255, 200, 150), (cx + sx - 1, win_y + 1, 2, 2))

            # ====== 团队色装饰腰带 ======
            belt_y = cy - 40
            belt_w = body_bot_w - 2 + (body_bot_w - body_top_w) * (body_bot - belt_y) / (body_bot - body_top)
            half_belt = int(belt_w)
            pg.draw.line(surf, light_c, (cx - half_belt, belt_y), (cx + half_belt, belt_y), 3)
            pg.draw.line(surf, trim_c, (cx - half_belt, belt_y), (cx + half_belt, belt_y), 1)

            # ====== 上层塔楼（带垛口） ======
            turret_bot = cy - 56
            turret_top = cy - 74
            turret_bot_w = 8
            turret_top_w = 5
            pts2 = [(cx - turret_bot_w, turret_bot), (cx - turret_top_w, turret_top),
                    (cx + turret_top_w, turret_top), (cx + turret_bot_w, turret_bot)]
            pg.draw.polygon(surf, mid_c, pts2)
            pg.draw.polygon(surf, (255, 255, 255), pts2, 1)
            # 垛口
            for i, sx in enumerate([-7, -3, 1, 5]):
                mx = cx + sx
                pg.draw.rect(surf, mid_c, (mx - 1, turret_bot - 4, 3, 5))
                pg.draw.rect(surf, trim_c, (mx - 1, turret_bot - 4, 3, 5), 1)
            # 塔楼腰线
            pg.draw.line(surf, trim_c, (cx - 7, turret_bot + 1), (cx + 7, turret_bot + 1), 1)
            # 塔楼窗
            pg.draw.rect(surf, (255, 213, 79, 120), (cx - 2, cy - 68, 4, 5))
            pg.draw.rect(surf, trim_c, (cx - 2, cy - 68, 4, 5), 1)
            pg.draw.rect(surf, (255, 240, 150, 160), (cx - 1, cy - 67, 2, 3))

            # ====== 尖顶 ======
            spire_base = turret_top
            spire_tip = cy - 94
            pts3 = [(cx - 5, spire_base), (cx, spire_tip), (cx + 5, spire_base)]
            pg.draw.polygon(surf, (140, 130, 150), pts3)
            pg.draw.polygon(surf, (175, 170, 185), pts3, 1)
            # 尖顶横纹
            for i in range(2):
                sy = spire_base - (i + 1) * 6
                half = 4 - i
                pg.draw.line(surf, (120, 110, 130), (cx - half, sy), (cx + half, sy), 1)

            # ====== 塔顶水晶 ======
            crys_y = cy - 82
            crys_pts = [(cx, crys_y - 8), (cx + 5, crys_y),
                        (cx, crys_y + 6), (cx - 5, crys_y)]
            pg.draw.polygon(surf, (255, 213, 79), crys_pts)
            pg.draw.polygon(surf, (255, 240, 180), crys_pts, 1)
            # 水晶高光
            crys_hl = [(cx - 2, crys_y - 2), (cx, crys_y - 5), (cx + 1, crys_y - 2)]
            pg.draw.polygon(surf, (255, 255, 255, 180), crys_hl)
            # 水晶光晕
            pg.draw.circle(surf, (255, 230, 100, 60), (cx, crys_y - 1), 10)
            pg.draw.circle(surf, (255, 240, 150, 30), (cx, crys_y - 1), 6)

            # ====== 旗帜（飘动效果） ======
            flag_x = cx + 10
            flag_base_y = cy - 80
            # 旗杆
            pg.draw.line(surf, (160, 155, 150), (flag_x, flag_base_y), (flag_x, flag_base_y - 16), 1)
            # 旗杆顶球
            pg.draw.circle(surf, trim_c, (flag_x, flag_base_y - 17), 2)
            # 旗帜
            flag_pts = [(flag_x, flag_base_y - 15),
                        (flag_x + 14, flag_base_y - 11),
                        (flag_x + 12, flag_base_y - 6),
                        (flag_x, flag_base_y - 4)]
            pg.draw.polygon(surf, flag_c, flag_pts)
            pg.draw.polygon(surf, (255, 255, 255), flag_pts, 1)
            # 旗上纹章
            pg.draw.circle(surf, (255, 255, 200), (flag_x + 6, flag_base_y - 10), 2)

            # ====== 装饰金边（塔身两侧） ======
            for side, sign in [(-1, -1), (1, 1)]:
                sx_base = cx + sign * (body_bot_w - 1)
                sx_top = cx + sign * (body_top_w - 1)
                pg.draw.line(surf, trim_c, (sx_base, body_bot), (sx_top, body_top), 1)

            self._surfaces[f'tower_{team}'] = surf
        _rnd.seed()

    def get_tower(self, team):
        return self._surfaces[f'tower_{team}']

    # ---- 水晶 ----

    def _build_crystals(self):
        import random as _rnd
        _rnd.seed(123)
        for team, tc, gc, light_c, glow_c, dark_c in [
            ('blue',
             (52, 152, 219),   # 主体蓝
             (100, 180, 240),  # 亮蓝
             (160, 220, 255),  # 高光白蓝
             (30, 100, 200, 80),  # 光晕
             (15, 60, 140)),   # 暗蓝
            ('red',
             (231, 76, 60),    # 主体红
             (245, 130, 110),  # 亮红
             (255, 180, 160),  # 高光粉
             (200, 50, 40, 80),   # 光晕
             (140, 25, 20)),   # 暗红
        ]:
            # 80×110，中心 (40,85) 对应实体 y
            surf = pg.Surface((80, 110), pg.SRCALPHA)
            cx, cy = 40, 85

            # ====== 地面光晕（多层） ======
            for i, (r, a) in enumerate([(52, 12), (44, 20), (34, 30), (24, 45)]):
                pg.draw.circle(surf, (*glow_c[:3], a), (cx, cy + 6), r)
            # 光晕外环
            pg.draw.circle(surf, (*light_c, 30), (cx, cy + 6), 48, 2)
            pg.draw.circle(surf, (*light_c, 15), (cx, cy + 6), 38, 1)

            # ====== 水晶基座（碎石） ======
            for i in range(5):
                ang = (i / 5) * math.pi * 2 + 0.3
                sx = cx + int(math.cos(ang) * 22)
                sy = cy + 8 + int(abs(math.sin(ang)) * 10)
                size = _rnd.randint(3, 7)
                shard_pts = [(sx, sy - size), (sx + size // 2, sy),
                             (sx, sy + size // 2), (sx - size // 2, sy)]
                pg.draw.polygon(surf, dark_c, shard_pts)
                pg.draw.polygon(surf, tc, shard_pts, 1)

            # ====== 底层大菱形 — 暗色轮廓 ======
            main_h = 48
            main_w = 22
            pts_main = [(cx, cy - main_h), (cx + main_w, cy - 4),
                        (cx, cy + main_h // 3), (cx - main_w, cy - 4)]
            pg.draw.polygon(surf, dark_c, pts_main)
            pg.draw.polygon(surf, tc, pts_main)
            # 主体高光边
            pg.draw.polygon(surf, light_c, pts_main, 1)

            # ====== 切割面 — 左/右斜面 ======
            # 左半切面（暗）
            left_half = [(cx, cy - main_h), (cx - main_w, cy - 4),
                         (cx, cy + main_h // 3)]
            pg.draw.polygon(surf, (*dark_c, 140), left_half)
            # 右半切面（亮）
            right_half = [(cx, cy - main_h), (cx + main_w, cy - 4),
                          (cx, cy + main_h // 3)]
            pg.draw.polygon(surf, (*light_c, 80), right_half)
            # 切面分界线
            pg.draw.line(surf, (*light_c, 120), (cx, cy - main_h), (cx, cy + main_h // 3), 1)

            # ====== 上层水晶（向前突出） ======
            top_h = main_h - 12
            top_w = main_w - 5
            top_cy = cy - 8
            pts_top = [(cx, top_cy - top_h), (cx + top_w, top_cy - 2),
                       (cx, top_cy + top_h // 3), (cx - top_w, top_cy - 2)]
            pg.draw.polygon(surf, gc, pts_top)
            pg.draw.polygon(surf, light_c, pts_top, 1)
            # 上层左斜面
            top_left = [(cx, top_cy - top_h), (cx - top_w, top_cy - 2), (cx, top_cy + top_h // 3)]
            pg.draw.polygon(surf, (*tc, 140), top_left)
            # 上层右斜面高光
            top_right = [(cx, top_cy - top_h), (cx + top_w, top_cy - 2), (cx, top_cy + top_h // 3)]
            pg.draw.polygon(surf, (*light_c, 100), top_right)

            # ====== 核心发光 ======
            core_r = 8
            for i, (r, a) in enumerate([(core_r + 8, 30), (core_r + 4, 50), (core_r, 80), (core_r - 2, 150)]):
                pg.draw.circle(surf, (*light_c, a), (cx, cy - main_h // 2), r)
            # 白热核心
            pg.draw.circle(surf, (255, 255, 255, 200), (cx, cy - main_h // 2), 3)
            pg.draw.circle(surf, (255, 255, 255, 100), (cx - 1, cy - main_h // 2 - 1), 1)

            # ====== 高光条纹（宝石质感） ======
            # 主高光 — 左上到中
            hl_pts = [(cx - 3, cy - main_h + 6), (cx - 1, cy - main_h // 2 + 4),
                      (cx + 2, cy - main_h // 2 + 4), (cx + 1, cy - main_h + 6)]
            pg.draw.polygon(surf, (255, 255, 255, 120), hl_pts)
            # 副高光 — 左下方小条
            hl2_pts = [(cx - 5, cy - main_h // 2 + 8), (cx - 3, cy - main_h // 2 + 14),
                       (cx, cy - main_h // 2 + 14), (cx - 2, cy - main_h // 2 + 8)]
            pg.draw.polygon(surf, (255, 255, 255, 70), hl2_pts)

            # ====== 浮空小晶片 ======
            for i in range(6):
                ang = (i / 6) * math.pi * 2 + _rnd.uniform(-0.2, 0.2)
                dist_out = 30 + _rnd.uniform(0, 8)
                fx = cx + int(math.cos(ang) * dist_out)
                fy = cy - main_h // 2 + int(math.sin(ang) * dist_out * 0.7)
                size = _rnd.randint(2, 5)
                spark_pts = [(fx, fy - size), (fx + size // 2, fy), (fx, fy + size // 2), (fx - size // 2, fy)]
                pg.draw.polygon(surf, (*light_c, 180), spark_pts)
                pg.draw.polygon(surf, (255, 255, 255, 140), spark_pts, 1)

            # ====== 上升光点 ======
            for i in range(8):
                px = cx + _rnd.randint(-30, 30)
                py = cy - _rnd.randint(5, 55)
                r = _rnd.randint(1, 2)
                pg.draw.circle(surf, (255, 255, 255, _rnd.randint(80, 200)), (px, py), r)

            # ====== 底环 ======
            pg.draw.ellipse(surf, tc, (cx - 24, cy - 3, 48, 8), 2)
            pg.draw.ellipse(surf, (*light_c, 80), (cx - 20, cy - 1, 40, 6), 1)

            self._surfaces[f'crystal_{team}'] = surf
        _rnd.seed()

    def get_crystal(self, team):
        return self._surfaces[f'crystal_{team}']

    # ---- 英雄身体基部 (不含武器 / 腿 / 动态效果) ----
    # 8 个职业各有独特造型，细节丰富

    def _build_hero_bodies(self):
        from config import HERO_TYPES
        for ht_id, ht in HERO_TYPES.items():
            bc = ht['bodyColor']
            hc = ht['headColor']
            bw, bh = (24, 22) if ht_id in ('paladin', 'warrior', 'berserker') else (20, 18)
            head_r = 9 if ht_id in ('paladin', 'warrior', 'berserker') else 8

            w = bw + 24
            h = bh + head_r * 2 + 14
            surf = pg.Surface((w, h), pg.SRCALPHA)
            cx = w // 2
            body_top = head_r * 2 + 4

            # ---------- 各职业独立绘制 ----------

            if ht_id == 'warrior':
                # 战士 — 红色重甲，银边，宽肩
                # 身体：红甲
                pg.draw.rect(surf, bc, (cx - bw // 2, body_top, bw, bh), border_radius=4)
                pg.draw.rect(surf, (180, 180, 200), (cx - bw // 2, body_top, bw, bh), 1, border_radius=4)
                # 肩甲
                pg.draw.circle(surf, (160, 160, 180), (cx - bw // 2 - 3, body_top + 4), 5)
                pg.draw.circle(surf, (160, 160, 180), (cx + bw // 2 + 3, body_top + 4), 5)
                # 胸甲中线
                pg.draw.line(surf, (200, 200, 220), (cx, body_top + 2), (cx, body_top + bh - 2), 2)
                # 腰带
                pg.draw.rect(surf, (120, 100, 80), (cx - bw // 2 + 1, body_top + bh - 4, bw - 2, 3))
                # 护颈
                pg.draw.rect(surf, (160, 160, 180), (cx - 5, body_top - 1, 10, 3))
                # 头 — 钢盔
                head_y = head_r + 2
                pg.draw.circle(surf, (160, 160, 180), (cx, head_y), head_r)
                pg.draw.circle(surf, bc, (cx, head_y), head_r - 1)
                # 面甲缝隙
                pg.draw.line(surf, (60, 60, 70), (cx - 3, head_y + 1), (cx + 3, head_y + 1), 1)
                # 盔缨
                pg.draw.polygon(surf, (200, 50, 50), [(cx - 2, head_y - head_r - 1),
                                                       (cx, head_y - head_r - 6),
                                                       (cx + 2, head_y - head_r - 1)])
                # 眼睛
                pg.draw.circle(surf, (60, 60, 80), (cx - 3, head_y - 1), 1)
                pg.draw.circle(surf, (60, 60, 80), (cx + 3, head_y - 1), 1)

            elif ht_id == 'mage':
                # 法师 — 紫袍，金边，星帽
                # 袍身：梯形
                robe_pts = [(cx - 8, body_top), (cx + 8, body_top),
                            (cx + 12, body_top + bh), (cx - 12, body_top + bh)]
                pg.draw.polygon(surf, bc, robe_pts)
                pg.draw.polygon(surf, (180, 160, 220), robe_pts, 1)
                # 金边
                pg.draw.line(surf, (200, 180, 50), (cx - 10, body_top + bh - 2), (cx + 10, body_top + bh - 2), 1)
                # 胸针/护符
                pg.draw.circle(surf, (100, 200, 255), (cx, body_top + 6), 3)
                pg.draw.circle(surf, (255, 255, 255), (cx - 1, body_top + 5), 1)
                # 领口
                pg.draw.line(surf, (180, 160, 220), (cx - 4, body_top), (cx, body_top + 3), 1)
                pg.draw.line(surf, (180, 160, 220), (cx + 4, body_top), (cx, body_top + 3), 1)
                # 头
                head_y = head_r + 2
                pg.draw.circle(surf, hc, (cx, head_y), head_r)
                # 法师帽
                pg.draw.polygon(surf, (80, 40, 160), [
                    (cx - 9, head_y - 2), (cx, head_y - 14), (cx + 9, head_y - 2)
                ])
                # 帽檐
                pg.draw.ellipse(surf, (60, 30, 140), (cx - 10, head_y - 3, 20, 5))
                # 星星
                pg.draw.circle(surf, (255, 220, 100), (cx, head_y - 12), 2)
                # 眼睛
                pg.draw.circle(surf, (40, 40, 60), (cx - 3, head_y), 1)
                pg.draw.circle(surf, (40, 40, 60), (cx + 3, head_y), 1)

            elif ht_id == 'archer':
                # 射手 — 绿色皮甲，兜帽，箭袋
                # 皮甲
                pg.draw.rect(surf, bc, (cx - bw // 2, body_top, bw, bh), border_radius=3)
                pg.draw.rect(surf, (150, 180, 100), (cx - bw // 2, body_top, bw, bh), 1, border_radius=3)
                # 皮带
                pg.draw.line(surf, (120, 80, 40), (cx - bw // 2, body_top + 4), (cx + bw // 2, body_top + 4), 2)
                pg.draw.line(surf, (120, 80, 40), (cx - bw // 2, body_top + bh - 2), (cx + bw // 2, body_top + bh - 2), 2)
                # 箭袋（背在右侧）
                pg.draw.rect(surf, (100, 60, 30), (cx + bw // 2 - 2, body_top - 2, 5, bh + 4))
                # 箭矢顶端
                for i in range(3):
                    px = cx + bw // 2 + 1
                    py = body_top - 2 + i * 5
                    pg.draw.line(surf, (180, 180, 180), (px, py), (px, py - 5), 1)
                # 护肩
                pg.draw.circle(surf, (130, 160, 90), (cx - bw // 2 - 2, body_top + 2), 4)
                # 兜帽头
                head_y = head_r + 2
                pg.draw.circle(surf, hc, (cx, head_y), head_r)
                # 兜帽
                pg.draw.polygon(surf, (60, 140, 60), [
                    (cx - 9, head_y - 6), (cx + 9, head_y - 6),
                    (cx + 10, head_y + 4), (cx - 10, head_y + 4)
                ], 1)
                # 面部
                pg.draw.circle(surf, (220, 190, 160), (cx, head_y), head_r - 1)
                # 眼睛
                pg.draw.circle(surf, (40, 60, 40), (cx - 3, head_y), 1)
                pg.draw.circle(surf, (40, 60, 40), (cx + 3, head_y), 1)
                # 耳朵
                pg.draw.circle(surf, (220, 190, 160), (cx - head_r - 1, head_y), 2)
                pg.draw.circle(surf, (220, 190, 160), (cx + head_r + 1, head_y), 2)

            elif ht_id == 'assassin':
                # 刺客 — 贴身黑衣，面罩
                # 紧身衣
                body_pts = [(cx - 7, body_top), (cx + 7, body_top),
                            (cx + 9, body_top + bh), (cx - 9, body_top + bh)]
                pg.draw.polygon(surf, bc, body_pts)
                # 皮甲背心
                vest_pts = [(cx - 5, body_top + 2), (cx + 5, body_top + 2),
                            (cx + 6, body_top + bh - 2), (cx - 6, body_top + bh - 2)]
                pg.draw.polygon(surf, (10, 30, 40), vest_pts)
                # 腰带 — 飞刀
                pg.draw.line(surf, (40, 40, 50), (cx - 8, body_top + bh - 3), (cx + 8, body_top + bh - 3), 2)
                for i in range(3):
                    dx = cx - 4 + i * 4
                    pg.draw.line(surf, (180, 180, 200), (dx, body_top + bh - 5), (dx, body_top + bh - 1), 1)
                # 护腕
                pg.draw.rect(surf, (10, 30, 40), (cx - 10, body_top + 3, 3, 6))
                pg.draw.rect(surf, (10, 30, 40), (cx + 7, body_top + 3, 3, 6))
                # 头 — 面罩
                head_y = head_r + 2
                pg.draw.circle(surf, hc, (cx, head_y), head_r)
                # 面罩（下半脸）
                pg.draw.rect(surf, bc, (cx - 7, head_y - 2, 14, head_r))
                # 眼睛（锐利）
                pg.draw.circle(surf, (200, 230, 240), (cx - 3, head_y - 2), 1)
                pg.draw.circle(surf, (200, 230, 240), (cx + 3, head_y - 2), 1)
                pg.draw.circle(surf, (0, 180, 200), (cx - 3, head_y - 2), 1)
                pg.draw.circle(surf, (0, 180, 200), (cx + 3, head_y - 2), 1)
                # 兜帽尖
                pg.draw.polygon(surf, bc, [(cx, head_y - head_r - 2), (cx - 1, head_y - head_r - 5),
                                           (cx + 1, head_y - head_r - 5)])

            elif ht_id == 'paladin':
                # 圣骑士 — 金色板甲，蓝披风，王冠
                # 板甲身体
                pg.draw.rect(surf, bc, (cx - bw // 2, body_top, bw, bh), border_radius=3)
                pg.draw.rect(surf, (180, 160, 60), (cx - bw // 2, body_top, bw, bh), 1, border_radius=3)
                # 板甲纹路
                pg.draw.line(surf, (160, 140, 40), (cx, body_top + 2), (cx, body_top + bh - 2), 1)
                for i in range(3):
                    y = body_top + 4 + i * 5
                    pg.draw.line(surf, (160, 140, 40), (cx - 4, y), (cx + 4, y), 1)
                # 肩甲
                pg.draw.ellipse(surf, (200, 180, 80), (cx - bw // 2 - 5, body_top - 1, 8, 8))
                pg.draw.ellipse(surf, (200, 180, 80), (cx + bw // 2 - 3, body_top - 1, 8, 8))
                # 圣光徽记（胸）
                pg.draw.circle(surf, (255, 230, 100), (cx, body_top + 8), 4)
                pg.draw.circle(surf, (255, 255, 200), (cx, body_top + 8), 2)
                # 披风（肩膀后方飘出）
                cape_pts = [(cx - 9, body_top), (cx + 9, body_top),
                            (cx + 12, body_top + bh + 2), (cx - 12, body_top + bh + 2)]
                pg.draw.polygon(surf, (40, 80, 160, 180), cape_pts)
                # 头 — 王冠
                head_y = head_r + 2
                pg.draw.circle(surf, (240, 220, 180), (cx, head_y), head_r)
                # 金发
                pg.draw.circle(surf, (200, 180, 100), (cx, head_y - 2), head_r + 1, 1)
                # 王冠
                pg.draw.polygon(surf, (200, 180, 60), [
                    (cx - 6, head_y - head_r - 1), (cx - 4, head_y - head_r - 5),
                    (cx - 1, head_y - head_r - 2), (cx + 1, head_y - head_r - 5),
                    (cx + 4, head_y - head_r - 2), (cx + 6, head_y - head_r - 1)
                ])
                # 眼睛
                pg.draw.circle(surf, (60, 80, 120), (cx - 3, head_y), 1)
                pg.draw.circle(surf, (60, 80, 120), (cx + 3, head_y), 1)

            elif ht_id == 'necromancer':
                # 死灵法师 — 暗紫破袍，骷髅肩饰
                # 破袍
                robe_pts = [(cx - 10, body_top), (cx + 10, body_top),
                            (cx + 8, body_top + bh), (cx - 8, body_top + bh)]
                pg.draw.polygon(surf, bc, robe_pts)
                # 破边
                pg.draw.line(surf, (80, 20, 60), (cx - 9, body_top + bh - 2), (cx + 9, body_top + bh - 2), 1)
                # 骷髅肩饰
                pg.draw.circle(surf, (200, 200, 210), (cx - bw // 2 - 3, body_top + 3), 4)
                pg.draw.circle(surf, (200, 200, 210), (cx + bw // 2 + 3, body_top + 3), 4)
                pg.draw.circle(surf, (40, 10, 30), (cx - bw // 2 - 3, body_top + 3), 1)
                pg.draw.circle(surf, (40, 10, 30), (cx + bw // 2 + 3, body_top + 3), 1)
                # 幽灵光晕
                pg.draw.circle(surf, (100, 50, 150, 40), (cx, body_top + bh // 2), 10)
                # 兜帽
                head_y = head_r + 2
                pg.draw.circle(surf, hc, (cx, head_y), head_r)
                # 暗黑兜帽
                hood_pts = [(cx - 9, head_y - head_r), (cx + 9, head_y - head_r),
                            (cx + 8, head_y + 4), (cx - 8, head_y + 4)]
                pg.draw.polygon(surf, (40, 10, 50), hood_pts)
                # 发光眼睛
                pg.draw.circle(surf, (100, 200, 100), (cx - 3, head_y), 2)
                pg.draw.circle(surf, (100, 200, 100), (cx + 3, head_y), 2)
                pg.draw.circle(surf, (200, 255, 200), (cx - 3, head_y), 1)
                pg.draw.circle(surf, (200, 255, 200), (cx + 3, head_y), 1)

            elif ht_id == 'druid':
                # 德鲁伊 — 皮毛装，鹿角，自然印记
                # 皮毛上衣
                pg.draw.rect(surf, bc, (cx - bw // 2, body_top, bw, bh), border_radius=4)
                pg.draw.rect(surf, (80, 120, 60), (cx - bw // 2, body_top, bw, bh), 1, border_radius=4)
                # 毛皮纹理
                for i in range(4):
                    y = body_top + 3 + i * 4
                    pg.draw.line(surf, (50, 100, 50), (cx - 6, y), (cx + 6, y), 1)
                # 自然印记（叶形）
                pg.draw.polygon(surf, (80, 200, 80), [
                    (cx, body_top + 2), (cx - 3, body_top + 6), (cx, body_top + 10), (cx + 3, body_top + 6)
                ])
                # 护肩（毛皮）
                pg.draw.circle(surf, (100, 70, 40), (cx - bw // 2 - 3, body_top + 3), 5)
                pg.draw.circle(surf, (100, 70, 40), (cx + bw // 2 + 3, body_top + 3), 5)
                # 头
                head_y = head_r + 2
                pg.draw.circle(surf, hc, (cx, head_y), head_r)
                # 长发
                pg.draw.polygon(surf, (80, 50, 30), [
                    (cx - 8, head_y + 2), (cx - 9, head_y - 2),
                    (cx - 6, head_y - 6), (cx + 6, head_y - 6),
                    (cx + 9, head_y - 2), (cx + 8, head_y + 2)
                ])
                # 鹿角
                for side, sign in [(-1, -1), (1, 1)]:
                    bx = cx + side * 7
                    pg.draw.line(surf, (120, 90, 60), (bx, head_y - 5), (bx + side * 5, head_y - 12), 2)
                    pg.draw.line(surf, (120, 90, 60), (bx + side * 2, head_y - 9), (bx + side * 5, head_y - 7), 1)
                # 眼睛
                pg.draw.circle(surf, (60, 80, 40), (cx - 3, head_y), 1)
                pg.draw.circle(surf, (60, 80, 40), (cx + 3, head_y), 1)

            elif ht_id == 'berserker':
                # 狂战士 — 赤膊，伤疤，兽皮，战纹
                # 身体（肌肉，不穿上衣 = skin tone base）
                pg.draw.rect(surf, (200, 160, 120), (cx - bw // 2, body_top, bw, bh), border_radius=4)
                # 伤疤
                pg.draw.line(surf, (160, 120, 80), (cx - 5, body_top + 4), (cx + 2, body_top + 8), 2)
                pg.draw.line(surf, (160, 120, 80), (cx + 4, body_top + 2), (cx - 1, body_top + 10), 1)
                # 战纹
                pg.draw.line(surf, (200, 50, 50), (cx - 6, body_top + 2), (cx - 2, body_top + 6), 1)
                pg.draw.line(surf, (200, 50, 50), (cx + 2, body_top + 6), (cx + 6, body_top + 2), 1)
                # 兽皮肩甲
                pg.draw.circle(surf, (120, 80, 40), (cx - bw // 2 - 4, body_top + 2), 6)
                pg.draw.circle(surf, (120, 80, 40), (cx + bw // 2 + 4, body_top + 2), 6)
                # 毛刺
                for _ in range(3):
                    pg.draw.line(surf, (160, 120, 80), (cx - bw // 2 - 5, body_top + 2),
                                 (cx - bw // 2 - 8, body_top - 2), 1)
                    pg.draw.line(surf, (160, 120, 80), (cx + bw // 2 + 5, body_top + 2),
                                 (cx + bw // 2 + 8, body_top - 2), 1)
                # 腰带（粗）
                pg.draw.rect(surf, (80, 50, 30), (cx - bw // 2 + 1, body_top + bh - 3, bw - 2, 4))
                # 头 — 狂野
                head_y = head_r + 2
                pg.draw.circle(surf, hc, (cx, head_y), head_r)
                # 乱发
                for i in range(5):
                    ang = -0.8 + i * 0.4
                    hx = cx + int(math.cos(ang) * (head_r + 2))
                    hy = head_y + int(math.sin(ang) * (head_r + 2))
                    pg.draw.line(surf, (180, 100, 0), (hx, hy), (hx + int(math.cos(ang - 0.3) * 4),
                                                                 hy + int(math.sin(ang - 0.3) * 4)), 2)
                # 战纹在脸上
                pg.draw.line(surf, (200, 50, 50), (cx - 4, head_y - 3), (cx + 4, head_y + 3), 1)
                # 怒眼
                pg.draw.circle(surf, (200, 60, 60), (cx - 3, head_y - 1), 2)
                pg.draw.circle(surf, (200, 60, 60), (cx + 3, head_y - 1), 2)
                pg.draw.circle(surf, (255, 200, 50), (cx - 3, head_y - 1), 1)
                pg.draw.circle(surf, (255, 200, 50), (cx + 3, head_y - 1), 1)

            else:
                # 后备 — 通用简化版
                body_rect = (cx - bw // 2, body_top, bw, bh)
                pg.draw.rect(surf, bc, body_rect, border_radius=6)
                pg.draw.rect(surf, (255, 255, 255), body_rect, 1, border_radius=6)
                head_y = head_r + 2
                pg.draw.circle(surf, hc, (cx, head_y), head_r)

            self._surfaces[f'hero_body_{ht_id}'] = surf

    def get_hero_body(self, hero_type):
        return self._surfaces[f'hero_body_{hero_type}']

    def get_hero_body_size(self, hero_type):
        s = self._surfaces[f'hero_body_{hero_type}']
        return s.get_width(), s.get_height()

    # ---- 武器 ----

    def _build_hero_weapons(self):
        weapons = {
            'sword': ((200, 200, 220), (100, 100, 120)),
            'staff': ((138, 109, 255), None),
            'bow': ((196, 154, 108), None),
            'dagger': ((77, 208, 225), None),
            'mace': ((249, 168, 37), (253, 216, 53)),
            'scythe': ((123, 31, 162), (206, 147, 216)),
            'claw': ((67, 160, 71), (129, 199, 132)),
            'axe': ((230, 81, 0), (255, 109, 0)),
        }
        for wname, (c1, c2) in weapons.items():
            surf = pg.Surface((36, 36), pg.SRCALPHA)
            if wname == 'sword':
                pg.draw.line(surf, c1, (20, 2), (30, 16), 2)
                pg.draw.line(surf, c2 or c1, (17, 6), (25, 4), 2)
            elif wname == 'staff':
                pg.draw.line(surf, c1, (18, 4), (30, 24), 2)
                pg.draw.circle(surf, (255, 150, 50), (30, 24), 4)
            elif wname == 'bow':
                pg.draw.arc(surf, c1, (18, 2, 16, 16), -1.0, 1.0, 2)
                pg.draw.line(surf, c1, (24, 0), (24, 18), 1)
            elif wname == 'dagger':
                pg.draw.line(surf, c1, (18, 2), (26, 16), 2)
            elif wname == 'mace':
                pg.draw.line(surf, c1, (18, 2), (24, 12), 2)
                pg.draw.circle(surf, c2 or c1, (26, 16), 6)
            elif wname == 'scythe':
                pg.draw.line(surf, c1, (18, 2), (26, 18), 2)
                pg.draw.arc(surf, c2 or c1, (20, -4, 18, 18), -2.2, 2.2, 2)
            elif wname == 'claw':
                pg.draw.line(surf, c1, (18, 2), (24, 14), 2)
                for i in range(3):
                    pg.draw.circle(surf, c2 or c1, (26 + i * 3, 10 + i * 2), 2)
            elif wname == 'axe':
                pg.draw.line(surf, c1, (18, 2), (26, 14), 3)
                pts = [(28, 22), (34, 22), (32, 12), (30, 12)]
                pg.draw.polygon(surf, c2 or c1, pts)
            self._surfaces[f'weapon_{wname}'] = surf

    def get_weapon(self, wname):
        return self._surfaces[f'weapon_{wname}']

    # ---- 小兵 ----

    def _build_minion_bodies(self):
        for team, tc in [('blue', (66, 165, 245)), ('red', (239, 83, 80))]:
            for mtype in ('melee', 'ranged', 'super'):
                if mtype == 'super':
                    bw, bh = 22, 24
                elif mtype == 'melee':
                    bw, bh = 18, 20
                else:
                    bw, bh = 14, 16
                surf = pg.Surface((bw + 14, bh + 16), pg.SRCALPHA)
                cx = (bw + 14) // 2
                body_y = 10
                # 身体
                body_rect = (cx - bw // 2, body_y, bw, bh)
                pg.draw.rect(surf, tc, body_rect, border_radius=3)
                pg.draw.rect(surf, (255, 255, 255), body_rect, 1, border_radius=3)
                # 胸甲纹路
                pg.draw.line(surf, (255, 255, 255, 80), (cx, body_y + 2), (cx, body_y + bh - 2), 1)
                # 腰带
                pg.draw.rect(surf, (80, 60, 40), (cx - bw // 2 + 1, body_y + bh - 4, bw - 2, 3))
                if mtype == 'super':
                    # 超级兵：大圆盾 + 金边 + 重盔
                    pg.draw.circle(surf, (200, 180, 50), (cx - bw // 2 - 3, body_y + 5), 6)
                    pg.draw.circle(surf, (220, 200, 80), (cx - bw // 2 - 3, body_y + 5), 4)
                    # 金边重盔
                    pg.draw.circle(surf, (200, 180, 50), (cx, 5), 8)
                    pg.draw.circle(surf, tc, (cx, 5), 6)
                    # 面甲
                    pg.draw.line(surf, (255, 200, 50), (cx - 3, 6), (cx + 3, 6), 2)
                    # 肩甲
                    pg.draw.circle(surf, (200, 180, 50), (cx - bw // 2 - 4, body_y + 2), 4)
                    pg.draw.circle(surf, (200, 180, 50), (cx + bw // 2 + 4, body_y + 2), 4)
                elif mtype == 'melee':
                    # 近战：小圆盾
                    pg.draw.circle(surf, (180, 180, 190), (cx - bw // 2 - 3, body_y + 5), 5)
                    pg.draw.circle(surf, (200, 200, 210), (cx - bw // 2 - 3, body_y + 5), 3)
                    # 头盔
                    pg.draw.circle(surf, (180, 180, 200), (cx, 5), 6)
                    pg.draw.circle(surf, tc, (cx, 5), 5)
                    # 面甲缝隙
                    pg.draw.line(surf, (40, 40, 50), (cx - 2, 6), (cx + 2, 6), 1)
                else:
                    # 远程：小弓（背在身后）
                    pg.draw.arc(surf, (150, 120, 80), (cx + bw // 2 - 2, body_y - 2, 10, 10), -0.8, 0.8, 2)
                    pg.draw.line(surf, (150, 120, 80), (cx + bw // 2 + 2, body_y), (cx + bw // 2 + 2, body_y + 8), 1)
                    # 轻头盔
                    pg.draw.circle(surf, (200, 200, 210), (cx, 4), 5)
                    pg.draw.circle(surf, tc, (cx, 4), 4)
                # 头
                head_r = 6 if mtype == 'super' else (5 if mtype == 'melee' else 4)
                head_y = 4
                pg.draw.circle(surf, (255, 220, 180), (cx, head_y), head_r)
                # 眼睛
                pg.draw.circle(surf, (40, 40, 50), (cx - 2, head_y), 1)
                pg.draw.circle(surf, (40, 40, 50), (cx + 2, head_y), 1)
                self._surfaces[f'minion_{team}_{mtype}'] = surf

    def get_minion(self, team, mtype):
        return self._surfaces[f'minion_{team}_{mtype}']

    # ---- 野怪 ----

    def _build_monster_bodies(self):
        # 狼 — 更自然轮廓+尾巴+描边
        wolf = pg.Surface((60, 40), pg.SRCALPHA)
        wc = (120, 144, 156)
        wc_dark = (80, 100, 112)
        # 身体（椭圆）
        pg.draw.ellipse(wolf, wc, (8, 10, 34, 20))
        pg.draw.ellipse(wolf, wc_dark, (8, 10, 34, 20), 1)
        # 腹部亮色
        pg.draw.ellipse(wolf, (145, 168, 178), (12, 18, 26, 8))
        # 头
        pg.draw.circle(wolf, wc, (40, 18), 9)
        pg.draw.circle(wolf, wc_dark, (40, 18), 9, 1)
        # 吻部
        pg.draw.ellipse(wolf, (100, 124, 136), (44, 16, 10, 8))
        # 耳朵
        pg.draw.polygon(wolf, wc, [(34, 10), (36, 1), (40, 10)])
        pg.draw.polygon(wolf, wc_dark, [(34, 10), (36, 1), (40, 10)], 1)
        pg.draw.polygon(wolf, wc, [(40, 10), (42, 1), (46, 10)])
        pg.draw.polygon(wolf, wc_dark, [(40, 10), (42, 1), (46, 10)], 1)
        # 眼睛（发光）
        pg.draw.circle(wolf, (255, 213, 79), (42, 16), 2)
        pg.draw.circle(wolf, (200, 160, 30), (42, 16), 1)
        # 尾巴（弯曲向上）
        tail_pts = [(8, 18), (4, 14), (0, 8), (2, 6), (6, 12), (8, 14)]
        pg.draw.lines(wolf, wc, False, [(8, 18), (4, 14), (1, 8)], 4)
        pg.draw.lines(wolf, wc_dark, False, [(8, 18), (4, 14), (1, 8)], 1)
        # 腿
        for lx in [14, 24, 32]:
            pg.draw.line(wolf, wc_dark, (lx, 28), (lx, 34), 2)
        self._surfaces['monster_wolf'] = wolf

        # 石头人 — 裂纹纹理+发光核心+描边
        golem = pg.Surface((60, 56), pg.SRCALPHA)
        gc = (141, 110, 99)
        gc_dark = (90, 70, 60)
        gc_light = (180, 155, 140)
        # 身体
        pg.draw.rect(golem, gc, (14, 16, 32, 24), border_radius=4)
        pg.draw.rect(golem, gc_dark, (14, 16, 32, 24), 1, border_radius=4)
        # 裂纹纹理
        pg.draw.line(golem, gc_dark, (22, 18), (20, 30), 1)
        pg.draw.line(golem, gc_dark, (30, 20), (34, 28), 1)
        pg.draw.line(golem, gc_dark, (38, 22), (40, 32), 1)
        # 发光核心
        pg.draw.circle(golem, (255, 200, 50, 120), (30, 28), 6)
        pg.draw.circle(golem, (255, 235, 59), (30, 28), 3)
        pg.draw.circle(golem, (255, 255, 200), (30, 27), 1)
        # 头
        pg.draw.rect(golem, gc, (16, 6, 28, 12), border_radius=3)
        pg.draw.rect(golem, gc_dark, (16, 6, 28, 12), 1, border_radius=3)
        # 眼睛（发光）
        pg.draw.rect(golem, (255, 235, 59), (22, 8, 5, 4))
        pg.draw.rect(golem, (255, 255, 200), (23, 9, 2, 2))
        pg.draw.rect(golem, (255, 235, 59), (32, 8, 5, 4))
        pg.draw.rect(golem, (255, 255, 200), (33, 9, 2, 2))
        # 眉脊
        pg.draw.line(golem, gc_dark, (20, 7), (28, 9), 2)
        pg.draw.line(golem, gc_dark, (32, 9), (40, 7), 2)
        # 手臂
        pg.draw.rect(golem, gc, (4, 18, 12, 16), border_radius=3)
        pg.draw.rect(golem, gc_dark, (4, 18, 12, 16), 1, border_radius=3)
        pg.draw.rect(golem, gc, (44, 18, 12, 16), border_radius=3)
        pg.draw.rect(golem, gc_dark, (44, 18, 12, 16), 1, border_radius=3)
        # 腿
        pg.draw.rect(golem, gc, (18, 40, 10, 12), border_radius=2)
        pg.draw.rect(golem, gc_dark, (18, 40, 10, 12), 1, border_radius=2)
        pg.draw.rect(golem, gc, (32, 40, 10, 12), border_radius=2)
        pg.draw.rect(golem, gc_dark, (32, 40, 10, 12), 1, border_radius=2)
        # 身体高光
        pg.draw.line(golem, gc_light, (16, 18), (16, 36), 1)
        self._surfaces['monster_golem'] = golem

        # 龙（更精细 — 鳞片、棘刺、翅膀网格、火焰呼吸）
        dragon = pg.Surface((80, 64), pg.SRCALPHA)
        dc = (126, 87, 194)
        # 身体（椭圆，有高光边）
        pg.draw.ellipse(dragon, dc, (4, 12, 48, 28))
        pg.draw.ellipse(dragon, (160, 120, 220), (4, 12, 48, 28), 1)
        # 鳞片纹理（V 形线）
        for i in range(5):
            sx = 12 + i * 8
            pg.draw.line(dragon, (100, 60, 160), (sx, 22), (sx + 3, 28), 1)
            pg.draw.line(dragon, (100, 60, 160), (sx, 22), (sx - 3, 28), 1)
        # 背部棘刺
        for i in range(4):
            spx = 10 + i * 10
            spy = 14 - i * 1
            pg.draw.polygon(dragon, (80, 40, 140), [(spx, spy), (spx - 3, spy - 6), (spx + 3, spy - 6)])
        # 翅膀（有翼膜网格）
        wing_color = (100, 60, 160, 160)
        # 左翼
        pg.draw.polygon(dragon, wing_color,
                        [(8, 16), (-4, 2), (6, 0), (14, 8)])
        pg.draw.line(dragon, dc, (8, 16), (-4, 2), 1)
        pg.draw.line(dragon, dc, (8, 16), (6, 0), 1)
        pg.draw.line(dragon, dc, (-4, 2), (6, 0), 1)
        # 右翼
        pg.draw.polygon(dragon, wing_color,
                        [(48, 16), (56, 0), (60, 2), (52, 8)])
        pg.draw.line(dragon, dc, (48, 16), (56, 0), 1)
        pg.draw.line(dragon, dc, (48, 16), (60, 2), 1)
        # 头（更大更精细）
        pg.draw.circle(dragon, dc, (50, 20), 13)
        pg.draw.circle(dragon, (160, 120, 220), (50, 20), 13, 1)
        # 头冠
        pg.draw.polygon(dragon, (80, 40, 140),
                        [(44, 8), (50, 2), (56, 8)])
        # 眼睛（龙瞳）
        pg.draw.circle(dragon, (255, 213, 79), (54, 18), 4)
        pg.draw.circle(dragon, (255, 150, 0), (54, 18), 2)
        pg.draw.circle(dragon, (0, 0, 0), (54, 18), 1)
        pg.draw.circle(dragon, (255, 213, 79), (58, 20), 3)
        pg.draw.circle(dragon, (255, 150, 0), (58, 20), 1)
        # 火焰呼吸（嘴部）
        for i in range(5):
            fx = 60 + i * 4
            fy = 22 + math.sin(i * 1.2) * 2
            pg.draw.circle(dragon, (255, 100 + i * 30, 0, 200 - i * 30), (fx, fy), 4 - i * 0.5)
        # 尾巴（带尾刺）
        pg.draw.line(dragon, dc, (4, 20), (-4, 14), 5)
        pg.draw.line(dragon, dc, (-4, 14), (-8, 18), 4)
        pg.draw.polygon(dragon, (80, 40, 140), [(-8, 18), (-10, 14), (-6, 14)])
        # 腿（更粗）
        pg.draw.line(dragon, dc, (20, 38), (18, 52), 5)
        pg.draw.line(dragon, dc, (36, 38), (38, 52), 5)
        # 爪子
        pg.draw.line(dragon, (80, 40, 140), (16, 50), (14, 54), 2)
        pg.draw.line(dragon, (80, 40, 140), (20, 50), (22, 54), 2)
        pg.draw.line(dragon, (80, 40, 140), (36, 50), (34, 54), 2)
        pg.draw.line(dragon, (80, 40, 140), (40, 50), (42, 54), 2)
        self._surfaces['monster_dragon'] = dragon

    def get_monster(self, mtype):
        return self._surfaces.get(f'monster_{mtype}')

    # ---- 弹头 ----

    def _build_projectile_bullet(self):
        surf = pg.Surface((8, 8), pg.SRCALPHA)
        pg.draw.circle(surf, (180, 180, 220), (4, 4), 3)
        pg.draw.circle(surf, (255, 255, 255, 150), (4, 4), 1)
        self._surfaces['projectile_bullet'] = surf

    def get_projectile_bullet(self):
        return self._surfaces['projectile_bullet']

    # ---- 掉落物 ----

    def _build_loot_icons(self):
        # 发光
        glow = pg.Surface((30, 30), pg.SRCALPHA)
        pg.draw.circle(glow, (255, 213, 79, 60), (15, 15), 12)
        self._surfaces['loot_glow'] = glow
        # 菱形
        diamond = pg.Surface((16, 16), pg.SRCALPHA)
        pts = [(8, 0), (14, 8), (8, 16), (2, 8)]
        pg.draw.polygon(diamond, (255, 213, 79), pts)
        self._surfaces['loot_diamond'] = diamond

    def get_loot_glow(self):
        return self._surfaces['loot_glow']

    def get_loot_diamond(self):
        return self._surfaces['loot_diamond']

    # ==================== 磁盘持久化 ====================

    def save_all(self):
        """将所有缓存 Surface 保存为 PNG 到 assets/sprites/"""
        d = _get_sprite_dir()
        os.makedirs(d, exist_ok=True)
        for name, surf in self._surfaces.items():
            path = os.path.join(d, f'{name}.png')
            pg.image.save(surf, path)
            print(f'  ✓ {name}.png  ({surf.get_width()}×{surf.get_height()})')
        print(f'共保存 {len(self._surfaces)} 个素材到 {d}')

    def load_from_disk(self):
        """从 assets/sprites/ 加载所有 PNG 文件"""
        d = _get_sprite_dir()
        if not os.path.isdir(d):
            return False
        names = [f[:-4] for f in os.listdir(d) if f.endswith('.png')]
        if not names:
            return False
        for name in names:
            path = os.path.join(d, f'{name}.png')
            try:
                surf = pg.image.load(path)
                # 优化：带 alpha 的用 convert_alpha，否则用 convert
                # (如果还没 set_mode 则跳过 convert)
                try:
                    if surf.get_flags() & pg.SRCALPHA:
                        surf = surf.convert_alpha()
                    else:
                        surf = surf.convert()
                except pg.error:
                    pass
                self._surfaces[name] = surf
            except Exception as e:
                print(f'  ⚠ 加载 {name}.png 失败: {e}')
        print(f'从磁盘加载 {len(self._surfaces)} 个素材')
        return True


# 模块级单例，方便全局访问
_CACHE = None

def get_cache():
    """获取 SpriteCache 实例。
    优先从磁盘加载 PNG，缺失项运行时构建补齐。
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    _CACHE = SpriteCache()
    # 尝试从磁盘加载已有素材
    _CACHE.load_from_disk()
    # 无论如何都构建一次 — build 方法内检查 key 是否已存在，避免重复
    _CACHE.build_all()
    return _CACHE
