#!/bin/bash
cd "$(dirname "$0")"
echo "正在啟動脈衝 PULSE..."
( sleep 2; xdg-open "http://127.0.0.1:5000/host" >/dev/null 2>&1 ) &
python3 app.py
