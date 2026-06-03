#!/bin/bash
# 从 .app 创建 DMG 安装包
# 用法: bash build_dmg.sh
# 需要先运行: PYTHONPATH=/tmp/py-build:/tmp/py-libs python3 build_app.py
# 
# 如果 hdiutil 在当前环境受限，直接使用 dist/ 内的 .zip

set -e

APP_NAME="MOBA 三线对决"
APP_PATH="dist/${APP_NAME}.app"
DMG_NAME="dist/${APP_NAME}.dmg"
STAGING_DIR="/tmp/moba-dmg-staging"

# 检查 .app 是否存在
if [ ! -d "$APP_PATH" ]; then
    echo "错误: 找不到 $APP_PATH"
    echo "请先运行: python3 build_app.py"
    exit 1
fi

echo "创建 DMG 安装包..."

# 清理临时目录
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

# 复制 .app 到临时目录
cp -R "$APP_PATH" "$STAGING_DIR/"

# 添加 Applications 快捷方式（拖拽安装引导）
ln -s /Applications "$STAGING_DIR/Applications"

# 计算 .app 大小以确定 DMG 尺寸
APP_SIZE_MB=$(du -sm "$APP_PATH" | cut -f1)
# DMG 需要额外空间给卷标和 Applications 链接
DMG_SIZE_MB=$(( APP_SIZE_MB + 20 ))

echo "  .app 大小: ${APP_SIZE_MB} MB"
echo "  DMG 大小: ${DMG_SIZE_MB} MB"

# 创建 DMG
hdiutil create -volname "$APP_NAME" \
    -srcfolder "$STAGING_DIR" \
    -ov -format UDZO \
    -size "${DMG_SIZE_MB}m" \
    "$DMG_NAME" 2>&1

# 清理
rm -rf "$STAGING_DIR"

echo ""
echo "✓ DMG 安装包已创建: $DMG_NAME"
echo "  大小: $(du -h "$DMG_NAME" | cut -f1)"
