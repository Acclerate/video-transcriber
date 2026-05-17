#!/bin/bash
cd /home/dministrator/video-transcriber-linux
export PORTABLE_MODE=1
export PYTHONPATH=./app
export PATH=./ffmpeg:$PATH
python/bin/python -m uvicorn api.apimain:app --host 0.0.0.0 --port 8665 &
PID=$!
sleep 8
curl -s http://localhost:8665/health
echo ""
echo "Server PID: $PID"
kill $PID 2>/dev/null
