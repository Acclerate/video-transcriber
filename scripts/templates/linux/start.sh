#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export PORTABLE_MODE=1
export PYTHONPATH="$SCRIPT_DIR/app"
export PATH="$SCRIPT_DIR/ffmpeg:$PATH"
export MODELSCOPE_CACHE="$SCRIPT_DIR/models_cache"

mkdir -p "$SCRIPT_DIR/temp" "$SCRIPT_DIR/output" "$SCRIPT_DIR/logs"

# 联网轻量版：首次启动时自动下载 FFmpeg 和模型
SETUP_SCRIPT="$SCRIPT_DIR/app/setup_runtime.py"
if [ -f "$SETUP_SCRIPT" ]; then
    PYTHON="$SCRIPT_DIR/python/bin/python"
    echo "  [检查] 运行环境组件 ..."
    "$PYTHON" "$SETUP_SCRIPT" --check 2>/dev/null || {
        echo "  缺失组件，开始自动下载 ..."
        "$PYTHON" "$SETUP_SCRIPT"
    }
fi

cd "$SCRIPT_DIR/app"

PYTHON="${PYTHON:-$SCRIPT_DIR/python/bin/python}"

echo ""
echo "  ============================================"
echo "    Video Transcriber"
echo "    Starting server..."
echo "  ============================================"
echo ""

"$PYTHON" -m uvicorn api.apimain:app --host 0.0.0.0 --port 8665 &
SERVER_PID=$!

echo "$SERVER_PID" > "$SCRIPT_DIR/.server.pid"

if command -v xdg-open &>/dev/null && [ -n "$DISPLAY" ]; then
    sleep 5
    xdg-open http://localhost:8665 2>/dev/null || true
fi

echo "Server PID: $SERVER_PID"
echo "To stop: ./stop.sh"

wait $SERVER_PID
