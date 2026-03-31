#!/bin/bash
set -e

echo "=== 安装 Python 依赖 ==="
pip install playwright pillow

echo "=== 安装 Chromium 浏览器 ==="
playwright install chromium
playwright install-deps chromium

echo "=== 创建数据目录 ==="
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
mkdir -p "$BASE_DIR/data"/{profiles,cache,downloads,logs,snapshots}

echo "=== 完成 ==="
echo "下一步: python scripts/login.py"
