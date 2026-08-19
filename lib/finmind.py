"""
FinMind API Client
- 200ms thread-safe rate-limit
- 24h 價格快取（JSON in data/price_cache/<ticker>.json）
- 兩段式 token 載入：config/finmind-api-key → ~/.env
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests


# ───────── Constants ─────────
FINMIND_API_BASE = 'https://api.finmindtrade.com/api/v4/data'
RATE_LIMIT_MS = 200
PRICE_CACHE_TTL_SECONDS = 86400  # 24h

# 兩段式 token 來源（優先順序：config/finmind-api-key → ~/.env）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_KEY_FILE = _PROJECT_ROOT / 'config' / 'finmind-api-key'
ENV_FILE = Path.home() / '.env'


# ───────── Errors ─────────
class FinMindError(RuntimeError):
    """FinMind API 錯誤（HTTP / 解析 / token 缺失）"""


# ───────── Token 載入 ─────────
def _parse_local_config_file(path: Path) -> dict:
    """
    解析 config/finmind-api-key 格式：
      ACCOUNT = "x"
      PASSWORD = "y"
      FINMIND_TOKEN=eyJ...
    """
    out: dict = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        v = v.strip()
        # 剝單/雙引號
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        out[k.strip()] = v
    return out


def _parse_env_file(path: Path) -> dict:
    """解析 ~/.env（Key=Value 格式）"""
    return _parse_local_config_file(path)


def load_finmind_token() -> str:
    """
    兩段式讀取：
      1) config/finmind-api-key 的 FINMIND_TOKEN
      2) ~/.env 的 FINMIND_TOKEN
    """
    cfg = _parse_local_config_file(CONFIG_KEY_FILE)
    tok = cfg.get('FINMIND_TOKEN', '').strip()
    if tok:
        return tok
    env = _parse_env_file(ENV_FILE)
    return env.get('FINMIND_TOKEN', '').strip()


# ───────── Client ─────────
class FinMindClient:
    """Thread-safe FinMind API client（200ms rate-limit + 24h 價格快取）"""

    _lock = threading.Lock()
    _last_call_ms = 0

    def __init__(
        self,
        token: str | None = None,
        rate_limit_ms: int = RATE_LIMIT_MS,
        cache_dir: Path | None = None,
        cache_ttl_seconds: int = PRICE_CACHE_TTL_SECONDS,
    ):
        self.token = token or load_finmind_token()
        if not self.token:
            raise FinMindError(
                'FINMIND_TOKEN not found. Place it in config/finmind-api-key '
                'or set FINMIND_TOKEN in ~/.env'
            )
        self.rate_limit_ms = rate_limit_ms
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'stock-portfolio-forecast/1.0 (Flask)'})
        self.cache_dir = cache_dir or (_PROJECT_ROOT / 'data' / 'price_cache')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_seconds = cache_ttl_seconds

    # ────────── 通用 query ──────────
    def query(self, dataset: str, params: dict | None = None) -> list[dict]:
        clean: dict[str, Any] = {'dataset': dataset, 'token': self.token}
        for k, v in (params or {}).items():
            if v is None:
                continue
            if isinstance(v, str) and v.lower() in ('undefined', 'null', ''):
                continue
            clean[k] = v
        resp = self._fetch(FINMIND_API_BASE, params=clean)
        data = resp.json()
        if not isinstance(data, dict):
            raise FinMindError(f'Invalid JSON from FinMind for {dataset}')
        if data.get('status', 0) != 200:
            raise FinMindError(f"FinMind error [{dataset}]: {data.get('msg', 'unknown')}")
        return data.get('data', [])

    # ────────── TaiwanStockPrice（with cache + ticker 自動試 variants） ──────────
    def get_stock_price(
        self,
        stock_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        use_cache: bool = True,
    ) -> list[dict]:
        """
        取得台股歷史股價（單一股）。
        start_date / end_date 格式 YYYY-MM-DD；不給 → 從 2000-01-01 抓到今天。
        24h 內同 ticker 會用本地 JSON cache（fetch 區間落在 cache 內時直接退回 cache）。

        自動試 variants：
          - 原文
          - 補 0 到 4 碼（純數字）
          - 補 0 到 6 碼（純數字 4 碼）
          - upper（字母型）
        哪個拿到資料就用哪個。
        """
        stock_id = stock_id.strip()
        if not stock_id:
            raise FinMindError('stock_id required')

        end_dt = datetime.strptime(end_date, '%Y-%m-%d') if end_date else datetime.now()
        start_dt = datetime.strptime(start_date, '%Y-%m-%d') if start_date else datetime(2000, 1, 1)
        if start_dt > end_dt:
            raise FinMindError('start_date > end_date')

        candidates = self._ticker_variants(stock_id)
        last_err: FinMindError | None = None
        for cand in candidates:
            try:
                rows = self._get_stock_price_single(cand, start_dt, end_dt, use_cache)
                if rows:
                    return self._slice_rows(rows, start_dt, end_dt)
            except FinMindError as e:
                last_err = e
                # 繼續試下一個 variant
                continue
        # 全部 variants 都拿不到 → 拋最後一個錯誤
        if last_err:
            raise last_err
        raise FinMindError(
            f'查無 {stock_id} 資料（試過 {candidates}）。'
            '若是新上 ETF 或已下市股票，請從名單移除。'
        )

    @staticmethod
    def _ticker_variants(stock_id: str) -> list[str]:
        """產生 ticker 候選清單（去掉重複，保留順序）"""
        out: list[str] = []
        seen: set[str] = set()
        for t in [stock_id, stock_id.upper(), stock_id.strip()]:
            if t and t not in seen:
                out.append(t)
                seen.add(t)
        # 純數字 ticker 加補 0 變體
        if stock_id.isdigit():
            for n in (4, 5, 6):
                z = stock_id.zfill(n)
                if z not in seen:
                    out.append(z)
                    seen.add(z)
        return out

    # ────────── 批次抓多股 ──────────
    def get_many_prices(
        self,
        stock_ids: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
        use_cache: bool = True,
    ) -> dict[str, list[dict]]:
        """
        批次抓取多股歷史價格；用 200ms rate-limit 順序呼叫。
        回傳 {stock_id: [{date, open, max, min, close, ...}]}
        """
        out: dict[str, list[dict]] = {}
        for sid in stock_ids:
            try:
                out[sid] = self.get_stock_price(sid, start_date, end_date, use_cache=use_cache)
            except FinMindError as e:
                # 單股失敗不中斷整批；記在 _error 欄位
                out[sid] = []
                out[f'{sid}._error'] = str(e)  # type: ignore[assignment]
        return out

    # ────────── 內部：單一股票（不試 variants） ──────────
    def _get_stock_price_single(
        self,
        stock_id: str,
        start_dt: datetime,
        end_dt: datetime,
        use_cache: bool,
    ) -> list[dict]:
        """單一 stock_id 抓價 + cache（不試 variants）"""
        cache_file = self.cache_dir / f'{stock_id}.json'

        # 1) cache 命中
        if use_cache and cache_file.is_file():
            cache = self._load_cache(cache_file)
            if cache and self._cache_covers(cache, start_dt, end_dt):
                return self._slice_rows(cache['rows'], start_dt, end_dt)

        # 2) 抓
        rows = self.query('TaiwanStockPrice', {
            'data_id': stock_id,
            'start_date': start_dt.strftime('%Y-%m-%d'),
            'end_date': end_dt.strftime('%Y-%m-%d'),
        })

        # 3) 寫 cache（合併）
        if use_cache:
            old_rows = []
            if cache_file.is_file():
                old = self._load_cache(cache_file)
                if old:
                    old_rows = old.get('rows', [])
            merged = self._merge_rows(old_rows, rows)
            self._write_cache(cache_file, stock_id, merged)

        return rows

    # ────────── Cache 工具 ──────────
    @staticmethod
    def _merge_rows(old: list[dict], new: list[dict]) -> list[dict]:
        """去重 + 排序（按 date）"""
        by_date: dict[str, dict] = {}
        for r in old + new:
            d = r.get('date')
            if not d:
                continue
            by_date[d] = r
        return sorted(by_date.values(), key=lambda x: x['date'])

    @staticmethod
    def _slice_rows(rows: list[dict], start_dt: datetime, end_dt: datetime) -> list[dict]:
        return [
            r for r in rows
            if start_dt <= datetime.strptime(r['date'], '%Y-%m-%d') <= end_dt
        ]

    @staticmethod
    def _cache_covers(cache: dict, start_dt: datetime, end_dt: datetime) -> bool:
        try:
            ts = cache.get('fetched_at', 0)
            if time.time() - ts > PRICE_CACHE_TTL_SECONDS:
                return False
            rows = cache.get('rows', [])
            if not rows:
                return False
            first = datetime.strptime(rows[0]['date'], '%Y-%m-%d')
            last = datetime.strptime(rows[-1]['date'], '%Y-%m-%d')
            return first <= start_dt and last >= end_dt
        except (KeyError, ValueError, TypeError):
            return False

    @staticmethod
    def _load_cache(path: Path) -> dict | None:
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _write_cache(path: Path, stock_id: str, rows: list[dict]) -> None:
        payload = {
            'stock_id': stock_id,
            'fetched_at': time.time(),
            'fetched_at_iso': datetime.now().isoformat(timespec='seconds'),
            'row_count': len(rows),
            'rows': rows,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')

    # ────────── HTTP ──────────
    def _fetch(self, url: str, params: dict) -> requests.Response:
        with self._lock:
            now_ms = int(time.monotonic() * 1000)
            gap = now_ms - self._last_call_ms
            if gap < self.rate_limit_ms:
                time.sleep((self.rate_limit_ms - gap) / 1000.0)
            self._last_call_ms = int(time.monotonic() * 1000)
        try:
            resp = self.session.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            raise FinMindError(f'Network error: {e}') from e
        if resp.status_code != 200:
            raise FinMindError(f'HTTP {resp.status_code}: {resp.text[:200]}')
        return resp
