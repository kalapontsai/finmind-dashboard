@echo off
REM ============================================================
REM FinMind Dashboard Launcher (no-console, log to file)
REM - Double-click to launch Flask on port 5000
REM - Uses project venv (.\venv\Scripts\activate.bat)
REM - pythonw runs in background, no terminal window
REM - All stdout/stderr written to logs/flask.log
REM ============================================================

setlocal

REM --- Resolve project root (parent of this scripts\ folder) ---
REM Buggy: "%~dp0..:~0,-1%" -> ends up as "scripts\." (wrong)
REM Fixed: for-loop resolves ".." to absolute path
for %%I in ("%~dp0\..") do set "PROJECT_DIR=%%~fI"

set PORT=5000
set LOG_DIR=%PROJECT_DIR%\logs
set LOG_FILE=%LOG_DIR%\flask.log

echo ============================================
echo   FinMind Dashboard Launcher
echo ============================================
echo PROJECT_DIR: %PROJECT_DIR%
echo Port:        %PORT%
echo LOG_FILE:    %LOG_FILE%
echo.

REM --- [1/4] Kill old python processes ---
echo [1/4] Killing old processes...
wmic process where "name='python.exe' and commandline like '%%app.py%%'" delete 2>nul
wmic process where "name='pythonw.exe' and commandline like '%%app.py%%'" delete 2>nul
timeout /t 2 >nul

REM --- [2/4] Verify venv exists ---
echo [2/4] Checking venv...
if not exist "%PROJECT_DIR%\venv\Scripts\activate.bat" (
    echo [ERROR] venv\Scripts\activate.bat not found.
    echo PROJECT_DIR: %PROJECT_DIR%
    echo To create venv:
    echo     cd /d "%PROJECT_DIR%"
    echo     python -m venv venv
    pause
    exit /b 1
)
echo venv OK.

REM --- [3/4] Ensure logs dir exists ---
echo [3/4] Checking logs directory...
if not exist "%LOG_DIR%" (
    mkdir "%LOG_DIR%" 2>nul
)
echo logs dir OK: %LOG_DIR%

REM --- [4/4] Launch Flask via run_hidden.py (no console window, all output to log) ---
echo [4/4] Starting Flask (pythonw + run_hidden.py, background)...
call "%PROJECT_DIR%\venv\Scripts\activate.bat" >nul
cd /d "%PROJECT_DIR%"
set "PYTHONIOENCODING=utf-8"

REM run_hidden.py launches pythonw with CREATE_NO_WINDOW and redirects all
REM stdout/stderr to logs/flask.log (see run_hidden.py for details)
start "" cmd /c "pythonw run_hidden.py"

echo.
echo [OK] Flask launched in background (no window).
echo LOG:     %LOG_FILE%
echo VISIT:   http://localhost:%PORT%/
echo STOP:    double-click stop.bat
echo.
echo NOTE: No window will appear. Check %LOG_FILE% for output.
echo.
REM Auto-close cmd window after 3 seconds (no manual keypress needed)
timeout /t 3 /nobreak >nul
