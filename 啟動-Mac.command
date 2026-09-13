#!/bin/bash
cd "$(dirname "$0")"
echo "正在啟動金榜問答..."
( sleep 2; open "http://127.0.0.1:5000/host" ) &
python3 app.py
