"""HUD 界面"""
import pygame as pg
from utils import get_font


class HUD:
    def __init__(self, game):
        self.game = game
        self.font = get_font(15)
        self.font_bold = get_font(15, bold=True)
        self.font_small = get_font(13)
        self.font_desc = get_font(12)
        self._skill_rects = {}   # slot -> pg.Rect
        self._item_rects = {}    # index -> pg.Rect
        self._shop_item_rects = []  # shop item rects
        self._shop_close_rect = None

    def render(self, surface, mouse_x=None, mouse_y=None):
        h = self.game.player_hero
        if not h:
            return
        W, H = self.game.view_w, self.game.view_h

        # 底部 HUD 背景
        hud_rect = pg.Rect(10, H - 96, W - 20, 86)
        pg.draw.rect(surface, (255, 255, 255), hud_rect, border_radius=14)
        pg.draw.rect(surface, (220, 225, 232), hud_rect, 1, border_radius=14)

        # ---- 左侧: 英雄信息 ----
        # 名称
        name_surf = self.font_bold.render(f'{h.type_icon} {h.type_name}', True, (22, 32, 45))
        surface.blit(name_surf, (30, H - 85))
        # 等级
        lvl_surf = self.font_small.render(f'Lv.{h.level}', True, (45, 55, 70))
        surface.blit(lvl_surf, (30, H - 65))

        # 血条 + 经验条
        hp_x, hp_y = 30, H - 50
        hp_w, hp_h = 180, 12
        pg.draw.rect(surface, (225, 230, 235), (hp_x, hp_y, hp_w, hp_h), border_radius=6)
        pg.draw.rect(surface, (180, 190, 200), (hp_x, hp_y, hp_w, hp_h), 1, border_radius=6)
        h_pct = max(0, h.hp / h.max_hp)
        hp_color = (46, 204, 113) if h_pct > 0.5 else \
                   (243, 156, 18) if h_pct > 0.25 else (200, 50, 40)
        if h_pct > 0:
            pg.draw.rect(surface, hp_color, (hp_x + 2, hp_y + 2,
                                              (hp_w - 4) * h_pct, hp_h - 4), border_radius=4)
        hp_text = self.font_small.render(f'{int(h.hp)}/{h.max_hp}', True, (30, 42, 55))
        surface.blit(hp_text, (hp_x + hp_w // 2 - hp_text.get_width() // 2, hp_y + 1))

        # 经验条
        exp_y = hp_y + hp_h + 2
        exp_h = 4
        pg.draw.rect(surface, (225, 230, 235), (hp_x, exp_y, hp_w, exp_h), border_radius=2)
        exp_pct = min(1, h.exp / h.max_exp)
        if exp_pct > 0:
            pg.draw.rect(surface, (65, 105, 180),
                         (hp_x + 1, exp_y + 1, (hp_w - 2) * exp_pct, exp_h - 2), border_radius=1)

        # 金币
        gold_surf = self.font_bold.render(f'G: {h.gold}', True, (180, 130, 20))
        surface.blit(gold_surf, (W - 200, H - 85))

        # 复活倒计时
        if not h.alive and h.respawn_timer > 0:
            resp = self.font_bold.render(f'DEAD {int(h.respawn_timer)}s', True, (200, 50, 40))
            surface.blit(resp, (hp_x + hp_w + 10, hp_y - 2))

        # ---- 中间: 技能按钮 ----
        ab_x = W // 2 - 90
        skills = [('Q', 'q'), ('W', 'w'), ('E', 'e')]
        self._skill_rects.clear()
        hovered_slot = None
        for i, (key, slot) in enumerate(skills):
            bx = ab_x + i * 65
            by = H - 80
            ab = h.abilities.get(slot)

            # 按钮背景
            btn_rect = pg.Rect(bx, by, 50, 50)
            self._skill_rects[slot] = btn_rect
            if mouse_x is not None and btn_rect.collidepoint(mouse_x, mouse_y):
                hovered_slot = slot
                pg.draw.rect(surface, (235, 242, 255), btn_rect, border_radius=12)
                pg.draw.rect(surface, (52, 152, 219), btn_rect, 2, border_radius=12)
            else:
                pg.draw.rect(surface, (255, 255, 255), btn_rect, border_radius=12)
                pg.draw.rect(surface, (220, 225, 232), btn_rect, 2, border_radius=12)

            # 按键名
            key_surf = self.font_bold.render(key, True, (35, 120, 190))
            surface.blit(key_surf, (bx + 19, by + 5))

            # 技能名
            if ab:
                name_s = self.font_small.render(ab['name'], True, (30, 40, 55))
                surface.blit(name_s, (bx + 25 - name_s.get_width() // 2, by + 28))

            # CD 遮罩
            if ab and ab['cur_cd'] > 0:
                cd_surf = pg.Surface((46, 46))
                cd_surf.set_alpha(160)
                cd_surf.fill((44, 62, 80))
                surface.blit(cd_surf, (bx + 2, by + 2))
                cd_text = self.font_bold.render(f'{int(ab["cur_cd"])}', True, (200, 50, 40))
                surface.blit(cd_text, (bx + 25 - cd_text.get_width() // 2,
                                       by + 25 - cd_text.get_height() // 2))

        # ---- 技能描述 tooltip ----
        if hovered_slot:
            ab = h.abilities.get(hovered_slot)
            if ab:
                self._render_skill_tooltip(surface, ab, ab_x, H - 90, W)

        # ---- 右侧: 装备 ----
        rx = W - 180
        self._item_rects.clear()
        hovered_item = None
        for i in range(self.game.cfg.ITEM_COUNT):
            ix = rx + i * 55
            iy = H - 78
            slot_rect = pg.Rect(ix, iy, 42, 42)
            self._item_rects[i] = slot_rect
            if i < len(h.items):
                item = h.items[i]
                if mouse_x is not None and slot_rect.collidepoint(mouse_x, mouse_y):
                    hovered_item = item
                    pg.draw.rect(surface, (255, 245, 220), slot_rect, border_radius=10)
                    pg.draw.rect(surface, (230, 160, 30), slot_rect, 2, border_radius=10)
                else:
                    pg.draw.rect(surface, (255, 251, 235), slot_rect, border_radius=10)
                    pg.draw.rect(surface, (200, 140, 20), slot_rect, 2, border_radius=10)
                item_s = self.font_small.render(item['name'][:3], True, (45, 30, 10))
                surface.blit(item_s, (ix + 21 - item_s.get_width() // 2,
                                      iy + 21 - item_s.get_height() // 2))
            else:
                pg.draw.rect(surface, (245, 247, 250), slot_rect, border_radius=10)
                pg.draw.rect(surface, (170, 180, 190), slot_rect, 1, border_radius=10)
                empty_s = self.font_small.render('空', True, (80, 90, 105))
                surface.blit(empty_s, (ix + 21 - empty_s.get_width() // 2,
                                       iy + 21 - empty_s.get_height() // 2))

        # ---- 装备描述 tooltip ----
        if hovered_item:
            self._render_item_tooltip(surface, hovered_item, rx, H - 88, W)

        # ---- 水晶状态 ----
        self._render_crystal_status(surface, W)

        # ---- LLM AI 状态面板 ----
        if self.game.llm_ai and self.game.llm_ai.enabled:
            self._render_llm_status(surface, W, H)

        # ---- 商店面板 ----
        if self.game.shop_open:
            self._render_shop_panel(surface, W, H)

    def _render_skill_tooltip(self, surface, ab, anchor_x, anchor_y, view_w):
        """在技能按钮上方渲染技能详细描述 tooltip"""
        name = ab.get('name', '')
        desc = ab.get('desc', '')
        cd = ab.get('cd', 0)
        dmg = ab.get('dmg', 0)
        cur_cd = ab.get('cur_cd', 0)

        lines = []
        # 标题行: 技能名 + CD状态
        cd_text = f'CD {int(cur_cd)}s' if cur_cd > 0 else f'CD {cd}s'
        lines.append((f'{name}  [{cd_text}]', True))
        # 伤害
        lines.append((f'伤害: {dmg}', False))
        # 描述（可能较长，需要换行）
        max_chars = 42
        if len(desc) > max_chars:
            # 尝试在 | 处断行
            parts = desc.split(' | ')
            for part in parts:
                lines.append((part.strip(), False))
        else:
            lines.append((desc, False))
        # CD 状态提示
        if cur_cd > 0:
            lines.append((f'冷却中... {cur_cd:.1f}秒', False))

        # 计算 tooltip 尺寸
        line_h = 16
        pad = 10
        max_w = 0
        for text, bold in lines:
            f = self.font_bold if bold else self.font_desc
            w = f.render(text, True, (0, 0, 0)).get_width()
            max_w = max(max_w, w)
        tw = max_w + pad * 2
        th = len(lines) * line_h + pad * 2

        # 定位：技能按钮上方居中
        tx = anchor_x - tw // 2 + 55  # 近似居中于三个按钮
        tx = max(10, min(tx, view_w - tw - 10))
        ty = anchor_y - th - 6

        # 背景
        tooltip_rect = pg.Rect(tx, ty, tw, th)
        pg.draw.rect(surface, (255, 255, 250), tooltip_rect, border_radius=8)
        pg.draw.rect(surface, (180, 190, 200), tooltip_rect, 1, border_radius=8)
        # 小三角
        tri_pts = [(anchor_x + 55, anchor_y + 4),
                   (anchor_x + 55 - 6, anchor_y - 2),
                   (anchor_x + 55 + 6, anchor_y - 2)]
        pg.draw.polygon(surface, (255, 255, 250), tri_pts)
        pg.draw.polygon(surface, (180, 190, 200), tri_pts, 1)

        # 渲染文字
        for i, (text, bold) in enumerate(lines):
            f = self.font_bold if bold else self.font_desc
            color = (25, 35, 50) if bold else (55, 65, 80)
            if '冷却中' in text:
                color = (200, 50, 40)
            text_surf = f.render(text, True, color)
            surface.blit(text_surf, (tx + pad, ty + pad + i * line_h))

    def _render_crystal_status(self, surface, W):
        """在屏幕顶部中央显示双方水晶状态"""
        game = self.game
        blue_crystals = getattr(game, 'blue_crystals', [])
        red_crystals = getattr(game, 'red_crystals', [])
        
        cy = 8
        dot_r = 6
        gap = 20
        
        # 蓝方水晶
        bx_start = W // 2 - 60
        for i, c in enumerate(blue_crystals):
            cx = bx_start + i * gap
            color = (52, 152, 219) if c.alive else (60, 60, 80)
            pg.draw.circle(surface, color, (cx, cy), dot_r)
            pg.draw.circle(surface, (80, 80, 100), (cx, cy), dot_r, 1)
        
        # 中间分隔
        sep_s = self.font_desc.render('CRYSTAL', True, (120, 130, 150))
        surface.blit(sep_s, (W // 2 - sep_s.get_width() // 2, cy - 4))
        
        # 红方水晶
        rx_start = W // 2 + 20
        for i, c in enumerate(red_crystals):
            cx = rx_start + i * gap
            color = (231, 76, 60) if c.alive else (60, 60, 80)
            pg.draw.circle(surface, color, (cx, cy), dot_r)
            pg.draw.circle(surface, (80, 80, 100), (cx, cy), dot_r, 1)

    def _render_shop_panel(self, surface, W, H):
        """渲染装备商店面板"""
        shop_items = self.game.shop_items
        if not shop_items:
            return
        h = self.game.player_hero
        game = self.game
        
        # 当前层级
        max_tier = 1
        for t, tier in game.cfg.SHOP_TIERS:
            if game.game_time >= t:
                max_tier = max(max_tier, tier)
        
        # 面板尺寸（4件装备用更宽的面板）
        pw, ph = 420, 190
        px, py = W // 2 - pw // 2, H // 2 - ph // 2 - 30
        
        # 半透明背景
        bg = pg.Surface((pw, ph), pg.SRCALPHA)
        bg.fill((20, 25, 40, 230))
        surface.blit(bg, (px, py))
        pg.draw.rect(surface, (100, 200, 255), (px, py, pw, ph), 2, border_radius=12)
        
        # 标题 + 层级
        tier_names = {1: '基础', 2: '中级', 3: '高级'}
        title_s = self.font_bold.render(f'装备商店 [T{max_tier} {tier_names.get(max_tier,"")}] [B关闭]', True, (200, 220, 255))
        surface.blit(title_s, (px + pw // 2 - title_s.get_width() // 2, py + 10))
        
        # 金币
        gold_s = self.font_small.render(f'金币: {h.gold if h else 0}', True, (255, 200, 50))
        surface.blit(gold_s, (px + 15, py + 35))
        
        # 商品
        self._shop_item_rects.clear()
        slot_w = 90
        gap = 10
        for i, item in enumerate(shop_items):
            ix = px + 15 + i * (slot_w + gap)
            iy = py + 55
            item_rect = pg.Rect(ix, iy, slot_w, 110)
            self._shop_item_rects.append(item_rect)
            
            # 卡片背景
            pg.draw.rect(surface, (40, 45, 60), item_rect, border_radius=8)
            pg.draw.rect(surface, (80, 90, 110), item_rect, 1, border_radius=8)
            
            # 层级标签
            t = item.get('tier', 1)
            tier_c = [(100, 180, 100), (100, 160, 220), (220, 150, 50)][min(t-1, 2)]
            tier_lbl = self.font_desc.render(f'T{t}', True, tier_c)
            surface.blit(tier_lbl, (ix + 3, iy + 3))
            
            # 物品名
            name_s = self.font_small.render(item['name'], True, (220, 230, 240))
            surface.blit(name_s, (ix + 45 - name_s.get_width() // 2, iy + 10))
            
            # 价格
            cost = item.get('cost', 300)
            cost_c = (50, 200, 50) if (h and h.gold >= cost) else (200, 50, 50)
            cost_s = self.font_small.render(f'{cost}G', True, cost_c)
            surface.blit(cost_s, (ix + 45 - cost_s.get_width() // 2, iy + 35))
            
            # 描述（截断）
            desc = item.get('desc', '')
            desc_s = self.font_desc.render(desc[:12], True, (150, 160, 170))
            surface.blit(desc_s, (ix + 45 - desc_s.get_width() // 2, iy + 55))
            
            # 购买提示
            buy_s = self.font_desc.render('点击购买', True, (120, 130, 150))
            surface.blit(buy_s, (ix + 45 - buy_s.get_width() // 2, iy + 75))
        
        # 关闭按钮
        close_rect = pg.Rect(px + pw - 30, py + 5, 25, 25)
        self._shop_close_rect = close_rect
        pg.draw.rect(surface, (140, 50, 50), close_rect, border_radius=4)
        close_s = self.font_small.render('X', True, (255, 255, 255))
        surface.blit(close_s, (close_rect.x + 8, close_rect.y + 3))
        
        # 操作提示
        hint_s = self.font_desc.render('右键装备槽出售 | B键开关商店 | 60s刷新', True, (130, 140, 160))
        surface.blit(hint_s, (px + pw // 2 - hint_s.get_width() // 2, py + ph - 20))

    def _render_item_tooltip(self, surface, item, anchor_x, anchor_y, view_w):
        """在装备槽上方渲染装备描述 tooltip"""
        name = item.get('name', '')
        desc = item.get('desc', '')
        color = item.get('color', '#ffffff')

        lines = []
        lines.append((name, True))
        lines.append((desc, False))

        line_h = 16
        pad = 10
        max_w = 0
        for text, bold in lines:
            f = self.font_bold if bold else self.font_desc
            w = f.render(text, True, (0, 0, 0)).get_width()
            max_w = max(max_w, w)
        tw = max_w + pad * 2
        th = len(lines) * line_h + pad * 2

        tx = anchor_x - tw // 2 + 21
        tx = max(10, min(tx, view_w - tw - 10))
        ty = anchor_y - th - 6

        tooltip_rect = pg.Rect(tx, ty, tw, th)
        pg.draw.rect(surface, (255, 252, 240), tooltip_rect, border_radius=8)
        pg.draw.rect(surface, (200, 150, 20), tooltip_rect, 1, border_radius=8)

        for i, (text, bold) in enumerate(lines):
            f = self.font_bold if bold else self.font_desc
            c = (60, 40, 20) if bold else (80, 65, 50)
            text_surf = f.render(text, True, c)
            surface.blit(text_surf, (tx + pad, ty + pad + i * line_h))

    def _render_llm_status(self, surface, W, H):
        """在小地图下方渲染 LLM AI 决策状态面板"""
        llm = self.game.llm_ai
        if not llm or not llm.enabled:
            return

        # 收集所有 LLM 控制英雄的信息
        heroes_info = []
        for e in self.game.entities:
            if not hasattr(e, 'hero_type') or not e.alive:
                continue
            if not llm.should_control_hero(e):
                continue
            d = llm.get_directive(e)
            action = d.get('action', '-') if d else '-'
            reason = d.get('reason', '') if d else ''
            # 截断原因
            if len(reason) > 8:
                reason = reason[:8] + '..'
            heroes_info.append((e.type_icon, action, reason))

        if not heroes_info:
            return

        # 面板尺寸
        panel_w = 170
        line_h = 18
        panel_h = 24 + len(heroes_info) * line_h + 8
        panel_x = W - panel_w - 10
        panel_y = H - 96 - panel_h - 10  # HUD 上方

        # 背景
        bg = pg.Surface((panel_w, panel_h), pg.SRCALPHA)
        bg.fill((15, 20, 35, 200))
        surface.blit(bg, (panel_x, panel_y))
        pg.draw.rect(surface, (80, 130, 200), (panel_x, panel_y, panel_w, panel_h), 1, border_radius=6)

        # 标题
        title_s = self.font_small.render('AI 指挥', True, (100, 180, 255))
        surface.blit(title_s, (panel_x + 8, panel_y + 4))

        # 每个英雄一行
        for i, (icon, action, reason) in enumerate(heroes_info):
            y = panel_y + 24 + i * line_h
            # 行动颜色
            action_colors = {
                'push': (46, 204, 113), 'retreat': (231, 76, 60),
                'gank': (155, 89, 182), 'defend': (52, 152, 219),
                'jungle': (241, 196, 15), 'group': (230, 126, 34),
                'idle': (149, 165, 166),
            }
            ac = action_colors.get(action, (180, 180, 190))
            # 英雄图标
            icon_s = self.font_desc.render(icon, True, (220, 225, 235))
            surface.blit(icon_s, (panel_x + 8, y))
            # 行动
            act_s = self.font_desc.render(action, True, ac)
            surface.blit(act_s, (panel_x + 28, y))
            # 原因
            if reason:
                reas_s = self.font_desc.render(reason, True, (130, 140, 155))
                surface.blit(reas_s, (panel_x + 72, y))