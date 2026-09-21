@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 脈衝 PULSE

echo ================================================
echo   脈衝 PULSE - 啟動中
echo ================================================
echo.

rem ---- 找 Python ----
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY (
  python --version >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [錯誤] 找不到 Python。
  echo.
  echo 請先安裝 Python 3：https://www.python.org/downloads/
  echo 安裝時務必勾選 "Add python.exe to PATH"。
  echo.
  pause
  exit /b 1
)
echo 使用的 Python：
%PY% --version
echo.

rem ---- 檢查 Flask，沒有就安裝 ----
%PY% -c "import flask" >nul 2>nul
if errorlevel 1 (
  echo 第一次執行，正在安裝所需套件...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo [錯誤] 套件安裝失敗，請把上面的訊息回報。
    pause
    exit /b 1
  )
  echo.
)

rem ---- 開瀏覽器並啟動伺服器 ----
echo 瀏覽器會自動開啟主持台。第一次執行時，Windows 可能跳出防火牆詢問，
echo 請按「允許存取」並勾選「專用網路」。
echo.
echo 要停止伺服器：在這個視窗按 Ctrl+C，或直接關閉視窗。
echo ================================================
echo.
rem 先等伺服器真的起來再開瀏覽器。題庫有三千多題,載入要一兩秒;
rem 以前直接開瀏覽器,常常比伺服器早一步,主題清單抓不到就變成空白畫面。
start "" powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 90;$i++){try{$r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5000/api/categories' -TimeoutSec 2; if($r.StatusCode -eq 200){Start-Process 'http://127.0.0.1:5000/host'; break}}catch{}; Start-Sleep -Milliseconds 400}"
%PY% app.py

echo.
echo 伺服器已停止。按任意鍵關閉視窗。
pause >nul
