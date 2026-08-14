"""
量化回測 runner
- 背景跑 quant/main.py（subprocess）
- 用 lock file 防止同時跑兩個
- 提供 status 查詢（讀 report.html + backtest_results.json）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from app_config import (
    QUANT_CACHE_DIR,
    QUANT_DIR,
    QUANT_OUTPUT_DIR,
    QUANT_RUN_LOCK_FILE,
    QUANT_RUN_LOCK_STALE_MIN,
    QUANT_RUN_TIMEOUT,
)


# ────────────────────────── 鎖檔 ──────────────────────────
def _is_lock_stale() -> bool:
    """lock 檔超過 stale 分鐘 → 判定為過期，可視為無鎖"""
    if not QUANT_RUN_LOCK_FILE.is_file():
        return False
    age_min = (time.time() - QUANT_RUN_LOCK_FILE.stat().st_mtime) / 60
    return age_min > QUANT_RUN_LOCK_STALE_MIN


def _acquire_lock() -> bool:
    """取得鎖；return True 成功；False 表示已有人在跑"""
    if QUANT_RUN_LOCK_FILE.is_file() and not _is_lock_stale():
        return False
    QUANT_RUN_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUANT_RUN_LOCK_FILE.write_text(
        json.dumps({
            'pid': os.getpid(),
            'started_at': datetime.now().isoformat(timespec='seconds'),
        }, ensure_ascii=False),
        encoding='utf-8',
    )
    return True


def _release_lock() -> None:
    if QUANT_RUN_LOCK_FILE.is_file():
        try:
            QUANT_RUN_LOCK_FILE.unlink()
        except OSError:
            pass


def is_running() -> bool:
    """是否有量化回測在跑"""
    return QUANT_RUN_LOCK_FILE.is_file() and not _is_lock_stale()


# ────────────────────────── 跑回測 ──────────────────────────
def run_quant() -> dict:
    """
    同步跑量化回測（會等跑完）

    Returns:
        dict: {
            'ok': True,
            'elapsed_sec': float,
            'kpis': {...} | None,
            'last_log': str,
        }
    """
    if not _acquire_lock():
        return {
            'ok': False,
            'error': '已有回測在跑（lock 存在）',
            'hint': '請等目前回測完成或刪除鎖檔',
        }

    start_time = time.monotonic()
    try:
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUNBUFFERED'] = '1'

        # 確保 quant/cache 與 output 目錄存在
        QUANT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        QUANT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        proc = subprocess.run(
            [sys.executable, 'main.py'],
            cwd=str(QUANT_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=QUANT_RUN_TIMEOUT,
        )

        elapsed = round(time.monotonic() - start_time, 1)
        last_log = (proc.stdout or '') + (proc.stderr or '')
        last_log = last_log[-2000:]  # 保留最後 2000 字元

        # 檢查報告檔
        report_file = QUANT_OUTPUT_DIR / 'report.html'
        results_file = QUANT_OUTPUT_DIR / 'backtest_results.json'

        if proc.returncode != 0:
            return {
                'ok': False,
                'error': f'回測 exit code {proc.returncode}',
                'elapsed_sec': elapsed,
                'last_log': last_log,
            }

        if not report_file.is_file():
            return {
                'ok': False,
                'error': '沒產出 report.html',
                'elapsed_sec': elapsed,
                'last_log': last_log,
            }

        # 解析 KPI
        kpis = None
        if results_file.is_file():
            try:
                data = json.loads(results_file.read_text(encoding='utf-8'))
                if isinstance(data, dict) and 'kpis' in data:
                    k = data['kpis']
                    kpis = {
                        'total_return':     round(k.get('total_return', 0) * 100, 2),
                        'benchmark_return': round(k.get('benchmark_return', 0) * 100, 2),
                        'excess_return':    round(k.get('excess_return', 0) * 100, 2),
                        'mdd':              round(k.get('mdd', 0) * 100, 2),
                        'sharpe':           round(k.get('sharpe', 0), 2),
                        'rebalance_count':  k.get('rebalance_count'),
                    }
            except Exception as e:
                last_log += f'\n[warn] KPI 解析失敗：{e}'

        return {
            'ok': True,
            'elapsed_sec': elapsed,
            'kpis': kpis,
            'last_log': last_log,
        }

    except subprocess.TimeoutExpired as e:
        return {
            'ok': False,
            'error': f'執行超過 {QUANT_RUN_TIMEOUT}s timeout',
            'last_log': (e.stdout or '')[-2000:] if hasattr(e, 'stdout') and e.stdout else '',
        }
    except Exception as e:
        return {
            'ok': False,
            'error': f'執行失敗：{e}',
        }
    finally:
        _release_lock()


# ────────────────────────── Status 查詢 ──────────────────────────
def get_status() -> dict:
    """查詢量化回測狀態（報告、KPI、是否在跑）"""
    report_file = QUANT_OUTPUT_DIR / 'report.html'
    results_file = QUANT_OUTPUT_DIR / 'backtest_results.json'

    last_update = None
    file_size = 0
    if report_file.is_file():
        mtime = report_file.stat().st_mtime
        last_update = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        file_size = report_file.stat().st_size

    kpis = None
    cum_strategy_first = None
    cum_strategy_last = None
    if results_file.is_file():
        try:
            data = json.loads(results_file.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                k = data.get('kpis', {})
                kpis = {
                    'total_return':     k.get('total_return'),
                    'benchmark_return': k.get('benchmark_return'),
                    'excess_return':    k.get('excess_return'),
                    'mdd':              k.get('mdd'),
                    'sharpe':           k.get('sharpe'),
                    'rebalance_count':  k.get('rebalance_count'),
                }
                cs = data.get('cum_strategy', [])
                if cs:
                    cum_strategy_first = cs[0].get('date', '')[:10]
                    cum_strategy_last = cs[-1].get('date', '')[:10]
        except Exception:
            pass

    return {
        'running': is_running(),
        'last_update': last_update,
        'file_size': file_size,
        'range_start': cum_strategy_first,
        'range_end': cum_strategy_last,
        'kpis': kpis,
    }
