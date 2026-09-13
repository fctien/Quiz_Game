@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title 推上 GitHub

set "REPO=https://github.com/fctien/Quiz_Game.git"

echo ================================================
echo   把脈衝 PULSE 推上 GitHub
echo   目標：%REPO%
echo ================================================
echo.

git --version >nul 2>nul
if errorlevel 1 (
  echo [錯誤] 找不到 git。
  echo 請先安裝 Git for Windows：https://git-scm.com/download/win
  echo 安裝時全部按預設值即可，裝完後重開這個檔案。
  echo.
  pause
  exit /b 1
)
git --version
echo.

if not exist ".git" (
  echo 這個資料夾還不是 git 儲存庫，正在初始化...
  git init
  git branch -M main
)

rem ---- 設定身分（若尚未設定）----
for /f "delims=" %%a in ('git config user.email 2^>nul') do set "GEMAIL=%%a"
if not defined GEMAIL (
  git config user.email "fctien@mail.ntut.edu.tw"
  git config user.name "Tien"
)

rem ---- 設定遠端 ----
git remote get-url origin >nul 2>nul
if errorlevel 1 (
  git remote add origin "%REPO%"
) else (
  git remote set-url origin "%REPO%"
)
echo 遠端：
git remote -v
echo.

rem ---- 提交尚未提交的變更 ----
git add -A
git diff --cached --quiet
if errorlevel 1 (
  echo 提交目前的變更...
  git commit -m "更新脈衝 PULSE"
) else (
  echo 沒有新的變更需要提交。
)
echo.

echo 開始推送。第一次會跳出 GitHub 登入視窗，請用瀏覽器完成授權。
echo.
git push -u origin main --tags
if errorlevel 1 (
  echo.
  echo 推送被拒絕，可能是 GitHub 上已經有內容。正在嘗試合併後重推...
  git pull --rebase --allow-unrelated-histories origin main
  if errorlevel 1 (
    echo.
    echo [錯誤] 自動合併失敗。請把上面的訊息回報給 Claude。
    pause
    exit /b 1
  )
  git push -u origin main --tags
  if errorlevel 1 (
    echo.
    echo [錯誤] 推送失敗，請把上面的訊息回報給 Claude。
    pause
    exit /b 1
  )
)

echo.
echo ================================================
echo   完成！打開看看：https://github.com/fctien/Quiz_Game
echo ================================================
echo.
pause
