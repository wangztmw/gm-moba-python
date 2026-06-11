#!/usr/bin/env python3
"""素材烘焙脚本 — 将游戏内所有静态元素预渲染为 PNG 文件

使用方法:
    python3 bake_sprites.py

生成所有 PNG 到 assets/sprites/ 目录，游戏随后可直接从磁盘加载，
无需在运行时执行任何 pg.draw 调用。
"""
import os
import sys
import pygame as pg


def main():
    print('=' * 50)
    print('  MOBA 素材烘焙工具')
    print('  将所有静态元素预渲染为 PNG')
    print('=' * 50)

    # 初始化 Pygame（无头模式）
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    pg.init()
    pg.display.set_mode((1, 1))

    from display.sprite_cache import get_cache, _get_sprite_dir

    # 构建所有 Surface
    print('\n▶ 构建缓存 Surface ...')
    from display.sprite_cache import SpriteCache
    cache = SpriteCache()
    cache.build_all()

    # 保存为 PNG
    out_dir = _get_sprite_dir()
    print(f'\n▶ 保存到 {out_dir} ...')
    cache.save_all()

    # 统计
    total_size = 0
    for f in os.listdir(out_dir):
        if f.endswith('.png'):
            total_size += os.path.getsize(os.path.join(out_dir, f))
    print(f'\n  总大小: {total_size / 1024:.1f} KB ({len(os.listdir(out_dir))} 个文件)')

    pg.quit()
    print('\n✓ 烘焙完成！游戏将从磁盘加载素材，无需运行时渲染。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
