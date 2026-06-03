#!/usr/bin/env python3
"""macOS 打包脚本 — 生成 .app + .dmg

用法:
    PYTHONPATH=/tmp/py-build:/tmp/py-libs python3 build_app.py

先决条件:
    pip3 install --break-system-packages --target=/tmp/py-build pyinstaller
    pip3 install --break-system-packages --target=/tmp/py-libs pygame-ce

输出:
    dist/MOBA 三线对决.app    (可拖拽到 Applications)
    dist/MOBA 三线对决.dmg    (安装包, 可选)
    dist/MOBA_三线对决.zip    (压缩包, 后备)
"""
import os
import sys
import shutil
import subprocess

sys.path.insert(0, '/tmp/py-build')
sys.path.insert(0, '/tmp/py-libs')

import PyInstaller.__main__

APP_NAME = "MOBA 三线对决"
ENTRY_POINT = "main.py"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_SRC = os.path.join(PROJECT_DIR, "assets", "sprites")
ASSETS_DST = os.path.join("assets", "sprites")


def step(msg):
    print(f"\n▶ {msg}")


def main():
    print("=" * 50)
    print(f"  打包 {APP_NAME} for macOS")
    print("=" * 50)

    # ── 检查素材 ──
    if not os.path.isdir(ASSETS_SRC):
        step("错误: 素材目录不存在，请先运行 python3 bake_sprites.py")
        return 1
    png_count = len([f for f in os.listdir(ASSETS_SRC) if f.endswith('.png')])
    print(f"   素材: {ASSETS_SRC} ({png_count} 个 PNG)")

    # ── 清理 ──
    step("清理旧构建")
    for d in ['build', 'dist']:
        dp = os.path.join(PROJECT_DIR, d)
        if os.path.isdir(dp):
            shutil.rmtree(dp)
            print(f"   删除: {d}/")

    # ── 构建 .app ──
    step("PyInstaller 打包 .app")
    build_dir = os.path.join(PROJECT_DIR, 'build')
    dist_dir = os.path.join(PROJECT_DIR, 'dist')
    args = [
        ENTRY_POINT,
        '--windowed',
        '--name', APP_NAME,
        '--noconfirm',
        '--clean',
        '--workpath', build_dir,
        '--distpath', dist_dir,
        '--add-data', f'{ASSETS_SRC}{os.pathsep}{ASSETS_DST}',
        '--exclude-module', 'tkinter',
        '--exclude-module', 'matplotlib',
        '--exclude-module', 'PIL',
        '--exclude-module', 'cv2',
        '--osx-bundle-identifier', 'com.moba.three-lanes',
    ]
    PyInstaller.__main__.run(args)

    app_path = os.path.join(dist_dir, f'{APP_NAME}.app')
    if not os.path.isdir(app_path):
        print("   错误: .app 未生成")
        return 1

    # 计算大小
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(app_path):
        for f in filenames:
            total_size += os.path.getsize(os.path.join(dirpath, f))
    mb = total_size / (1024 * 1024)
    print(f"   ✓ {APP_NAME}.app  ({mb:.0f} MB)")

    # ── 创建 DMG ──
    step("创建 .dmg 安装包")
    dmg_path = os.path.join(dist_dir, f'{APP_NAME}.dmg')
    staging = '/tmp/moba-dmg-staging'
    try:
        if os.path.isdir(staging):
            shutil.rmtree(staging)
        os.makedirs(staging)
        shutil.copytree(app_path, os.path.join(staging, f'{APP_NAME}.app'))
        os.symlink('/Applications', os.path.join(staging, 'Applications'))

        dmg_size_mb = int(mb) + 20
        result = subprocess.run([
            'hdiutil', 'create',
            '-volname', APP_NAME,
            '-srcfolder', staging,
            '-ov',
            '-format', 'UDZO',
            '-size', f'{dmg_size_mb}m',
            dmg_path,
        ], capture_output=True, text=True)
        if result.returncode == 0:
            dmg_mb = os.path.getsize(dmg_path) / (1024 * 1024)
            print(f"   ✓ {APP_NAME}.dmg  ({dmg_mb:.0f} MB)")
        else:
            print(f"   ⚠ hdiutil 失败: {result.stderr.strip()}")
            print(f"   可用: open dist/{APP_NAME}.app (直接运行)")
            dmg_path = None
        shutil.rmtree(staging)
    except Exception as e:
        print(f"   ⚠ DMG 创建失败: {e}")
        dmg_path = None

    # ── 创建 ZIP 后备 ──
    step("创建 .zip 压缩包 (后备)")
    zip_path = os.path.join(dist_dir, f'{APP_NAME}.zip')
    shutil.make_archive(
        zip_path.replace('.zip', ''),
        'zip',
        dist_dir,
        f'{APP_NAME}.app'
    )
    zip_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"   ✓ {APP_NAME}.zip  ({zip_mb:.0f} MB)")

    # ── 完成 ──
    print("\n" + "=" * 50)
    print("  打包完成!")
    print("=" * 50)
    print(f"\n  .app:  {dist_dir}/{APP_NAME}.app")
    if dmg_path:
        print(f"  .dmg:  {dmg_path}")
    print(f"  .zip:  {zip_path}")
    print(f"\n  安装方式:")
    print(f"    1. 打开 dist/ 目录")
    if dmg_path:
        print(f"    2. 双击 {APP_NAME}.dmg")
        print(f"    3. 将 {APP_NAME}.app 拖入 Applications")
    else:
        print(f"    2. 解压 {APP_NAME}.zip")
        print(f"    3. 将 {APP_NAME}.app 拖入 Applications")
    print(f"    4. 右键 > 打开 (首次运行需绕过 Gatekeeper)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
