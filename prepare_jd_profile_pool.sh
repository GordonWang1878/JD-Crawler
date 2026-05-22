#!/bin/bash
# 一次性脚本:依次准备 N 个 JD profile,每个都在 Chrome 里扫码登录京东.
# 用法:
#   bash prepare_jd_profile_pool.sh        # 默认准备 3 个
#   bash prepare_jd_profile_pool.sh 5      # 准备 5 个

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
POOL_DIR="$SCRIPT_DIR/jd_chrome_profile_pool"
PORT=9222
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

N=${1:-3}

if [ ! -x "$CHROME" ]; then
    echo "❌ 未找到 Chrome: $CHROME"
    exit 1
fi

# 检测端口冲突
if lsof -nP -iTCP:$PORT -sTCP:LISTEN > /dev/null 2>&1; then
    echo "❌ 端口 $PORT 已被占用,请先关闭已经运行的 crawler Chrome"
    exit 1
fi

mkdir -p "$POOL_DIR"

echo "========================================"
echo "  准备 JD profile 池 (共 $N 个)"
echo "========================================"
echo ""
echo "操作步骤:"
echo "  - 每个 profile 会启动一次 Chrome,你扫码登录京东"
echo "  - 登录成功后,请在终端按回车,然后 Chrome 自动关闭进入下一个"
echo "  - 同一个京东账号可以登录所有 profile(每个 profile 是独立身份)"
echo ""
read -p "准备好了吗?按回车继续..."

for i in $(seq 1 $N); do
    PROFILE="$POOL_DIR/profile_$i"

    echo ""
    echo "========================================"
    echo "  准备 profile $i / $N"
    echo "========================================"
    echo "  路径: $PROFILE"

    if [ -d "$PROFILE" ] && [ -n "$(ls -A "$PROFILE" 2>/dev/null)" ]; then
        echo "  ✓ profile_$i 已存在(已扫码过),跳过"
        continue
    fi

    mkdir -p "$PROFILE"
    echo "  Chrome 将启动 → 请扫码登录京东 → 回到终端按回车关闭 Chrome"
    echo ""

    "$CHROME" \
        --remote-debugging-port=$PORT \
        --user-data-dir="$PROFILE" \
        --no-first-run \
        --no-default-browser-check \
        https://passport.jd.com/new/login.aspx \
        > /dev/null 2>&1 &

    CHROME_PID=$!
    sleep 2

    if ! kill -0 $CHROME_PID 2>/dev/null; then
        echo "❌ Chrome 启动失败"
        exit 1
    fi

    read -p "在 Chrome 里扫码登录完成后,按回车关闭这个 Chrome..."

    # 关闭 Chrome
    kill -TERM $CHROME_PID 2>/dev/null || true
    sleep 1
    kill -KILL $CHROME_PID 2>/dev/null || true

    # 等端口释放
    sleep 2
    while lsof -nP -iTCP:$PORT -sTCP:LISTEN > /dev/null 2>&1; do
        sleep 1
    done

    echo "  ✓ profile_$i 准备完成"
done

echo ""
echo "========================================"
echo "  ✓ 全部 $N 个 profile 准备完成"
echo "========================================"
echo "  现在可以到 web UI 点'开始爬取',crawler 会自动 spawn profile_1"
echo "  风控触发时会自动轮转到 profile_2 → profile_3 ..."
