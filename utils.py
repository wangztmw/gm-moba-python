"""工具函数"""
import math
import random
import warnings
import pygame as pg


def dist(a, b):
    """两点距离"""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def rnd(a, b):
    """随机浮点 [a, b)"""
    return a + random.random() * (b - a)


def rnd_int(a, b):
    """随机整数 [a, b] 闭区间"""
    return random.randint(a, b)


def clamp(v, mn, mx):
    return max(mn, min(mx, v))


def alpha_surf(w, h, draw_fn):
    """在临时 SRCALPHA surface 上绘制，返回 surface 可用于 blit"""
    s = pg.Surface((w, h), pg.SRCALPHA)
    draw_fn(s)
    return s


def rgb(c):
    """将 RGBA 转为 RGB（丢弃 alpha），适配 pg.draw 不接受 alpha 的旧 API"""
    if len(c) == 4:
        return c[:3]
    return c


# 中文字体候选 (macOS / Linux / Windows / 通用)
_CHINESE_FONT_NAMES = [
    'PingFang SC', 'PingFang HK', 'PingFang TC',
    'STHeiti', 'Heiti SC',
    'Hiragino Sans GB', 'Hiragino Sans CNS',
    'Apple SD Gothic Neo',
    'Noto Sans CJK SC', 'Noto Sans CJK',
    'Source Han Sans SC', 'Source Han Sans',
    'Microsoft YaHei', 'Microsoft JhengHei',
    'SimHei', 'simsun', 'FangSong',
    'WenQuanYi Micro Hei', 'WenQuanYi Zen Hei',
    'Droid Sans Fallback',
]
_CHINESE_FONT_NAME = None  # 惰性查找

def get_font(size, bold=False):
    """获取支持中文的字体，各平台通用。
    逐个候选字体尝试，选择第一个能渲染中文的。
    兜底策略：扫描系统字体目录找 TTF。
    """
    global _CHINESE_FONT_NAME
    if _CHINESE_FONT_NAME is not None:
        return pg.font.SysFont(_CHINESE_FONT_NAME, size, bold=bold)

    # ---- 尝试 SysFont ----
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for name in _CHINESE_FONT_NAMES:
            try:
                f = pg.font.SysFont(name, 12)
                s = f.render('中', True, (0, 0, 0))
                w = s.get_width()
                # 有效中文字体渲染 '中' 宽度应在 8~20px (12pt下)
                if 8 <= w <= 20:
                    _CHINESE_FONT_NAME = name
                    return pg.font.SysFont(name, size, bold=bold)
            except Exception:
                continue

    # ---- 扫描系统 TTF 目录 ----
    _CHINESE_FONT_NAME = _find_font_file()
    if _CHINESE_FONT_NAME:
        return pg.font.Font(_CHINESE_FONT_NAME, size)

    # ---- 最终兜底 ----
    _CHINESE_FONT_NAME = 'arial'
    print('⚠ 未找到中文字体，使用 arial 替代')
    return pg.font.SysFont('arial', size, bold=bold)


def _find_font_file():
    """扫描常见系统字体目录，返回第一个可用的中文字体文件路径"""
    import os
    search_dirs = [
        '/System/Library/Fonts',
        '/Library/Fonts',
        os.path.expanduser('~/Library/Fonts'),
        '/usr/share/fonts',
        '/usr/local/share/fonts',
    ]
    keywords = ['PingFang', 'STHeiti', 'Heiti', 'Hiragino', 'Noto', 'CJK',
                'SimHei', 'simsun', 'WenQuanYi', 'Droid Sans']
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for fname in os.listdir(d):
            lower = fname.lower()
            if any(kw.lower() in lower for kw in keywords):
                if fname.endswith(('.ttf', '.ttc', '.otf')):
                    fpath = os.path.join(d, fname)
                    try:
                        f = pg.font.Font(fpath, 12)
                        w = f.render('中', True, (0, 0, 0)).get_width()
                        if 8 <= w <= 20:
                            return fpath
                    except Exception:
                        continue
    return None
