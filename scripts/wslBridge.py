#!/usr/bin/env python3
"""
wslBridge.py — 給 run_pythonw.bat 用的 Windows stub

流程：
1) 接收 WSL 內 Flask 專案路徑（command-line 參數）
2) 透過 WSL 跑 Flask（subprocess.Popen + DETACHED_PROCESS）
3) 自己瞬間 exit（pythonw 沒 console 視窗）

雙擊 run_pythonw.bat → pythonw 跑這個檔 → 內部 spawn WSL Flask → 立即 exit
→ 結果：Flask 在 WSL 內跑於 5000 port，Windows 端沒有任何視窗殘留
"""
import subprocess
import sys
import os
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        # 沒給參數 → 預設 ../（相對於這個檔案）
        project_dir = str(Path(__file__).resolve().parent.parent)
    else:
        project_dir = sys.argv[1]

    # 確認路徑存在
    if not os.path.isdir(project_dir):
        sys.stderr.write(f'[wslBridge] 無效路徑: {project_dir}\n')
        sys.exit(1)

    app_py = os.path.join(project_dir, 'app.py')
    if not os.path.isfile(app_py):
        sys.stderr.write(f'[wslBridge] 找不到 app.py: {app_py}\n')
        sys.exit(1)

    # WSL 路徑轉換：D:\foo\bar → /mnt/d/foo/bar
    # 簡化處理：假設都是 D:\ 開頭（看 USER.md）
    if project_dir[1:3] == ':\\':
        drive = project_dir[0].lower()
        wsl_path = f'/mnt/{drive}{project_dir[2:].replace(chr(92), "/")}'
    else:
        wsl_path = project_dir

    # 構造 WSL 指令
    bash_cmd = f'cd "{wsl_path}" && python3 app.py'
    print(f'[wslBridge] WSL 指令: wsl bash -c "{bash_cmd[:80]}..."')

    # spawn WSL（DETACHED_PROCESS：父 process 完全獨立）
    # Windows 與 Linux 用不同 flag
    kwargs = dict(
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if sys.platform == 'win32':
        # Windows：DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs['creationflags'] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        kwargs['close_fds'] = True
    else:
        # Linux/Mac：用 start_new_session（建立新 session 獨立）
        kwargs['start_new_session'] = True

    try:
        proc = subprocess.Popen(['wsl', 'bash', '-c', bash_cmd], **kwargs)
        print(f'[wslBridge] WSL Flask PID = {proc.pid}')
    except FileNotFoundError:
        sys.stderr.write('[wslBridge] 找不到 wsl.exe，請確認 WSL 已安裝\n')
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f'[wslBridge] 啟動失敗: {e}\n')
        sys.exit(1)

    # 寫入 PID 檔（方便 stop.bat 砍）
    pid_file = os.path.join(project_dir, 'logs', 'wsl_flask.pid')
    try:
        os.makedirs(os.path.dirname(pid_file), exist_ok=True)
        with open(pid_file, 'w') as f:
            f.write(str(proc.pid))
    except Exception:
        pass

    # 給 1.5 秒讓 WSL 啟動後再 exit（避免 race）
    import time
    time.sleep(1.5)

    print('[wslBridge] 啟動完成，立即 exit')


if __name__ == '__main__':
    main()
