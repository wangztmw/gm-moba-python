"""输入处理"""
import pygame as pg
from utils import dist


class InputHandler:
    def __init__(self, game):
        self.game = game
        self.last_click_time = 0

    def handle_events(self):
        game = self.game
        for event in pg.event.get():
            if event.type == pg.QUIT:
                return False

            if event.type == pg.VIDEORESIZE:
                # 窗口大小改变时更新视口
                game.view_w, game.view_h = event.w, event.h
                if hasattr(game, 'camera'):
                    game.camera.view_w = event.w
                    game.camera.view_h = event.h
                # 用新尺寸重建屏幕 surface（保留 RESIZABLE 属性）
                if game.screen:
                    try:
                        game.screen = pg.display.set_mode((event.w, event.h), pg.RESIZABLE | pg.SCALED, vsync=1)
                    except Exception:
                        pass

            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                now = pg.time.get_ticks()
                if now - self.last_click_time < 80:
                    continue
                self.last_click_time = now
                # 商店打开时：检查是否点击了商店物品
                if game.shop_open:
                    self._handle_shop_click(event.pos)
                else:
                    self._handle_click(event.pos)

            if event.type == pg.MOUSEBUTTONDOWN and event.button == 3:
                # 右键出售装备
                self._handle_right_click(event.pos)

            if event.type == pg.KEYDOWN:
                if event.key == pg.K_F11:
                    self._toggle_fullscreen()
                elif event.key == pg.K_b:
                    self._handle_shop_toggle()
                else:
                    self._handle_key(event.key)

        return True

    def _toggle_fullscreen(self):
        game = self.game
        if not game.screen:
            return
        is_full = bool(game.screen.get_flags() & pg.FULLSCREEN)
        if is_full:
            game.screen = pg.display.set_mode((game.view_w, game.view_h), pg.RESIZABLE | pg.SCALED, vsync=1)
        else:
            game.screen = pg.display.set_mode((0, 0), pg.FULLSCREEN | pg.RESIZABLE | pg.SCALED, vsync=1)
            game.view_w, game.view_h = game.screen.get_size()
        if hasattr(game, 'camera'):
            game.camera.view_w = game.view_w
            game.camera.view_h = game.view_h

    def _handle_click(self, screen_pos):
        game = self.game
        if game.game_over:
            return
        sx, sy = screen_pos
        wx, wy = game.camera.screen_to_world(sx, sy)

        # 点击指示器
        game.add_click_marker(wx, wy)

        hero = game.player_hero
        if not hero or not hero.alive:
            return

        # 拾取
        for loot in game.loot_drops:
            if loot.life > 0 and dist((wx, wy), (loot.x, loot.y)) < 18:
                game.pickup_loot(hero, loot)
                return

        # 点击攻击
        click_radius = 60
        enemies = game.get_all_enemies(hero.team)
        nearest = None
        nearest_d = click_radius
        for e in enemies:
            if not e.alive:
                continue
            d = dist((wx, wy), (e.x, e.y))
            if d < nearest_d:
                nearest_d = d
                nearest = e

        if nearest:
            hero.target = nearest
            hero.waypoints = [(nearest.x, nearest.y)]
            hero._want_attack = True
            return

        # 普通移动 — 始终覆盖攻击目标
        hero.target = None
        hero.waypoints = [(wx, wy)]

    def _handle_key(self, key):
        game = self.game
        if game.game_over or not game.player_hero or not game.player_hero.alive:
            return
        hero = game.player_hero
        # 获取鼠标在游戏世界中的坐标（作为技能目标方向）
        mx, my = pg.mouse.get_pos()
        wx, wy = game.camera.screen_to_world(mx, my)
        if key == pg.K_q:
            hero.use_ability_ui('q', game, target_x=wx, target_y=wy)
        elif key == pg.K_w:
            hero.use_ability_ui('w', game, target_x=wx, target_y=wy)
        elif key == pg.K_e:
            hero.use_ability_ui('e', game, target_x=wx, target_y=wy)
        elif key == pg.K_SPACE:
            hero._want_attack = True

    def _handle_right_click(self, screen_pos):
        """右键出售装备"""
        game = self.game
        hero = game.player_hero
        if not hero or not hero.alive:
            return
        # 检查是否点击了装备槽
        item_rects = getattr(game.hud, '_item_rects', {})
        mx, my = screen_pos
        for idx, rect in item_rects.items():
            if rect.collidepoint(mx, my) and idx < len(hero.items):
                game.sell_item(hero, idx)
                return

    def _handle_shop_toggle(self):
        """B键开关商店（60秒后可用）"""
        game = self.game
        hero = game.player_hero
        if not hero or not hero.alive:
            return
        if game.game_time < 60:
            game.add_floating_text(hero.x, hero.y - 30, f'商店{60-int(game.game_time)}秒后开放', False, '#888')
            return
        if game.shop_open:
            game.close_shop()
        else:
            game.open_shop()

    def _handle_shop_click(self, screen_pos):
        """在商店界面点击购买物品"""
        game = self.game
        hero = game.player_hero
        if not hero or not hero.alive:
            return
        mx, my = screen_pos
        # 商店物品由 HUD 渲染，检查点击
        shop_rects = getattr(game.hud, '_shop_item_rects', [])
        for i, rect in enumerate(shop_rects):
            if rect.collidepoint(mx, my):
                game.buy_item(hero, i)
                return
        # 点击关闭按钮或空白区域关闭商店
        close_rect = getattr(game.hud, '_shop_close_rect', None)
        if close_rect and close_rect.collidepoint(mx, my):
            game.close_shop()
