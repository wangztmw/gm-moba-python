"""渲染器 — 使用 SpriteCache 缓存静态元素，减少每帧 draw call"""
import math
import pygame as pg
from utils import get_font, alpha_surf
from config import W, H
from systems.sprite_cache import get_cache


class Renderer:
    def __init__(self):
        # 构建/获取全局缓存
        self._cache = get_cache()
        # 小 surface 缓存 — 避免每帧重复创建
        self._surf_pool = {}

    def _pool_surf(self, w, h):
        """获取或创建 SRCALPHA surface"""
        key = (w, h)
        if key not in self._surf_pool:
            self._surf_pool[key] = pg.Surface((w, h), pg.SRCALPHA)
        s = self._surf_pool[key]
        s.fill((0, 0, 0, 0))  # 清空
        return s

    def render(self, game, surface):
        cam = game.camera
        surface.fill((245, 247, 250))
        # 使用浮点偏移让相机移动更平滑，避免像素捕捉抖动
        ox = cam.view_w / 2 - cam.x
        oy = cam.view_h / 2 - cam.y

        self._render_map(surface, ox, oy)

        def is_vis(e, margin=100):
            alive = getattr(e, 'alive', e.life > 0 if hasattr(e, 'life') else True)
            return (alive and
                    e.x > cam.x - cam.view_w / 2 - margin and
                    e.x < cam.x + cam.view_w / 2 + margin and
                    e.y > cam.y - cam.view_h / 2 - margin and
                    e.y < cam.y + cam.view_h / 2 + margin)

        render_list = []
        for e in game.entities:
            if hasattr(e, 'shielded') and e.alive:
                render_list.append((e, -1))
            elif hasattr(e, 'tier') and e.alive:
                render_list.append((e, 0))
            elif hasattr(e, 'lane_idx') and is_vis(e):
                render_list.append((e, 1))
            elif hasattr(e, 'spawn_x') and is_vis(e):
                render_list.append((e, 2))
            elif hasattr(e, 'is_player') and is_vis(e):
                render_list.append((e, 3))
        render_list.sort(key=lambda x: x[1])

        for e, _ in render_list:
            try: e.render(surface, ox, oy)
            except Exception: pass

        for e in game.entities:
            if hasattr(e, 'tier') and not e.alive:
                try: e.render(surface, ox, oy)
                except: pass
            if hasattr(e, 'shielded') and not e.alive:
                try: e.render(surface, ox, oy)
                except: pass

        for l in game.loot_drops:
            if is_vis(l, 50):
                self._render_loot(surface, l, ox, oy)

        for p in game.projectiles:
            try: self._render_projectile(surface, p, ox, oy)
            except Exception: pass

        for f in game.floating_texts:
            try: self._render_floating_text(surface, f, ox, oy)
            except Exception: pass

        # 点击指示器
        for cm in game.click_markers:
            try: self._render_click_marker(surface, cm, ox, oy)
            except Exception: pass

        # 路径点不显示标记，仅保留逻辑

    # ==================== 地图（完全缓存） ====================

    def _render_map(self, surface, ox, oy):
        """blit 预渲染好的地图 + 灌木（全整数坐标，消除瓦片缝隙）"""
        # 可见区域裁剪 — 全部使用 int 保证对齐
        vx = int(max(0, -ox))
        vy = int(max(0, -oy))
        vw = int(min(W, -ox + surface.get_width()) - vx)
        vh = int(min(H, -oy + surface.get_height()) - vy)
        if vw <= 0 or vh <= 0:
            return

        cache = get_cache()
        blit_x = int(ox + vx)
        blit_y = int(oy + vy)
        # 地图基底
        map_surf = cache.get_map_bg()
        surface.blit(map_surf, (blit_x, blit_y), (vx, vy, vw, vh))
        # 灌木（半透明覆盖）
        bush_surf = cache.get_bushes()
        surface.blit(bush_surf, (blit_x, blit_y), (vx, vy, vw, vh))

    # ==================== 掉落物 ====================

    def _render_loot(self, surface, loot, ox, oy):
        if loot.life <= 0:
            return
        bob = math.sin(loot.bob_offset) * 3
        x, y = loot.x + ox, loot.y + oy + bob
        col = loot.item.get('color', '#ffd54f')
        r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)

        cache = get_cache()
        # 发光
        glow = cache.get_loot_glow()
        # 着色 — 用 tinted 版本
        tinted_glow = pg.Surface((30, 30), pg.SRCALPHA)
        tinted_glow.blit(glow, (0, 0))
        # 重新着色 (保留 alpha)
        tinted_glow.fill((r, g, b, 0), None, pg.BLEND_RGBA_MULT)
        surface.blit(tinted_glow, (x - 15, y - 15))

        # 圆环
        pg.draw.circle(surface, (r, g, b), (int(x), int(y)), 12, 2)

        # 菱形（从缓存取形状，动态着色）
        dia = cache.get_loot_diamond()
        tinted_dia = dia.copy()
        tinted_dia.fill((r, g, b, 0), None, pg.BLEND_RGBA_MULT)
        surface.blit(tinted_dia, (int(x) - 8, int(y) - 8))

        s = get_font(10).render(loot.item['name'], True, (45, 55, 70))
        surface.blit(s, (x - s.get_width() // 2, y + 20))

    # ==================== 弹道 / 特效 ====================

    def _render_projectile(self, surface, p, ox, oy):
        if not p.alive:
            return
        x, y = int(p.x + ox), int(p.y + oy)

        # Dash 线 — 流星冲刺特效（宽→窄锥形 + 光晕 + 沿路粒子）
        if p.type == 'dash' and 'startX' in p.extra:
            max_life = p.extra.get('maxLife', 0.35)
            t = 1 - p.extra['life'] / max_life
            sx = float(p.extra['startX'] + ox)
            sy = float(p.extra['startY'] + oy)
            ex = float(p.extra.get('endX', p.x) + ox)
            ey = float(p.extra.get('endY', p.y) + oy)
            fade = max(0, 1 - t)
            dx, dy = ex - sx, ey - sy
            d_len = math.hypot(dx, dy)
            if d_len < 1:
                return
            nx, ny = -dy / d_len, dx / d_len
            # 颜色（从 extra 或默认青色）
            col = p.extra.get('color', '#00bcd4')
            cr, cg, cb = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
            # 外层宽锥形 — 半透明光晕
            w_start = max(3.0, 18.0 * fade)
            w_end = max(1.0, 5.0 * fade)
            pts = [
                (sx + nx * w_start, sy + ny * w_start),
                (ex + nx * w_end,   ey + ny * w_end),
                (ex - nx * w_end,   ey - ny * w_end),
                (sx - nx * w_start, sy - ny * w_start),
            ]
            bx = int(min(p[0] for p in pts)) - 8
            by = int(min(p[1] for p in pts)) - 8
            bw = int(max(p[0] for p in pts) - bx) + 16
            bh = int(max(p[1] for p in pts) - by) + 16
            adj = [(px - bx + 8, py - by + 8) for px, py in pts]
            s = self._pool_surf(bw, bh)
            pg.draw.polygon(s, (cr // 3, cg // 3, cb // 3, int(120 * fade)), adj)
            surface.blit(s, (bx - 8, by - 8))
            # 中层 — 亮色主体
            pts2 = [
                (sx + nx * w_start * 0.5, sy + ny * w_start * 0.5),
                (ex + nx * w_end * 0.6,   ey + ny * w_end * 0.6),
                (ex - nx * w_end * 0.6,   ey - ny * w_end * 0.6),
                (sx - nx * w_start * 0.5, sy - ny * w_start * 0.5),
            ]
            bi = int(min(p[0] for p in pts2)) - 8
            bj = int(min(p[1] for p in pts2)) - 8
            bwi = int(max(p[0] for p in pts2) - bi) + 16
            bhi = int(max(p[1] for p in pts2) - bj) + 16
            adji = [(px - bi + 8, py - bj + 8) for px, py in pts2]
            s2 = self._pool_surf(bwi, bhi)
            pg.draw.polygon(s2, (cr, cg, cb, int(200 * fade)), adji)
            surface.blit(s2, (bi - 8, bj - 8))
            # 内芯 — 白亮色
            pts3 = [
                (sx + nx * w_start * 0.15, sy + ny * w_start * 0.15),
                (ex + nx * w_end * 0.2,   ey + ny * w_end * 0.2),
                (ex - nx * w_end * 0.2,   ey - ny * w_end * 0.2),
                (sx - nx * w_start * 0.15, sy - ny * w_start * 0.15),
            ]
            ci = int(min(p[0] for p in pts3)) - 8
            cj = int(min(p[1] for p in pts3)) - 8
            cwi = int(max(p[0] for p in pts3) - ci) + 16
            chi = int(max(p[1] for p in pts3) - cj) + 16
            adjc = [(px - ci + 8, py - cj + 8) for px, py in pts3]
            s3 = self._pool_surf(cwi, chi)
            bright = tuple(min(255, c + 120) for c in (cr, cg, cb))
            pg.draw.polygon(s3, bright + (int(220 * fade),), adjc)
            surface.blit(s3, (ci - 8, cj - 8))
            # 沿路粒子（6颗）
            n_dots = 6
            for di in range(n_dots):
                frac = (di + 0.5) / n_dots
                if frac > 1 - t:
                    continue
                px = sx + dx * frac + nx * (rnd(-3, 3))
                py = sy + dy * frac + ny * (rnd(-3, 3))
                dot_r = max(1, int(rnd(2, 4) * fade))
                ds = self._pool_surf(dot_r * 2 + 6, dot_r * 2 + 6)
                dc = dot_r + 3
                pg.draw.circle(ds, bright + (int(180 * fade),), (dc, dc), dot_r)
                surface.blit(ds, (int(px) - dc, int(py) - dc))
            # 起点圆（散射）
            start_r = max(2, int(10 * fade))
            ss = self._pool_surf(start_r * 2 + 8, start_r * 2 + 8)
            sc = start_r + 4
            pg.draw.circle(ss, (cr, cg, cb, int(160 * fade)), (sc, sc), start_r)
            surface.blit(ss, (int(sx) - sc, int(sy) - sc))
            # 终点圆（明亮冲击点）
            end_r = max(3, int(14 * fade))
            es = self._pool_surf(end_r * 2 + 8, end_r * 2 + 8)
            ec = end_r + 4
            pg.draw.circle(es, bright + (int(220 * fade),), (ec, ec), end_r)
            pg.draw.circle(es, (255, 255, 255, int(180 * fade)), (ec, ec), max(1, end_r // 2))
            surface.blit(es, (int(ex) - ec, int(ey) - ec))
            return

        # AOE 环 — 渐变双环
        if p.type == 'aoe' and 'radius' in p.extra:
            t = 1 - p.extra['life'] / p.extra['maxLife']
            r = int(p.extra['radius'] * (0.6 + t * 0.4))
            col = p.color if p.color.startswith('#') else '#ffffff'
            cr, cg, cb = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
            fade = 1 - t
            # 外暗环（极细 - 1px）
            outer_sz = r * 2 + 14
            s = self._pool_surf(outer_sz, outer_sz)
            co = outer_sz // 2
            pg.draw.circle(s, (cr//2, cg//2, cb//2, int(130 * fade)), (co, co), r,
                           max(1, int(1.5 * fade)))
            surface.blit(s, (x - co, y - co))
            # 内亮环
            ir = int(r * 0.65)
            inner_sz = ir * 2 + 14
            s2 = self._pool_surf(inner_sz, inner_sz)
            ci = inner_sz // 2
            pg.draw.circle(s2, (min(255, cr+60), min(255, cg+60), min(255, cb+60), int(180 * fade)),
                           (ci, ci), ir)
            surface.blit(s2, (x - ci, y - ci))
            return

        # Slash 斩击弧 — 渐变：边缘暗，中心亮
        if p.type == 'slash' and 'angle' in p.extra:
            t = 1 - p.extra['life'] / p.extra['maxLife']
            ang = p.extra['angle']
            w = p.extra.get('width', 1.2)
            length = p.extra.get('length', 70)
            col = p.color if p.color.startswith('#') else '#ffffff'
            cr, cg, cb = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
            fade = 1 - t
            n = 12
            r = length * (0.6 + 0.4 * t)
            # 外层暗色
            r_outer = r
            pts_outer = []
            for i in range(n + 1):
                a = ang - w / 2 + w * i / n
                pts_outer.append((x + math.cos(a) * r_outer, y + math.sin(a) * r_outer))
            inner_ro = r_outer * 0.4
            for i in range(n, -1, -1):
                a = ang - w / 2 + w * i / n
                pts_outer.append((x + math.cos(a) * inner_ro, y + math.sin(a) * inner_ro))
            if len(pts_outer) >= 4:
                bx = int(min(p[0] for p in pts_outer))
                by = int(min(p[1] for p in pts_outer))
                bw = int(max(p[0] for p in pts_outer) - bx) + 8
                bh = int(max(p[1] for p in pts_outer) - by) + 8
                adj = [(px - bx + 4, py - by + 4) for px, py in pts_outer]
                s = self._pool_surf(bw, bh)
                pg.draw.polygon(s, (cr//2, cg//2, cb//2, int(150 * fade)), adj)
                surface.blit(s, (bx - 4, by - 4))
            # 内层亮色（稍小）
            r_inner = r * 0.82
            pts_inner = []
            w_inner = w * 0.85
            for i in range(n + 1):
                a = ang - w_inner / 2 + w_inner * i / n
                pts_inner.append((x + math.cos(a) * r_inner, y + math.sin(a) * r_inner))
            inner_ri = r_inner * 0.5
            for i in range(n, -1, -1):
                a = ang - w_inner / 2 + w_inner * i / n
                pts_inner.append((x + math.cos(a) * inner_ri, y + math.sin(a) * inner_ri))
            if len(pts_inner) >= 4:
                bx2 = int(min(p[0] for p in pts_inner))
                by2 = int(min(p[1] for p in pts_inner))
                bw2 = int(max(p[0] for p in pts_inner) - bx2) + 8
                bh2 = int(max(p[1] for p in pts_inner) - by2) + 8
                adj2 = [(px - bx2 + 4, py - by2 + 4) for px, py in pts_inner]
                s2 = self._pool_surf(bw2, bh2)
                pg.draw.polygon(s2, (min(255, cr+60), min(255, cg+60), min(255, cb+60), int(200 * fade)), adj2)
                surface.blit(s2, (bx2 - 4, by2 - 4))
            return

        # Beam 光束 — 闭合锥形，极薄外层 + 高亮芯
        if p.type == 'beam' and 'endX' in p.extra:
            t = 1 - p.extra['life'] / p.extra['maxLife']
            fx, fy = float(p.x + ox), float(p.y + oy)
            ex, ey = float(p.extra['endX'] + ox), float(p.extra['endY'] + oy)
            col = p.color if p.color.startswith('#') else '#ffffff'
            cr, cg, cb = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
            fade = 1 - t
            dx, dy = ex - fx, ey - fy
            d_len = math.hypot(dx, dy)
            if d_len < 1:
                return
            nx, ny = -dy / d_len, dx / d_len
            # 外层极薄光晕（仅 1-2px 宽）
            w_start = max(0.5, 3.0 * fade)
            w_end = max(0.3, 1.2 * fade)
            pts = [
                (fx + nx * w_start, fy + ny * w_start),
                (ex + nx * w_end,   ey + ny * w_end),
                (ex - nx * w_end,   ey - ny * w_end),
                (fx - nx * w_start, fy - ny * w_start),
            ]
            bx = int(min(p[0] for p in pts)) - 4
            by = int(min(p[1] for p in pts)) - 4
            bw = int(max(p[0] for p in pts) - bx) + 8
            bh = int(max(p[1] for p in pts) - by) + 8
            adj = [(px - bx + 4, py - by + 4) for px, py in pts]
            s = self._pool_surf(bw, bh)
            pg.draw.polygon(s, (cr//3, cg//3, cb//3, int(120 * fade)), adj)
            surface.blit(s, (bx - 4, by - 4))
            # 内层亮芯
            w_inner_start = max(0.3, 1.0 * fade)
            w_inner_end = max(0.2, 0.5 * fade)
            pts_inner = [
                (fx + nx * w_inner_start, fy + ny * w_inner_start),
                (ex + nx * w_inner_end,   ey + ny * w_inner_end),
                (ex - nx * w_inner_end,   ey - ny * w_inner_end),
                (fx - nx * w_inner_start, fy - ny * w_inner_start),
            ]
            bi = int(min(p[0] for p in pts_inner)) - 4
            bj = int(min(p[1] for p in pts_inner)) - 4
            bwi = int(max(p[0] for p in pts_inner) - bi) + 8
            bhi = int(max(p[1] for p in pts_inner) - bj) + 8
            adji = [(px - bi + 4, py - bj + 4) for px, py in pts_inner]
            s2 = self._pool_surf(bwi, bhi)
            pg.draw.polygon(s2, (min(255, cr+60), min(255, cg+60), min(255, cb+60), int(190 * fade)), adji)
            surface.blit(s2, (bi - 4, bj - 4))
            # 中心极细亮线（1px）
            core_margin = 6
            bw3 = abs(int(ex) - int(fx)) + 2 * core_margin
            bh3 = abs(int(ey) - int(fy)) + 2 * core_margin
            mx3, my3 = min(int(fx), int(ex)) - core_margin, min(int(fy), int(ey)) - core_margin
            s3 = self._pool_surf(bw3, bh3)
            pg.draw.line(s3, (255, 255, 255, int(170 * fade)),
                         (int(fx) - mx3, int(fy) - my3),
                         (int(ex) - mx3, int(ey) - my3), 1)
            surface.blit(s3, (mx3, my3))
            return

        # Burst particle — 渐变：边缘暗，中心亮白
        if p.type == 'burst_particle':
            t = 1 - p.extra['life'] / p.extra['maxLife']
            pr = max(1, p.extra.get('radius', 3) * (1 - t * 0.7))
            col = p.color if p.color.startswith('#') else '#ffffff'
            cr, cg, cb = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
            fade = 1 - t
            ps = int(pr * 2 + 10)
            cx, cy = ps // 2, ps // 2
            # 外层暗光晕
            s = self._pool_surf(ps, ps)
            pg.draw.circle(s, (cr//3, cg//3, cb//3, int(100 * fade)), (cx, cy), max(1, int(pr * 0.3)))
            surface.blit(s, (x - cx, y - cy))
            # 内层亮核
            s2 = self._pool_surf(ps, ps)
            pg.draw.circle(s2, (min(255, cr+80), min(255, cg+80), min(255, cb+80), int(255 * fade)),
                           (cx, cy), max(1, int(pr * 0.7)))
            surface.blit(s2, (x - cx, y - cy))
            return

        # 拖尾 — 使用弹道自身颜色
        col = p.color if p.color.startswith('#') else '#b0bec5'
        cr, cg, cb = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
        for tr in p.trail:
            tx, ty = int(tr['x'] + ox), int(tr['y'] + oy)
            alpha = max(0, min(255, int(tr['life'] / 0.3 * 150)))
            ts = self._pool_surf(8, 8)
            pg.draw.circle(ts, (cr, cg, cb, alpha), (4, 4), 2)
            surface.blit(ts, (tx - 4, ty - 4))

        # 弹头 — 使用弹道自身颜色
        bs = self._pool_surf(10, 10)
        pg.draw.circle(bs, (cr, cg, cb, 220), (5, 5), 4)
        pg.draw.circle(bs, (255, 255, 255, 200), (5, 5), 2)
        surface.blit(bs, (x - 5, y - 5))

    # ==================== 浮动文字 ====================

    def _render_floating_text(self, surface, ft, ox, oy):
        if ft.life <= 0:
            return
        alpha = min(1, ft.life * 2)
        x, y = int(ft.x + ox), int(ft.y + oy)
        col = ft.color if ft.color.startswith('#') else '#ffffff'
        r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
        size = 16 if ft.is_damage else 14
        s = get_font(size, bold=ft.is_damage)
        text_surf = s.render(ft.text, True, (r, g, b))
        text_surf.set_alpha(int(255 * alpha))
        surface.blit(text_surf, (x - text_surf.get_width() // 2, y))

    def _render_click_marker(self, surface, cm, ox, oy):
        """渲染点击指示器 — 内缩圆环，渐隐消失"""
        life = cm.get('life', 0)
        if life <= 0:
            return
        x, y = int(cm['x'] + ox), int(cm['y'] + oy)
        t = 1 - life / 0.6  # 0→1 从大到小
        alpha = int(180 * (1 - t))
        r = int(18 * (1 - t * 0.5) + 4)
        # 外环
        pg.draw.circle(surface, (52, 152, 219, alpha), (x, y), r, 2)
        # 内点
        pg.draw.circle(surface, (52, 152, 219, alpha + 40), (x, y), 3)