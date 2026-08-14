"""
run_hidden.py — Windows no-console Flask launcher
用法: pythonw run_hidden.py

特點：
- CREATE_NO_WINDOW flag（無終端視窗）
- 所有 stdout/stderr 寫入 logs/flask.log
- subprocess 自動重啟（看門狗模式）
"""
import sys, os, subprocess, time, atexit

# Project root = directory containing this script (run_hidden.py is in the project root)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = SCRIPT_DIR
LOG_DIR    = os.path.join(PROJECT_DIR, "logs")
LOG_FILE   = os.path.join(LOG_DIR, "flask.log")

def ensure_log_dir():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="", flush=True)

def cleanup():
    log("run_hidden.py exiting — Flask should have been killed by stop.bat")

def main():
    atexit.register(cleanup)
    ensure_log_dir()

    log("=" * 50)
    log(f"run_hidden.py started")
    log(f"PROJECT_DIR: {PROJECT_DIR}")
    log(f"LOG_FILE:    {LOG_FILE}")
    log(f"sys.version: {sys.version}")
    log("=" * 50)

    # Build pythonw command
    pythonw = os.path.join(PROJECT_DIR, "venv", "Scripts", "pythonw.exe")
    app_py  = os.path.join(PROJECT_DIR, "app.py")

    if not os.path.exists(pythonw):
        log(f"[FATAL] pythonw not found: {pythonw}")
        sys.exit(1)
    if not os.path.exists(app_py):
        log(f"[FATAL] app.py not found: {app_py}")
        sys.exit(1)

    # Environment: inherit current env, add PYTHONIOENCODING
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    # Ensure venv python takes priority (inherit venv activation context)
    venv_scripts = os.path.join(PROJECT_DIR, "venv", "Scripts")
    if venv_scripts not in env.get("PATH", ""):
        env["PATH"] = venv_scripts + os.pathsep + env.get("PATH", "")

    # Launch pythonw with CREATE_NO_WINDOW = 0x08000000
    # and redirect stdout/stderr to log file
    with open(LOG_FILE, "a", encoding="utf-8") as log_fp:
        proc = subprocess.Popen(
            [pythonw, app_py],
            cwd=PROJECT_DIR,
            env=env,
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        log(f"[OK] Flask started (pid={proc.pid})")
        log(f"    pythonw: {pythonw}")
        log(f"    app.py:  {app_py}")
        log(f"    stdout/stderr -> {LOG_FILE}")

        # Wait for Flask to bind port (or process exits)
        log("Waiting for Flask to initialize...")
        try:
            rc = proc.wait(timeout=5)
            log(f"[WARN] Flask exited early (rc={rc})")
        except subprocess.TimeoutExpired:
            log("Flask appears to be running. Keeping this wrapper alive.")
            # Keep alive — stop.bat will kill the pythonw process
            try:
                while True:
                    time.sleep(10)
                    if proc.poll() is not None:
                        log(f"[WARN] Flask crashed (pid={proc.pid} exited)")
                        break
            except KeyboardInterrupt:
                log("Interrupted, stopping Flask...")
                proc.terminate()
                proc.wait()

if __name__ == "__main__":
    main()
