#!/bin/bash
# 用你日常 Chrome 的 user-data-dir 启动 Chrome,带 CDP 9222 端口.
# Profile 是真人画像(完整历史 + cookies + 扩展),selenium attach 后行为更难被识别.
#
# 重要前置条件:
# 1. 必须先完全关闭日常 Chrome (Command+Q,不是关窗口)
# 2. 跑爬虫期间不能在这个 Chrome 里做别的操作(否则会干扰 selenium)
# 3. 跑完后:关掉这个 Chrome → 双击 Chrome 图标重新打开 → 一切恢复正常

set -e

USER_DATA_DIR="$HOME/Library/Application Support/Google/Chrome"
PORT=9222
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

if [ ! -x "$CHROME" ]; then
    echo "❌ 未找到 Chrome: $CHROME"
    exit 1
fi

if [ ! -d "$USER_DATA_DIR" ]; then
    echo "❌ 未找到日常 Chrome user-data-dir: $USER_DATA_DIR"
    exit 1
fi

# 检测日常 Chrome 是否还在跑(Chrome 同时只允许一个进程访问 user-data-dir)
if pgrep -f "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" > /dev/null 2>&1; then
    echo "❌ 检测到 Chrome 正在运行!"
    echo ""
    echo "请先完全关闭日常 Chrome:"
    echo "  - 在 Dock 上 右键 Chrome → 退出"
    echo "  - 或者 Chrome 窗口前按 Command+Q"
    echo ""
    echo "(关闭窗口不够,必须退出整个应用)"
    exit 1
fi

# 检测端口
if lsof -nP -iTCP:$PORT -sTCP:LISTEN > /dev/null 2>&1; then
    echo "❌ 端口 $PORT 已被占用,请先 kill 占用进程:"
    echo "    lsof -ti :$PORT | xargs kill -9"
    exit 1
fi

echo "========================================"
echo "  启动 Chrome (使用日常 profile)"
echo "========================================"
echo "  user-data-dir: $USER_DATA_DIR"
echo "  CDP port: $PORT"
echo ""
echo "✓ 你日常 Chrome 里已登录的京东账号会直接生效"
echo "✓ 跑完爬虫后,关掉这个 Chrome → 双击 Chrome 图标重开 → 恢复日常使用"
echo ""

"$CHROME" \
    --remote-debugging-port=$PORT \
    --user-data-dir="$USER_DATA_DIR" \
    --no-first-run \
    --no-default-browser-check \
    https://www.jd.com \
    > /dev/null 2>&1 &

CHROME_PID=$!
sleep 3

if kill -0 $CHROME_PID 2>/dev/null && lsof -nP -iTCP:$PORT -sTCP:LISTEN > /dev/null 2>&1; then
    echo "✓ Chrome 已启动 (PID $CHROME_PID,CDP 端口 $PORT 就绪)"
    echo "  现在到 web UI 点'开始爬取'"
else
    echo "❌ Chrome 启动失败或 CDP 端口未就绪"
    exit 1
fi
