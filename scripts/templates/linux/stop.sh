#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.server.pid" ]; then
    kill "$(cat "$SCRIPT_DIR/.server.pid")" 2>/dev/null || true
    rm "$SCRIPT_DIR/.server.pid"
fi
echo "Server stopped."
