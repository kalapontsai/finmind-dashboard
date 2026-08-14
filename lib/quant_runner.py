"""
量化回測 runner
- 背景跑 quant/main.py（subprocess）或 quant.quant.run()（thread）
- 用 lock file 防止同時跑兩個
- 提供 status / progress 查詢（讀 progress/ 目錄）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from app_config import (
    QUANT_CACHE_DIR,
    QUANT_DIR,
    QUANT_OUTPUT_DIR,
    QUANT_PROGRESS_DIR,
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
    QUANT_PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
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


# ────────────────────────── 進度檔 ──────────────────────────

def _progress_file(job_id: str) -> Path:
    return QUANT_PROGRESS_DIR / f'{job_id}.json'


def _write_progress(job_id: str, status: str, progress_pct: int,
                    stage: str, result: dict | None = None, error: str | None = None) -> None:
    """寫入 progress/<job_id>.json"""
    QUANT_PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        'job_id': job_id,
        'status': status,
        'progress_pct': progress_pct,
        'stage': stage,
        'updated_at': datetime.now().isoformat(timespec='seconds'),
    }
    if result is not None:
        payload['result'] = result
    if error is not None:
        payload['error'] = error
    _progress_file(job_id).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding='utf-8',
    )


# ────────────────────────── 非同步 job（thread 版，用於 Flask 內直接跑） ──────────────────────────

def run_quant_async() -> dict:
    """
    非同步版本：立即回 job_id，背景執行。
    使用 threading 在 Flask 行程內跑（避免 subprocess 開銷）。

    Returns:
        { ok: True, job_id: str }
        或
        { ok: False, error: str }
    """
    if not _acquire_lock():
        return {
            'ok': False,
            'error': '已有回測在跑（lock 存在）',
            'hint': '請等目前回測完成或刪除鎖檔',
        }

    job_id = uuid.uuid4().hex[:12]

    def _run():
        try:
            _write_progress(job_id, 'running', 5, '啟動')
            import quant.quant as q
            result = q.run()

            # 寫入結果
            from quant.report import save
            save(result)

            _write_progress(
                job_id, 'done', 100, '完成',
                result={'elapsed_sec': 0},  # elapsed 由 caller 在寫入時估算
            )
        except Exception as e:
            _write_progress(job_id, 'error', 0, '錯誤', error=str(e))
        finally:
            _release_lock()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return {'ok': True, 'job_id': job_id}


# ────────────────────────── 同步版（保留向後相容） ──────────────────────────

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
        last_log = last_log[-2000:]

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
                        'total_return':           round(k.get('total_return', 0) * 100, 2),
                        'pool_benchmark_return':    round(k.get('pool_benchmark_return', 0) * 100, 2),
                        'pool_excess_return':      round(k.get('pool_excess_return', 0) * 100, 2),
                        'market_benchmark_return': round(k.get('market_benchmark_return') or 0, 2),
                        'market_alpha':           round(k.get('market_alpha') or 0, 2),
                        'mdd':                   round(k.get('mdd', 0) * 100, 2),
                        'sharpe':                round(k.get('sharpe', 0), 2),
                        'rebalance_count':         k.get('rebalance_count'),
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

def get_status(job_id: str | None = None) -> dict:
    """
    查詢量化回測狀態。
    若 job_id 指定，讀 progress/<job_id>.json（非同步 job）。
    若無 job_id，回傳同步版的最後狀態。
    """
    # ── 非同步 job status ──
    if job_id:
        pf = _progress_file(job_id)
        if pf.is_file():
            try:
                data = json.loads(pf.read_text(encoding='utf-8'))
                return {
                    'job_id': job_id,
                    'status': data.get('status', 'unknown'),
                    'progress_pct': data.get('progress_pct', 0),
                    'stage': data.get('stage', ''),
                    'updated_at': data.get('updated_at'),
                    'result': data.get('result'),
                    'error': data.get('error'),
                }
            except Exception:
                pass
        return {
            'job_id': job_id,
            'status': 'not_found',
            'progress_pct': 0,
            'stage': '',
        }

    # ── 同步版（向後相容）：讀 output/backtest_results.json ──
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
                    'total_return':           k.get('total_return'),
                    'pool_benchmark_return':  k.get('pool_benchmark_return'),
                    'pool_excess_return':    k.get('pool_excess_return'),
                    'market_benchmark_return': k.get('market_benchmark_return'),
                    'market_alpha':           k.get('market_alpha'),
                    'mdd':                    k.get('mdd'),
                    'sharpe':                 k.get('sharpe'),
                    'rebalance_count':         k.get('rebalance_count'),
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
