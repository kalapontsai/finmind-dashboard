@echo off
REM FinMind Dashboard 停止

setlocal
echo ============================================
echo   FinMind Dashboard 停止
echo ============================================
echo.

echo [1/1] 砍掉 python app.py 進程...
wmic process where "name='python.exe' and commandline like '%%app.py%%'" delete 2>nul
wmic process where "name='pythonw.exe' and commandline like '%%app.py%%'" delete 2>nul

timeout /t 2 >nul

REM 驗證 port 5000 沒人用
netstat -ano | findstr :5000 | findstr LISTENING >nul
if errorlevel 1 (
    echo [OK] Flask 已停止
) else (
    echo [WARN] Port 5000 仍有進程，請手動檢查
)

echo.
pause
