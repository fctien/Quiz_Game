@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在啟動金榜問答...
start "" http://127.0.0.1:5000/host
python app.py
echo.
echo 伺服器已停止。按任意鍵關閉視窗。
pause >nul
