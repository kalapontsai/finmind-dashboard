@echo off
REM FinMind Dashboard 啟動（簡單版）
REM 雙擊此檔啟動 Flask 於 5000 port
REM 如已在跑會先砍掉舊進程

setlocal
set PROJECT_DIR=%~dp0..
set PROJECT_DIR=%PROJECT_DIR:~0,-1%
set PORT=5000

echo ============================================
echo   FinMind Dashboard 啟動
echo ============================================
echo 位置: %PROJECT_DIR%
echo Port: %PORT%
echo.

REM 砍掉舊的 python app.py 進程
echo [1/2] 檢查並砍掉舊進程...
wmic process where "name='python.exe' and commandline like '%%app.py%%'" delete 2>nul
wmic process where "name='python.exe' and commandline like '%%flask%%'" delete 2>nul
timeout /t 2 >nul

REM 啟動 Flask（用 WSL 跑，因為有 FinMind/pandas）
echo [2/2] 啟動 Flask (WSL)...
start "FinMind Dashboard" /B wsl bash -c "cd '%PROJECT_DIR%' && python3 app.py"

echo.
echo [OK] Flask 啟動完成
echo 訪問: http://localhost:%PORT%/
echo 關閉: 雙擊 stop.bat
echo.
pause
