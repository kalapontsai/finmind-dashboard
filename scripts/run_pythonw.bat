@echo off
REM ============================================
REM   FinMind Dashboard — pythonw 啟動版
REM   雙擊啟動，無 console 視窗殘留
REM ============================================
REM 流程：
REM   1) 找 pythonw.exe（PATH 或常見位置）
REM   2) 砍掉舊的 python app.py / pythonw wslBridge.py 進程
REM   3) pythonw wslBridge.py  →  內部 spawn WSL 跑 Flask
REM   4) 父 cmd 視窗立即關閉
REM
REM 對比 start.bat：
REM   - start.bat  →  用 start /B 在 cmd 內背景跑（會留個隱藏視窗）
REM   - run_pythonw.bat →  用 pythonw 跑 stub，stub 自動 exit（無任何視窗殘留）

setlocal
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..

REM ── 1. 找 pythonw.exe ──
set PYTHONW=
where pythonw.exe >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%i in ('where pythonw.exe') do set PYTHONW=%%i
)

REM 找不到 PATH → 試常見位置
if "%PYTHONW%"=="" (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" set PYTHONW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe" set PYTHONW=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe
    if exist "C:\Python312\pythonw.exe" set PYTHONW=C:\Python312\pythonw.exe
    if exist "C:\Python311\pythonw.exe" set PYTHONW=C:\Python311\pythonw.exe
)

if "%PYTHONW%"=="" (
    echo [ERROR] 找不到 pythonw.exe，請安裝 Python 3.10+ 並加入 PATH
    echo 常見位置：C:\Python312\pythonw.exe 或 %LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe
    pause
    exit /b 1
)

echo [1/3] pythonw.exe: %PYTHONW%

REM ── 2. 砍掉舊的 python app.py / pythonw wslBridge.py 進程 ──
echo [2/3] 砍掉舊進程...
wmic process where "name='pythonw.exe' and commandline like '%%wslBridge.py%%'" delete 2>nul
wmic process where "name='python.exe' and commandline like '%%app.py%%'" delete 2>nul
wmic process where "name='pythonw.exe' and commandline like '%%app.py%%'" delete 2>nul
timeout /t 2 >nul

REM ── 3. pythonw 跑 stub ──
echo [3/3] 啟動 stub (pythonw 隱藏模式)...
start "FinMind Launcher" /B "%PYTHONW%" "%SCRIPT_DIR%wslBridge.py" "%PROJECT_DIR%"

REM 父 cmd 立即關閉（不留任何視窗）
exit
