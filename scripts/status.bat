@echo off
REM FinMind Dashboard 狀態查詢

setlocal
set PORT=5000

echo ============================================
echo   FinMind Dashboard 狀態
echo ============================================
echo.

REM 檢查 port 5000 是否 LISTENING
netstat -ano | findstr :%PORT% | findstr LISTENING >nul
if errorlevel 1 (
    echo [狀態] ❌ 未運行（Port %PORT% 沒人在用）
    echo.
    echo 啟動：雙擊 start.bat
    goto :end
)

echo [狀態] ✅ 運行中

REM 列出相關 python 進程
echo.
echo [進程]
wmic process where "name='python.exe' and commandline like '%%app.py%%'" get processid,commandline /format:list 2>nul

REM 嘗試健康檢查
echo.
echo [健康檢查]
curl -s http://localhost:%PORT%/api/health
echo.
echo.

:end
pause
