#!/bin/bash
# 启动 JD crawler 专用 Chrome (CDP attach 模式)
# - 独立 user-data-dir,跟你日常 Chrome 完全隔离
# - 开启 9222 远程调试端口,供 crawler 连接
# - 指纹层 100% 真实 Chrome,京东风控难以识别为自动化

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROFILE_DIR="$SCRIPT_DIR/jd_chrome_profile"
PORT=9222

# macOS Chrome 路径
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

if [ ! -x "$CHROME" ]; then
    echo "❌ 未找到 Chrome: $CHROME"
    echo "   请确认已安装 Google Chrome"
    exit 1
fi

mkdir -p "$PROFILE_DIR"

# 检测端口是否已被占用
if lsof -nP -iTCP:$PORT -sTCP:LISTEN > /dev/null 2>&1; then
    echo "✓ 端口 $PORT 已在监听,Chrome 已经在运行(无需重新启动)"
    echo "  如果需要重启,先关掉当前 crawler Chrome 窗口再运行本脚本"
    exit 0
fi

echo "========================================"
echo "  启动 JD crawler 专用 Chrome"
echo "========================================"
echo "  profile: $PROFILE_DIR"
echo "  CDP port: $PORT"
echo ""
echo "操作步骤:"
echo "  1. Chrome 弹出后,在里面扫码登录京东"
echo "  2. 登录完成后,保持 Chrome 开着(不要关闭)"
echo "  3. 到 web UI 点 '开始爬取',crawler 会自动 attach"
echo ""
echo "下次跑爬虫前,如果 Chrome 还开着,直接到 web UI 点开始即可."
echo "如果 Chrome 已关闭,重新双击/运行本脚本即可."
echo "========================================"

"$CHROME" \
    --remote-debugging-port=$PORT \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    https://www.jd.com \
    > /dev/null 2>&1 &

CHROME_PID=$!
sleep 2

if kill -0 $CHROME_PID 2>/dev/null; then
    echo ""
    echo "✓ Chrome 已启动 (PID: $CHROME_PID)"
    echo "  请在 Chrome 窗口中扫码登录京东"
else
    echo "❌ Chrome 启动失败"
    exit 1
fi
