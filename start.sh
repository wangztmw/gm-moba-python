#!/bin/bash
# 安装依赖并启动游戏
cd "$(dirname "$0")"
pip3 install --break-system-packages pygame-ce 2>/dev/null || pip3 install pygame-ce 2>/dev/null
python3 main.py
