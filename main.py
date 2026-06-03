#!/usr/bin/env python3
"""三线对决 - MOBA (Python/Pygame 版) — 明亮简约风格启动界面"""

import subprocess
import math
import json
import os
import pygame as pg
from config import HERO_TYPES, LLM_SETTINGS
from utils import get_font

# ====== LLM 设置持久化 ======
_SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.llm_settings.json')

def _load_llm_settings():
    """从磁盘加载上次保存的 LLM 设置"""
    try:
        with open(_SETTINGS_PATH, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        merged = dict(LLM_SETTINGS)
        merged.update(saved)
        return merged
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return dict(LLM_SETTINGS)

def _save_llm_settings(settings):
    """将 LLM 设置保存到磁盘"""
    try:
        with open(_SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ====== 配色方案 (明亮简约) ======
CLR = {
    'bg':          '#F0F2F5',
    'panel':       '#FFFFFF',
    'panel_dark':  '#F8F9FB',
    'text':        '#1A1A2E',
    'text_dim':    '#6B7280',
    'accent':      '#4A90D9',
    'accent_light':'#E8F0FE',
    'success':     '#10B981',
    'error':       '#EF4444',
    'warning':     '#F59E0B',
    'border':      '#D1D5DB',
    'border_light':'#E5E7EB',
    'input_bg':    '#F9FAFB',
}

W, H = 1300, 750

# ====== 绘制辅助 ======

def _draw_panel(screen, x, y, w, h, color=None, radius=12, border=None):
    c = color or CLR['panel']
    s = pg.Surface((w, h), pg.SRCALPHA)
    rgb = _hex_to_rgb(c)
    pg.draw.rect(s, rgb + (255,), (0, 0, w, h), border_radius=radius)
    if border:
        pg.draw.rect(s, _hex_to_rgb(border) + (255,), (0, 0, w, h), border_radius=radius, width=1)
    screen.blit(s, (x, y))

class TextInputField:
    """带光标和选区支持的文本输入字段"""
    def __init__(self, text='', max_len=500):
        self.text = text
        self.cursor = len(text)
        self.sel_start = None
        self.sel_end = None
        self.max_len = max_len

    def insert(self, char):
        if self.has_selection():
            self._delete_selection()
        if len(self.text) < self.max_len:
            self.text = self.text[:self.cursor] + char + self.text[self.cursor:]
            self.cursor += 1

    def insert_text(self, s):
        if self.has_selection():
            self._delete_selection()
        for c in s:
            if len(self.text) < self.max_len:
                self.text = self.text[:self.cursor] + c + self.text[self.cursor:]
                self.cursor += 1

    def delete_back(self):
        if self.has_selection():
            self._delete_selection()
            return
        if self.cursor > 0:
            self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
            self.cursor -= 1

    def delete_forward(self):
        if self.has_selection():
            self._delete_selection()
            return
        if self.cursor < len(self.text):
            self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]

    def select_all(self):
        self.sel_start = 0
        self.sel_end = len(self.text)

    def clear_selection(self):
        self.sel_start = None
        self.sel_end = None

    def has_selection(self):
        return (self.sel_start is not None and self.sel_end is not None
                and self.sel_start != self.sel_end)

    def clear(self):
        self.text = ''
        self.cursor = 0
        self.sel_start = None
        self.sel_end = None

    def set_text(self, text):
        self.text = text
        self.cursor = len(text)
        self.sel_start = None
        self.sel_end = None

    def move_cursor(self, delta):
        self.clear_selection()
        self.cursor = max(0, min(len(self.text), self.cursor + delta))

    def move_cursor_home(self):
        self.clear_selection()
        self.cursor = 0

    def move_cursor_end(self):
        self.clear_selection()
        self.cursor = len(self.text)

    def _delete_selection(self):
        s, e = min(self.sel_start, self.sel_end), max(self.sel_start, self.sel_end)
        self.text = self.text[:s] + self.text[e:]
        self.cursor = s
        self.sel_start = None
        self.sel_end = None


def _draw_input_box(screen, x, y, w, h, text, active, masked=False, show_mask=False,
                    placeholder='', cursor_pos=None, sel_range=None, has_clear=False):
    border_c = CLR['accent'] if active else CLR['border']
    bg_c = _hex_to_rgb('#FFFFFF' if active else CLR['input_bg'])
    pg.draw.rect(screen, bg_c, (x, y, w, h), border_radius=6)
    pg.draw.rect(screen, _hex_to_rgb(border_c), (x, y, w, h), border_radius=6, width=2)
    font = get_font(14)
    text_x = x + 10
    text_w = w - 20 - (20 if has_clear else 0)
    max_chars = max(1, text_w // 9)
    cp = cursor_pos if cursor_pos is not None else len(text)

    if text:
        if masked and not show_mask:
            display = '*' * min(len(text), 200)
        else:
            display = text

        # 滚动：让光标位置可见
        start = 0
        if len(display) > max_chars:
            if cp >= max_chars:
                start = cp - max_chars + 1
            display_vis = display[start:start + max_chars]
        else:
            display_vis = display[:max_chars]
            if len(display) > max_chars:
                display_vis = display[:max_chars - 3] + '...'

        # 选区高亮
        if sel_range and active:
            ss, se = sel_range
            if ss is not None and se is not None and ss != se:
                s0, s1 = min(ss, se), max(ss, se)
                vis_s = max(0, s0 - start)
                vis_e = min(len(display_vis), s1 - start)
                if vis_e > vis_s:
                    sel_x1 = text_x + font.render(display_vis[:vis_s], True, (0, 0, 0)).get_width()
                    sel_x2 = text_x + font.render(display_vis[:vis_e], True, (0, 0, 0)).get_width()
                    sel_surf = pg.Surface((max(1, sel_x2 - sel_x1), h - 8), pg.SRCALPHA)
                    sel_surf.fill((74, 144, 217, 60))
                    screen.blit(sel_surf, (sel_x1, y + 4))

        txt_s = font.render(display_vis, True, _hex_to_rgb(CLR['text']))
        screen.blit(txt_s, (text_x, y + h // 2 - txt_s.get_height() // 2))
    elif placeholder:
        ph_s = get_font(12).render(placeholder, True, _hex_to_rgb(CLR['text_dim']))
        screen.blit(ph_s, (text_x, y + h // 2 - ph_s.get_height() // 2))

    if active:
        cursor_x = text_x
        if text:
            if masked and not show_mask:
                d4c = '*' * min(len(text), 200)
            else:
                d4c = text
            if len(d4c) > max_chars:
                c_start = max(0, cp - max_chars + 1) if cp >= max_chars else 0
            else:
                c_start = 0
            cursor_x += font.render(d4c[c_start:cp], True, (0, 0, 0)).get_width()
        if cursor_x > x + w - 10 - (20 if has_clear else 0):
            cursor_x = x + w - 10 - (20 if has_clear else 0)
        pg.draw.line(screen, _hex_to_rgb(CLR['accent']),
                     (cursor_x, y + 8), (cursor_x, y + h - 8), 2)

    # 清除按钮 (×)
    if has_clear and text:
        btn_x = x + w - 22
        btn_cy = y + h // 2
        pg.draw.circle(screen, _hex_to_rgb(CLR['border']), (btn_x + 7, btn_cy), 8)
        x_s = get_font(11, bold=True).render('×', True, _hex_to_rgb('#FFFFFF'))
        screen.blit(x_s, (btn_x + 7 - x_s.get_width() // 2, btn_cy - x_s.get_height() // 2))

def _draw_button(screen, x, y, w, h, text, primary=True, enabled=True, small=False):
    if not enabled:
        bg = _hex_to_rgb('#D1D5DB'); txt_c = _hex_to_rgb('#9CA3AF')
    elif primary:
        bg = _hex_to_rgb(CLR['accent']); txt_c = (255, 255, 255)
    else:
        bg = _hex_to_rgb('#E5E7EB'); txt_c = _hex_to_rgb(CLR['text'])
    pg.draw.rect(screen, bg, (x, y, w, h), border_radius=8)
    fs = 13 if small else 16
    txt_s = get_font(fs, bold=True).render(text, True, txt_c)
    screen.blit(txt_s, (x + w // 2 - txt_s.get_width() // 2,
                        y + h // 2 - txt_s.get_height() // 2))

def _draw_arrow_left(screen, x, y, size, color):
    c = _hex_to_rgb(color); hw = size // 2
    pts = [(x + hw, y - hw), (x - hw // 2, y), (x + hw, y + hw)]
    pg.draw.polygon(screen, c, pts)

def _draw_arrow_right(screen, x, y, size, color):
    c = _hex_to_rgb(color); hw = size // 2
    pts = [(x - hw, y - hw), (x + hw // 2, y), (x - hw, y + hw)]
    pg.draw.polygon(screen, c, pts)

def _draw_checkbox(screen, x, y, size, checked, color):
    c = _hex_to_rgb(color if checked else CLR['border']); r = size // 2
    if checked:
        pg.draw.rect(screen, c, (x - r, y - r, size, size), border_radius=3)
        pg.draw.line(screen, (255,255,255), (x - r + 3, y), (x - 1, y + r - 2), 2)
        pg.draw.line(screen, (255,255,255), (x - 1, y + r - 2), (x + r - 2, y - r + 3), 2)
    else:
        pg.draw.rect(screen, c, (x - r, y - r, size, size), border_radius=3, width=2)

def _draw_status_dot(screen, x, y, ok, size=10):
    c = _hex_to_rgb(CLR['success'] if ok else CLR['error'])
    pg.draw.circle(screen, c, (x, y), size // 2)
    pg.draw.circle(screen, (255,255,255), (x, y), size // 4)

def _draw_chip(screen, x, y, w, h, text, selected=False, color=None):
    """圆角药丸按钮 — selected 时填充强调色"""
    base_c = color or CLR['accent']
    if selected:
        bg = _hex_to_rgb(base_c); txt_c = (255, 255, 255)
    else:
        bg = _hex_to_rgb(CLR['input_bg']); txt_c = _hex_to_rgb(CLR['text_dim'])
    pg.draw.rect(screen, bg, (x, y, w, h), border_radius=h // 2)
    if not selected:
        pg.draw.rect(screen, _hex_to_rgb(CLR['border']), (x, y, w, h), border_radius=h // 2, width=1)
    txt_s = get_font(13, bold=selected).render(text, True, txt_c)
    screen.blit(txt_s, (x + w // 2 - txt_s.get_width() // 2,
                        y + h // 2 - txt_s.get_height() // 2))

def _draw_section_label(screen, x, y, text):
    """带左侧竖线的段落标题"""
    pg.draw.rect(screen, _hex_to_rgb(CLR['accent']), (x, y + 2, 3, 14), border_radius=1)
    _left_text(screen, text, x + 10, y, size=13, bold=True, color=CLR['text'])

def _draw_divider(screen, x, y, w):
    pg.draw.line(screen, _hex_to_rgb(CLR['border_light']), (x, y), (x + w, y), 1)

WEAPON_CN = {
    'sword':'剑','staff':'杖','bow':'弓','dagger':'匕首',
    'mace':'锤','scythe':'镰','claw':'爪','axe':'斧',
}

def _attack_style(ht):
    r = ht['range']
    if r >= 200: return '远程', '#4A90D9'
    elif r < 150: return '近战', '#F59E0B'
    else: return '中程', '#8B5CF6'

def _hex_to_rgb(h):
    if isinstance(h, tuple): return h
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _center_text(screen, text, y, size=18, color=None, bold=False):
    c = color or CLR['text']
    s = get_font(size, bold=bold).render(text, True, _hex_to_rgb(c))
    screen.blit(s, (W // 2 - s.get_width() // 2, y))
    return s

def _left_text(screen, text, x, y, size=16, color=None, bold=False):
    c = color or CLR['text']
    s = get_font(size, bold=bold).render(text, True, _hex_to_rgb(c))
    screen.blit(s, (x, y))
    return s


# ====== LLM 连接测试 ======

_test_result = None

def _run_test_connection(provider_id, api_key, api_url_override, model):
    global _test_result
    _test_result = 'testing'
    try:
        from systems.llm_ai import LLMAIController
        success, msg, used_model = LLMAIController.test_connection(
            provider_id, api_key, api_url_override, model)
        _test_result = (success, msg, used_model)
    except Exception as e:
        _test_result = (False, f'测试异常: {str(e)[:200]}', '')

def _get_clipboard():
    """跨平台剪贴板"""
    import sys
    # 1) subprocess (macOS / Linux / Windows)
    try:
        if sys.platform == 'darwin':
            r = subprocess.run(['pbpaste'], capture_output=True, text=True, timeout=1)
            if r.returncode == 0 and r.stdout: return r.stdout.strip()
        elif sys.platform == 'win32':
            r = subprocess.run(['powershell', '-Command', 'Get-Clipboard'], capture_output=True, text=True, timeout=2)
            if r.returncode == 0 and r.stdout: return r.stdout.strip()
        else:
            for cmd in (['xclip', '-selection', 'clipboard', '-o'], ['xsel', '-b']):
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1)
                    if r.returncode == 0 and r.stdout: return r.stdout.strip()
                except Exception: continue
    except Exception: pass
    # 2) tkinter fallback
    try:
        import tkinter as tk
        root = tk.Tk(); root.withdraw()
        txt = root.clipboard_get(); root.destroy()
        return txt.strip() if txt else ''
    except Exception: pass
    # 3) pygame.scrap (last resort)
    try:
        for t in [pg.SCRAP_TEXT, 'text/plain;charset=utf-8', 'text/plain']:
            try:
                if hasattr(pg.scrap, 'get_text'):
                    txt = pg.scrap.get_text(t)
                else:
                    txt = pg.scrap.get(t)
                if txt:
                    return txt.decode('utf-8', errors='replace') if isinstance(txt, bytes) else txt
            except Exception: continue
    except Exception: pass
    return ''


# ====== LLM AI 设置界面 ======

def _fill_settings(settings, api_key, api_url, model, interval_str,
                   provider, team, position_options, pos_checks):
    """填充 LLM 设置字典并持久化"""
    settings['api_key'] = api_key
    settings['api_url_override'] = api_url
    settings['model'] = model
    try:
        val = float(interval_str)
        settings['interval'] = max(1.0, min(30.0, val))
    except ValueError:
        settings['interval'] = 8.0
    settings['provider'] = provider
    settings['control_team'] = team
    settings['enabled'] = bool(api_key.strip())
    settings['control_positions'] = [p for p in position_options if pos_checks.get(p)]
    _save_llm_settings(settings)


def show_llm_setup(screen):
    global _test_result
    from systems.llm_config import LLM_PROVIDERS, DEFAULT_LLM_SETTINGS
    import threading

    # 启用文本输入（macOS IME 支持）
    if hasattr(pg.key, 'start_text_input'):
        pg.key.start_text_input()

    _test_result = None
    settings = _load_llm_settings()
    providers = list(LLM_PROVIDERS.keys())
    prov_idx = providers.index(settings['provider'])
    teams = ['red', 'blue', 'both']
    team_idx = teams.index(settings['control_team'])
    position_options = ['all', 'top', 'mid', 'bottom', 'jungle']
    pos_checks = {p: p in settings.get('control_positions', ['all']) for p in position_options}
    show_key = False
    clock = pg.time.Clock()
    test_thread = None
    error_msg = ''
    error_timer = 0.0

    active_field = None
    FIELD_ORDER = ['api_key', 'api_url', 'model', 'interval']

    # 用 TextInputField 管理各输入框状态
    fields = {
        'api_key':  TextInputField(settings.get('api_key', '')),
        'api_url':  TextInputField(settings.get('api_url_override', '')),
        'model':    TextInputField(settings.get('model', '')),
        'interval': TextInputField(str(settings.get('interval', 8.0)), max_len=10),
    }

    # 检测 TEXTINPUT 事件是否可用
    _textinput_received = False

    # 布局
    PANEL_W, PANEL_H = 760, 560
    PX = (W - PANEL_W) // 2
    PY = 80
    LX = PX + 32
    RX = PX + 140
    RW = PANEL_W - 172

    # 输入框 Rect（用于点击检测）
    FIELDS_RECT = {
        'api_key':  pg.Rect(RX, PY + 128, RW, 32),
        'api_url':  pg.Rect(RX, PY + 185, RW, 32),
        'model':    pg.Rect(RX, PY + 242, RW, 32),
        'interval': pg.Rect(RX, PY + 299, 90, 32),
    }

    # 清除按钮 Rect
    CLEAR_BTNS = {
        'api_key':  pg.Rect(RX + RW - 22, PY + 130, 18, 28),
        'api_url':  pg.Rect(RX + RW - 22, PY + 187, 18, 28),
        'model':    pg.Rect(RX + RW - 22, PY + 244, 18, 28),
        'interval': None,
    }

    # 提供商 chip 布局（预计算）
    prov_chip_gap = 8
    prov_chips = []
    cx = RX
    for pid in providers:
        pname = LLM_PROVIDERS[pid]['name']
        tw = get_font(13, bold=True).render(pname, True, (0,0,0)).get_width()
        cw = tw + 24
        prov_chips.append((cx, PY + 62, cw, 28))
        cx += cw + prov_chip_gap

    # 队伍 chip 布局
    team_labels = {'red': '红方', 'blue': '蓝方', 'both': '双方'}
    team_colors = {'red': '#EF4444', 'blue': '#3B82F6', 'both': '#8B5CF6'}
    team_chip_gap = 8
    team_chips = []
    cx = RX
    for tid in teams:
        tw = get_font(13, bold=True).render(team_labels[tid], True, (0,0,0)).get_width()
        cw = tw + 24
        team_chips.append((cx, PY + 390, cw, 28))
        cx += cw + team_chip_gap

    # 位置 chip 布局
    pos_labels = {'all': '全部', 'top': '上路', 'mid': '中路', 'bottom': '下路', 'jungle': '野区'}
    pos_chip_gap = 8
    pos_chips = []
    cx = RX
    for pid in position_options:
        tw = get_font(13, bold=True).render(pos_labels[pid], True, (0,0,0)).get_width()
        cw = tw + 20
        pos_chips.append((cx, PY + 435, cw, 26))
        cx += cw + pos_chip_gap

    def _stop_text_input():
        if hasattr(pg.key, 'stop_text_input'):
            pg.key.stop_text_input()

    while True:
        dt = clock.tick(30) / 1000.0
        mx, my = pg.mouse.get_pos()
        if error_timer > 0:
            error_timer -= dt

        if test_thread and not test_thread.is_alive():
            test_thread = None

        for event in pg.event.get():
            if event.type == pg.QUIT:
                _stop_text_input()
                return None

            # TEXTINPUT 事件（macOS IME 更兼容）
            if hasattr(pg, 'TEXTINPUT') and event.type == pg.TEXTINPUT:
                _textinput_received = True
                if active_field and active_field in fields:
                    f = fields[active_field]
                    if active_field == 'interval':
                        for c in event.text:
                            if c in '0123456789.':
                                f.insert(c)
                    else:
                        f.insert_text(event.text)
                continue

            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                # 清除按钮
                clear_clicked = False
                for fname, btn_rect in CLEAR_BTNS.items():
                    if btn_rect and btn_rect.collidepoint(mx, my):
                        fields[fname].clear()
                        active_field = fname
                        clear_clicked = True
                        break
                if clear_clicked:
                    continue

                # 提供商 chip
                for i, (cx_, cy_, cw_, ch_) in enumerate(prov_chips):
                    if cx_ <= mx <= cx_ + cw_ and cy_ <= my <= cy_ + ch_:
                        old_prov = providers[prov_idx]
                        prov_idx = i
                        if providers[prov_idx] != old_prov:
                            fields['api_url'].clear()
                            fields['model'].set_text('')
                        break

                # 输入框焦点
                clicked_field = None
                for fname, frect in FIELDS_RECT.items():
                    if frect.collidepoint(mx, my):
                        clicked_field = fname
                        break
                if clicked_field:
                    active_field = clicked_field
                    fields[clicked_field].clear_selection()
                    # 点击输入框时将光标移到末尾
                    fields[clicked_field].cursor = len(fields[clicked_field].text)
                else:
                    panel_rect = pg.Rect(PX, PY, PANEL_W, PANEL_H)
                    if not panel_rect.collidepoint(mx, my):
                        active_field = None

                # 队伍 chip
                for i, (cx_, cy_, cw_, ch_) in enumerate(team_chips):
                    if cx_ <= mx <= cx_ + cw_ and cy_ <= my <= cy_ + ch_:
                        team_idx = i
                        break

                # 位置 chip
                for i, (cx_, cy_, cw_, ch_) in enumerate(pos_chips):
                    if cx_ <= mx <= cx_ + cw_ and cy_ <= my <= cy_ + ch_:
                        p = position_options[i]
                        pos_checks[p] = not pos_checks[p]
                        if p == 'all' and pos_checks[p]:
                            for pp in position_options:
                                if pp != 'all': pos_checks[pp] = False
                        break

                # 测试连接
                test_btn_rect = pg.Rect(RX, PY + 492, 110, 32)
                if test_btn_rect.collidepoint(mx, my):
                    if _test_result != 'testing':
                        t = threading.Thread(
                            target=_run_test_connection,
                            args=(providers[prov_idx], fields['api_key'].text,
                                  fields['api_url'].text, fields['model'].text),
                            daemon=True)
                        test_thread = t; t.start()

                # 开始游戏
                start_btn_rect = pg.Rect(PX + PANEL_W - 148, PY + 492, 120, 32)
                if start_btn_rect.collidepoint(mx, my):
                    if not fields['api_key'].text.strip():
                        error_msg = '请输入 API Key 或点击下方跳过'
                        error_timer = 3.0
                        active_field = 'api_key'
                        continue
                    _fill_settings(settings, fields['api_key'].text, fields['api_url'].text,
                                   fields['model'].text, fields['interval'].text,
                                   providers[prov_idx], teams[team_idx],
                                   position_options, pos_checks)
                    _stop_text_input()
                    return settings

                # 跳过
                skip_rect = pg.Rect(W // 2 - 70, PY + PANEL_H + 10, 140, 38)
                if skip_rect.collidepoint(mx, my):
                    settings['enabled'] = False
                    _stop_text_input()
                    return settings

            if event.type == pg.KEYDOWN:
                ctrl = event.mod & (pg.KMOD_CTRL | pg.KMOD_META)

                if event.key == pg.K_TAB:
                    if active_field in FIELD_ORDER:
                        idx = FIELD_ORDER.index(active_field)
                        active_field = FIELD_ORDER[(idx + 1) % len(FIELD_ORDER)]
                    else:
                        active_field = FIELD_ORDER[0]
                    continue

                # 粘贴 (Ctrl+V)
                if event.key == pg.K_v and ctrl:
                    clip = _get_clipboard()
                    if clip:
                        target = active_field or 'api_key'
                        active_field = target  # 关键修复：粘贴后激活目标字段
                        parts = [p.strip() for p in clip.strip().replace('\n', '').split(',')]
                        if len(parts) >= 2 and parts[0] in LLM_PROVIDERS:
                            prov_idx = providers.index(parts[0])
                            fields['api_key'].set_text(parts[1])
                            fields['api_url'].set_text(parts[2] if len(parts) > 2 else '')
                            if len(parts) > 3:
                                fields['model'].set_text(parts[3])
                        else:
                            if target == 'interval':
                                filtered = ''.join(c for c in clip if c in '0123456789.')
                                fields[target].insert_text(filtered)
                            else:
                                fields[target].insert_text(clip)
                    continue

                if event.key == pg.K_ESCAPE:
                    _stop_text_input()
                    return None

                # 输入字段编辑
                if active_field and active_field in fields:
                    f = fields[active_field]

                    # Ctrl+A 全选
                    if event.key == pg.K_a and ctrl:
                        f.select_all()
                        continue

                    # 退格
                    if event.key == pg.K_BACKSPACE:
                        f.delete_back()
                        continue

                    # 前进删除
                    if event.key == pg.K_DELETE:
                        f.delete_forward()
                        continue

                    # 光标移动
                    if event.key == pg.K_LEFT:
                        f.move_cursor(-1)
                        continue
                    if event.key == pg.K_RIGHT:
                        f.move_cursor(1)
                        continue
                    if event.key == pg.K_HOME:
                        f.move_cursor_home()
                        continue
                    if event.key == pg.K_END:
                        f.move_cursor_end()
                        continue

                    # Ctrl+H 显示/隐藏 Key
                    if active_field == 'api_key' and event.key == pg.K_h and ctrl:
                        show_key = not show_key
                        continue

                    # 字符输入（TEXTINPUT 不可用时的回退方案）
                    if not _textinput_received and event.unicode and event.unicode.isprintable():
                        if active_field == 'interval':
                            if event.unicode in '0123456789.':
                                f.insert(event.unicode)
                        else:
                            f.insert(event.unicode)
                        continue

                if event.key == pg.K_RETURN:
                    if not fields['api_key'].text.strip():
                        error_msg = '请输入 API Key 或点击下方跳过'
                        error_timer = 3.0
                        active_field = 'api_key'
                        continue
                    _fill_settings(settings, fields['api_key'].text, fields['api_url'].text,
                                   fields['model'].text, fields['interval'].text,
                                   providers[prov_idx], teams[team_idx],
                                   position_options, pos_checks)
                    _stop_text_input()
                    return settings

        # ====== 渲染 ======
        screen.fill(_hex_to_rgb(CLR['bg']))

        _center_text(screen, '三线对决 — AI 指挥官设置', 25, size=26, color=CLR['text'], bold=True)
        _center_text(screen, '配置大模型来控制人机英雄的战术决策', 55, size=13, color=CLR['text_dim'])

        _draw_panel(screen, PX, PY, PANEL_W, PANEL_H, color=CLR['panel'], border=CLR['border_light'])

        # ── 提供商 ──
        _draw_section_label(screen, LX, PY + 40, 'LLM 提供商')
        for i, (cx_, cy_, cw_, ch_) in enumerate(prov_chips):
            _draw_chip(screen, cx_, cy_, cw_, ch_, LLM_PROVIDERS[providers[i]]['name'],
                       selected=i == prov_idx)
        prov = LLM_PROVIDERS[providers[prov_idx]]
        _left_text(screen, prov.get('api_url', ''), RX, PY + 95, size=11, color=CLR['text_dim'])

        # ── 连接配置 ──
        _draw_section_label(screen, LX, PY + 118, '连接配置')

        # API Key
        _left_text(screen, 'API Key', LX, PY + 132, size=12, color=CLR['text_dim'])
        f_ak = fields['api_key']
        _draw_input_box(screen, RX, PY + 128, RW, 32, f_ak.text,
                        active_field == 'api_key', masked=True, show_mask=show_key,
                        placeholder='粘贴或输入 API Key...',
                        cursor_pos=f_ak.cursor,
                        sel_range=(f_ak.sel_start, f_ak.sel_end),
                        has_clear=True)

        # API URL
        _left_text(screen, 'Base URL', LX, PY + 189, size=12, color=CLR['text_dim'])
        f_au = fields['api_url']
        url_placeholder = '' if f_au.text else f'默认: {prov.get("api_url", "")}'
        _draw_input_box(screen, RX, PY + 185, RW, 32, f_au.text,
                        active_field == 'api_url', placeholder=url_placeholder,
                        cursor_pos=f_au.cursor,
                        sel_range=(f_au.sel_start, f_au.sel_end),
                        has_clear=True)

        # 模型
        _left_text(screen, '模型', LX, PY + 246, size=12, color=CLR['text_dim'])
        f_md = fields['model']
        model_placeholder = '' if f_md.text else f'默认: {prov["default_model"]}'
        _draw_input_box(screen, RX, PY + 242, RW, 32, f_md.text,
                        active_field == 'model', placeholder=model_placeholder,
                        cursor_pos=f_md.cursor,
                        sel_range=(f_md.sel_start, f_md.sel_end),
                        has_clear=True)

        # 间隔
        _left_text(screen, '间隔', LX, PY + 303, size=12, color=CLR['text_dim'])
        f_iv = fields['interval']
        _draw_input_box(screen, RX, PY + 299, 90, 32, f_iv.text,
                        active_field == 'interval', placeholder='8',
                        cursor_pos=f_iv.cursor,
                        sel_range=(f_iv.sel_start, f_iv.sel_end))
        _left_text(screen, '秒 (推荐 5-10)', RX + 98, PY + 307, size=12, color=CLR['text_dim'])

        _draw_divider(screen, LX, PY + 350, PANEL_W - 64)

        # ── 控制范围 ──
        _draw_section_label(screen, LX, PY + 362, '控制范围')

        # 队伍
        _left_text(screen, '队伍', LX, PY + 394, size=12, color=CLR['text_dim'])
        for i, (cx_, cy_, cw_, ch_) in enumerate(team_chips):
            _draw_chip(screen, cx_, cy_, cw_, ch_, team_labels[teams[i]],
                       selected=i == team_idx, color=team_colors[teams[i]])

        # 位置
        _left_text(screen, '位置', LX, PY + 439, size=12, color=CLR['text_dim'])
        for i, (cx_, cy_, cw_, ch_) in enumerate(pos_chips):
            _draw_chip(screen, cx_, cy_, cw_, ch_, pos_labels[position_options[i]],
                       selected=pos_checks.get(position_options[i], False))

        _draw_divider(screen, LX, PY + 475, PANEL_W - 64)

        # ── 操作 ──
        _draw_section_label(screen, LX, PY + 487, '操作')

        _draw_button(screen, RX, PY + 492, 110, 32, '测试连接',
                     primary=False, enabled=_test_result != 'testing', small=True)

        if _test_result == 'testing':
            _left_text(screen, '连接中...', RX + 120, PY + 500, size=12, color=CLR['warning'])
        elif _test_result is not None:
            success, msg, used_model = _test_result
            _draw_status_dot(screen, RX + 122, PY + 508, success)
            first_line = msg.split('\n')[0]
            tc = CLR['success'] if success else CLR['error']
            _left_text(screen, first_line[:30], RX + 136, PY + 500, size=11, color=tc)
            if used_model:
                _left_text(screen, f'模型: {used_model}', RX + 136, PY + 514, size=10, color=CLR['text_dim'])

        _draw_button(screen, PX + PANEL_W - 148, PY + 492, 120, 32, '开始游戏 ▶', primary=True, small=True)

        # 错误提示
        if error_timer > 0 and error_msg:
            alpha = min(255, int(error_timer * 255))
            err_surf = get_font(13, bold=True).render(error_msg, True, _hex_to_rgb(CLR['error']))
            err_bg = pg.Surface((err_surf.get_width() + 20, err_surf.get_height() + 10), pg.SRCALPHA)
            err_bg.fill((255, 240, 240, min(230, alpha)))
            screen.blit(err_bg, (PX + PANEL_W // 2 - err_bg.get_width() // 2, PY - 35))
            err_surf.set_alpha(alpha)
            screen.blit(err_surf, (PX + PANEL_W // 2 - err_surf.get_width() // 2, PY - 30))

        skip_y = PY + PANEL_H + 10
        _draw_button(screen, W // 2 - 70, skip_y, 140, 38, '跳过 (离线模式)', primary=False)

        _center_text(screen, 'Tab 切换 | ←→ 移动光标 | Ctrl+V 粘贴 | Ctrl+A 全选 | Enter 开始 | ESC 退出',
                     H - 22, size=11, color=CLR['text_dim'])
        pg.display.flip()


# ====== 英雄选择界面 ======

def show_hero_selection(screen):
    types_list = list(HERO_TYPES.keys())
    n = len(types_list)
    selected = 0
    clock = pg.time.Clock()

    cols = 4
    card_w, card_h = 150, 170
    gap_x, gap_y = 24, 20
    total_w = cols * card_w + (cols - 1) * gap_x
    start_x = (W - total_w) // 2
    rows = (n + cols - 1) // cols
    total_h = rows * card_h + (rows - 1) * gap_y
    start_y = 115
    detail_y = start_y + total_h + 20
    anim_t = 0.0

    while True:
        dt = clock.tick(30) / 1000.0
        anim_t += dt
        mx, my = pg.mouse.get_pos()

        for event in pg.event.get():
            if event.type == pg.QUIT: return None
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_LEFT: selected = (selected - 1) % n
                elif event.key == pg.K_RIGHT: selected = (selected + 1) % n
                elif event.key == pg.K_UP: selected = (selected - cols) % n
                elif event.key == pg.K_DOWN: selected = (selected + cols) % n
                elif event.key in (pg.K_RETURN, pg.K_SPACE): return types_list[selected]
                elif event.key == pg.K_ESCAPE: return None
            if event.type == pg.MOUSEBUTTONDOWN:
                for i in range(n):
                    col = i % cols; row = i // cols
                    cx = start_x + col * (card_w + gap_x) + card_w // 2
                    cy = start_y + row * (card_h + gap_y) + card_h // 2
                    if abs(mx - cx) < card_w // 2 and abs(my - cy) < card_h // 2:
                        if i == selected and event.button == 1:
                            return types_list[selected]
                        selected = i

        screen.fill(_hex_to_rgb(CLR['bg']))
        _center_text(screen, '选择英雄', 28, size=28, color=CLR['text'], bold=True)
        _center_text(screen, '点击选择，再次点击或 Enter 确认', 60, size=13, color=CLR['text_dim'])

        for i, ht_id in enumerate(types_list):
            ht = HERO_TYPES[ht_id]
            col = i % cols; row = i // cols
            card_x = start_x + col * (card_w + gap_x)
            card_y = start_y + row * (card_h + gap_y)
            is_sel = i == selected

            pulse = 1.0 + math.sin(anim_t * 4) * 0.03 if is_sel else 1.0

            # 卡片背景
            card_color = '#EBF3FD' if is_sel else CLR['panel']
            card_border = CLR['accent'] if is_sel else CLR['border_light']
            _draw_panel(screen, card_x, card_y, card_w, card_h,
                        color=card_color, border=card_border, radius=10)

            # 左侧色条
            body_rgb = _hex_to_rgb(ht['bodyColor'])
            bar_surf = pg.Surface((4, card_h - 20), pg.SRCALPHA)
            bar_surf.fill(body_rgb + (255,))
            screen.blit(bar_surf, (card_x + 6, card_y + 10))

            # 英雄图标
            icon_cx = card_x + card_w // 2
            icon_cy = card_y + 50
            icon_bg = body_rgb
            icon_bg_light = tuple(min(255, c + 50) for c in icon_bg)
            pg.draw.circle(screen, icon_bg_light, (icon_cx, icon_cy), int(30 * pulse))
            pg.draw.circle(screen, icon_bg, (icon_cx, icon_cy), int(30 * pulse), width=3)
            icon_s = get_font(20, bold=True).render(ht['icon'], True, (255,255,255))
            screen.blit(icon_s, (icon_cx - icon_s.get_width() // 2, icon_cy - icon_s.get_height() // 2))

            # 名字
            name_c = CLR['accent'] if is_sel else CLR['text']
            name_s = get_font(15, bold=True).render(ht['name'], True, _hex_to_rgb(name_c))
            screen.blit(name_s, (card_x + card_w // 2 - name_s.get_width() // 2, card_y + 88))

            # 角色标签
            atk_style, style_c = _attack_style(ht)
            style_s = get_font(10).render(atk_style, True, _hex_to_rgb(style_c))
            sw = style_s.get_width() + 12
            chip_x = card_x + card_w // 2 - sw // 2
            pg.draw.rect(screen, _hex_to_rgb(style_c) + (30,) if len(_hex_to_rgb(style_c)) == 3 else _hex_to_rgb(style_c),
                         (chip_x, card_y + 108, sw, 18), border_radius=9)
            style_bg = pg.Surface((sw, 18), pg.SRCALPHA)
            sc = _hex_to_rgb(style_c)
            style_bg.fill(sc + (30,))
            pg.draw.rect(style_bg, sc + (60,), (0, 0, sw, 18), border_radius=9)
            screen.blit(style_bg, (chip_x, card_y + 108))
            screen.blit(style_s, (chip_x + 6, card_y + 109))

            # 简略属性
            wp = WEAPON_CN.get(ht['weapon'], ht['weapon'])
            stat_s = get_font(10).render(f'{wp} HP{ht["hp"]} ATK{ht["atk"]}', True, _hex_to_rgb(CLR['text_dim']))
            screen.blit(stat_s, (card_x + card_w // 2 - stat_s.get_width() // 2, card_y + 132))

        # ── 选中英雄详情 ──
        sel_ht = HERO_TYPES[types_list[selected]]
        detail_w = total_w + 20
        detail_x = (W - detail_w) // 2
        _draw_panel(screen, detail_x, detail_y, detail_w, 110,
                    color=CLR['panel'], border=CLR['border_light'], radius=10)

        # 左: 英雄名 + 属性
        left_x = detail_x + 20
        body_rgb = _hex_to_rgb(sel_ht['bodyColor'])
        name_big = get_font(22, bold=True).render(sel_ht['name'], True, body_rgb)
        screen.blit(name_big, (left_x, detail_y + 12))

        wp = WEAPON_CN.get(sel_ht['weapon'], sel_ht['weapon'])
        atk_style, _ = _attack_style(sel_ht)
        stats_str = f'{atk_style} | {wp} | HP {sel_ht["hp"]} | ATK {sel_ht["atk"]} | SPD {sel_ht["speed"]} | 射程 {sel_ht["range"]}'
        stats_s = get_font(12).render(stats_str, True, _hex_to_rgb(CLR['text_dim']))
        screen.blit(stats_s, (left_x, detail_y + 40))

        # 技能卡片
        ab = sel_ht['abilities']
        ab_card_w = 175; ab_card_h = 50; ab_gap = 12
        ab_start_x = left_x
        ab_y = detail_y + 58
        for ki, key in enumerate(['q', 'w', 'e']):
            a = ab[key]; lb = {'q':'Q','w':'W','e':'E'}[key]
            ax = ab_start_x + ki * (ab_card_w + ab_gap)
            # 技能小卡片
            _draw_panel(screen, ax, ab_y, ab_card_w, ab_card_h,
                        color=CLR['input_bg'], border=CLR['border_light'], radius=8)
            # 按键标签
            lb_s = get_font(14, bold=True).render(lb, True, body_rgb)
            screen.blit(lb_s, (ax + 8, ab_y + 4))
            # 技能名
            ab_name_s = get_font(12, bold=True).render(a['name'], True, _hex_to_rgb(CLR['text']))
            screen.blit(ab_name_s, (ax + 28, ab_y + 5))
            # CD / DMG
            ab_info_s = get_font(10).render(f'CD {a["cd"]}s  DMG {a["dmg"]}', True, _hex_to_rgb(CLR['text_dim']))
            screen.blit(ab_info_s, (ax + 28, ab_y + 25))

        _center_text(screen, '方向键 / 点击选择   Enter/Space 确认   ESC 返回',
                     H - 28, size=11, color=CLR['text_dim'])
        pg.display.flip()


# ====== 游戏结束菜单 ======

def show_game_over_menu(screen, winner):
    clock = pg.time.Clock()
    card_w, card_h = 400, 300
    card_x = (W - card_w) // 2; card_y = (H - card_h) // 2
    anim_t = 0.0

    # 保存最后一帧游戏画面，避免每帧叠加 overlay 导致画面撕裂
    bg_snapshot = screen.copy()

    while True:
        dt = clock.tick(30) / 1000.0
        anim_t += dt
        mx, my = pg.mouse.get_pos()

        for event in pg.event.get():
            if event.type == pg.QUIT: return 'quit'
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_r: return 'restart'
                if event.key in (pg.K_q, pg.K_ESCAPE): return 'quit'
            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                btn_y = card_y + 180
                if btn_y < my < btn_y + 40:
                    if card_x + 50 < mx < card_x + 190: return 'restart'
                    if card_x + 210 < mx < card_x + 350: return 'quit'

        # 每帧先恢复干净画面，再叠一层 overlay
        screen.blit(bg_snapshot, (0, 0))
        overlay = pg.Surface((W, H), pg.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))

        _draw_panel(screen, card_x, card_y, card_w, card_h,
                    color=CLR['panel'], border=CLR['border_light'], radius=14)

        if winner == 'blue':
            title = 'VICTORY'
            title_c = CLR['accent']
            sub = '蓝方摧毁了所有敌方水晶!'
            glow_c = (74, 144, 217)
        else:
            title = 'DEFEAT'
            title_c = CLR['error']
            sub = '红方摧毁了所有己方水晶!'
            glow_c = (239, 68, 68)

        # 顶部装饰色条
        bar_surf = pg.Surface((card_w - 2, 6), pg.SRCALPHA)
        bar_surf.fill(glow_c + (255,))
        screen.blit(bar_surf, (card_x + 1, card_y + 1))

        # 标题
        title_s = get_font(36, bold=True).render(title, True, _hex_to_rgb(title_c))
        screen.blit(title_s, (card_x + card_w // 2 - title_s.get_width() // 2, card_y + 30))

        # 结果描述
        sub_s = get_font(15).render(sub, True, _hex_to_rgb(CLR['text_dim']))
        screen.blit(sub_s, (card_x + card_w // 2 - sub_s.get_width() // 2, card_y + 82))

        # 规则提示
        rule_s = get_font(12).render('胜利条件: 摧毁敌方全部 3 个水晶', True, _hex_to_rgb(CLR['text_dim']))
        screen.blit(rule_s, (card_x + card_w // 2 - rule_s.get_width() // 2, card_y + 110))

        _draw_divider(screen, card_x + 30, card_y + 140, card_w - 60)

        # 按钮
        _draw_button(screen, card_x + 50, card_y + 160, 140, 40, '再来一局 [R]', primary=True)
        _draw_button(screen, card_x + 210, card_y + 160, 140, 40, '退出游戏 [Q]', primary=False)

        hint_s = get_font(11).render('R 重新选择英雄 | Q/ESC 退出', True, _hex_to_rgb(CLR['text_dim']))
        screen.blit(hint_s, (card_x + card_w // 2 - hint_s.get_width() // 2, card_y + 220))

        pg.display.flip()


# ====== 主入口 ======

if __name__ == '__main__':
    pg.init()
    screen = pg.display.set_mode((W, H), pg.RESIZABLE | pg.SCALED, vsync=1)
    pg.display.set_caption('三线对决 - MOBA (Python版) [F11 全屏]')

    # 首次进入：LLM 设置
    llm_settings = show_llm_setup(screen)
    if llm_settings is None:
        pg.quit()
        raise SystemExit

    while True:
        hero_type = show_hero_selection(screen)
        if hero_type is None:
            # 返回 LLM 设置
            llm_settings = show_llm_setup(screen)
            if llm_settings is None:
                break
            continue

        from game import Game
        game = Game(hero_type, screen, llm_settings=llm_settings)
        game.run()

        if game.game_over:
            result = show_game_over_menu(screen, game.winner)
            if result == 'quit':
                break
            # result == 'restart' → 回到英雄选择
        else:
            # 非正常退出（ESC等）
            break

    pg.quit()
