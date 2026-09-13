@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "LOG=%~dp0診斷結果.txt"
title 金榜問答 - 環境診斷

echo 正在診斷，請稍候...
echo ===== 金榜問答 環境診斷 ===== > "%LOG%"
echo 時間: %DATE% %TIME% >> "%LOG%"
echo 資料夾: %~dp0 >> "%LOG%"
echo. >> "%LOG%"

echo --- where py --- >> "%LOG%"
where py >> "%LOG%" 2>&1
echo --- py -3 --version --- >> "%LOG%"
py -3 --version >> "%LOG%" 2>&1
echo --- where python --- >> "%LOG%"
where python >> "%LOG%" 2>&1
echo --- python --version --- >> "%LOG%"
python --version >> "%LOG%" 2>&1
echo --- where pip --- >> "%LOG%"
where pip >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo --- 已安裝套件（flask 相關） --- >> "%LOG%"
py -3 -m pip list 2>nul | findstr /i "flask requests" >> "%LOG%" 2>&1
python -m pip list 2>nul | findstr /i "flask requests" >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo --- 試著 import flask --- >> "%LOG%"
py -3 -c "import flask, sys; print('flask ok', flask.__version__ if hasattr(flask,'__version__') else '', sys.version)" >> "%LOG%" 2>&1
python -c "import flask, sys; print('flask ok', sys.version)" >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo --- 資料夾內容 --- >> "%LOG%"
dir /b >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo --- 網路卡 IP --- >> "%LOG%"
ipconfig | findstr /i "IPv4" >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo --- 5000 埠是否已被占用 --- >> "%LOG%"
netstat -ano | findstr ":5000" >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo --- 防火牆是否已有 Python 規則 --- >> "%LOG%"
netsh advfirewall firewall show rule name=all dir=in 2>nul | findstr /i "python" >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo ===== 診斷結束 ===== >> "%LOG%"
echo.
echo 診斷完成，結果已存成「診斷結果.txt」，請告訴 Claude 我跑好了。
echo.
pause
