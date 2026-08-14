"""
FinMind API Client
統一封裝 v4 API 呼叫 + 快取 + 錯誤處理
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import requests

from app_config import (
    FINMIND_API_BASE,
    FINMIND_TOKEN,
    FINMIND_RATE_LIMIT_MS,
    STOCK_LIST_CACHE_FILE,
    STOCK_LIST_CACHE_TTL,
)


class FinMindError(RuntimeError):
    """FinMind API 錯誤（HTTP / status / 解析失敗）"""


class FinMindClient:
    """FinMind API 客戶端（thread-safe rate-limit）"""

    _lock = threading.Lock()
    _last_call_ms = 0

    def __init__(self, token: str | None = None, rate_limit_ms: int = FINMIND_RATE_LIMIT_MS):
        self.token = token or FINMIND_TOKEN
        if not self.token:
            raise FinMindError(
                'FINMIND_TOKEN not found. Place it in data/finmind_token.txt '
                'or set FINMIND_TOKEN in ~/.env'
            )
        self.rate_limit_ms = rate_limit_ms
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'finmind-dashboard/2.0 (Flask)',
        })

    # ────────────────────────── 通用查詢 ──────────────────────────
    def query(self, dataset: str, params: dict | None = None) -> list[dict]:
        """
        通用查詢（data endpoint）

        自動過濾掉 null / 字串 "undefined" / 空字串（避免前端 bug 污染 URL）

        Args:
            dataset: 例如 'TaiwanStockPrice'
            params: 額外參數（data_id, start_date, end_date 等）

        Returns:
            'data' 欄位的 list

        Raises:
            FinMindError: API 回非 200、HTTP 失敗、JSON 解析失敗
        """
        clean_params: dict[str, Any] = {'dataset': dataset, 'token': self.token}
        for k, v in (params or {}).items():
            if v is None:
                continue
            if isinstance(v, str) and v.lower() in ('undefined', 'null', ''):
                continue
            clean_params[k] = v

        url = FINMIND_API_BASE
        resp = self._fetch_with_rate_limit(url, params=clean_params)
        data = resp.json()
        if not isinstance(data, dict):
            raise FinMindError(f'Invalid JSON from FinMind for {dataset}')

        status = data.get('status', 0)
        if status != 200:
            msg = data.get('msg', 'unknown')
            raise FinMindError(f'FinMind error [{dataset}]: {msg}')

        return data.get('data', [])

    # ────────────────────────── 個股清單 ──────────────────────────
    def get_stock_list(self, use_cache: bool = True) -> list[dict]:
        """
        個股清單（含 24h 快取）

        每個 stock_id 取最新一筆（含 stock_name / industry / type）
        """
        cache_file = Path(STOCK_LIST_CACHE_FILE)
        if use_cache and cache_file.is_file():
            try:
                mtime = cache_file.stat().st_mtime
                if time.time() - mtime < STOCK_LIST_CACHE_TTL:
                    cached = json.loads(cache_file.read_text(encoding='utf-8'))
                    if isinstance(cached, list):
                        return cached
            except Exception:
                pass  # 快取壞掉 → 重抓

        rows = self.query('TaiwanStockInfo')

        # 過濾 + 整理：取最新一筆（每個 stock_id 的最新 date）
        by_stock: dict[str, dict] = {}
        for r in rows:
            sid = r['stock_id']
            r_date = r.get('date', '')
            if sid not in by_stock or by_stock[sid]['date'] < r_date:
                by_stock[sid] = {
                    'date':       r_date,
                    'stock_id':   sid,
                    'stock_name': r.get('stock_name', ''),
                    'industry':   r.get('industry_category', ''),
                    'type':       r.get('type', ''),
                }

        result = sorted(by_stock.values(), key=lambda s: s['stock_id'])

        # 寫快取（簡單寫入；若需要 atomic write 留待之後）
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(result, ensure_ascii=False),
                encoding='utf-8',
            )
        except Exception:
            pass  # 寫失敗不影響回傳

        return result

    # ────────────────────────── 個股搜尋 ──────────────────────────
    def search_stock(self, q: str, limit: int = 30) -> list[dict]:
        """
        個股搜尋（5-tier 相關度排序，與原 PHP 版一致）

        優先順序：
        1) 完全匹配 stock_id
        2) 完全匹配 stock_name
        3) stock_id 前綴匹配
        4) stock_name 前綴匹配
        5) 內含匹配
        """
        all_stocks = self.get_stock_list()
        q = q.strip()
        if not q:
            return []
        q_lower = q.lower()

        # 5-tier 評分
        tier1, tier2, tier3, tier4, tier5 = [], [], [], [], []
        for s in all_stocks:
            sid = s['stock_id']
            name = s['stock_name']
            name_lower = name.lower()

            if sid == q:
                tier1.append(s)
            elif name == q:
                tier2.append(s)
            elif sid.startswith(q):
                tier3.append(s)
            elif name.startswith(q) or name_lower.startswith(q_lower):
                tier4.append(s)
            elif q in sid or q in name or q_lower in name_lower:
                tier5.append(s)

        result = tier1 + tier2 + tier3 + tier4 + tier5
        return result[:limit]

    # ────────────────────────── 帶 rate-limit 的 HTTP GET ──────────────────────────
    def _fetch_with_rate_limit(self, url: str, params: dict) -> requests.Response:
        """thread-safe 200ms rate-limit"""
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
