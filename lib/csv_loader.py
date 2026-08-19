"""
Portfolio CSV Loader
讀取 (Ticker, Shares) 格式的用戶名單 CSV

支援：
- 欄位名：Ticker / 代號 / 股票代號 / Code / Symbol / Stock
- 股數欄位：Shares / 股數 / 張數 / Quantity / Qty
- 股數字串帶千分位逗號（"21,315" → 21315）
- 無 header（僅兩欄）
- 副檔名 .csv
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import IO


@dataclass(frozen=True)
class Holding:
    ticker: str
    shares: int


class CSVLintError(ValueError):
    """CSV 格式錯誤（給前端明確訊息）"""


# 常見欄位別名（lowercase 比對）
TICKER_KEYS = {'ticker', 'symbol', 'code', 'stock', 'stock_id', '代號', '股票代號', '股票代碼', '標的'}
SHARES_KEYS = {'shares', 'qty', 'quantity', 'units', '股數', '張數', '持股', '單位', '庫存'}


def _norm_key(k: str) -> str:
    return re.sub(r'\s+', '', k.strip().lower())


def _to_int_shares(raw: str) -> int:
    """支援 "21,315" / "21315" / 21315.0 / 2.5（張 → 股 若合理）"""
    s = raw.strip().replace(',', '').replace(' ', '')
    if not s:
        raise CSVLintError('股數為空')
    try:
        v = float(s)
    except ValueError:
        raise CSVLintError(f'股數不可解析: {raw!r}')
    # 整數（含小數 .0）或 5+ 位數當作「股」
    if v.is_integer():
        return int(v)
    # 帶小數且 < 100 → 視為「張」，轉股（1 張 = 1000 股）
    if v < 100:
        return int(round(v * 1000))
    raise CSVLintError(f'股數看起來不對: {raw!r}')


def load_portfolio_csv(file: IO[str] | str | Path) -> list[Holding]:
    """
    解析用戶名單 CSV。回傳 list[Holding]。
    - str  → 視為 CSV 內容
    - Path → 讀成檔案
    - IO   → 視為 file-like
    Raises:
        CSVLintError: 格式錯誤
    """
    if isinstance(file, Path):
        text = file.read_text(encoding='utf-8-sig')
    elif hasattr(file, 'read'):
        text = file.read()
    else:
        text = str(file)

    if not text.strip():
        raise CSVLintError('CSV 是空的')

    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if r and any(c.strip() for c in r)]
    if not rows:
        raise CSVLintError('CSV 是空的')

    first = rows[0]
    # 判斷是否有 header：第二行起是純數字 / 沒對應 ticker 別名 → 視為無 header
    normed = [_norm_key(c) for c in first]
    has_header = any(k in TICKER_KEYS for k in normed) or any(k in SHARES_KEYS for k in normed)

    if has_header:
        tk_idx, sh_idx = None, None
        for i, k in enumerate(normed):
            if k in TICKER_KEYS and tk_idx is None:
                tk_idx = i
            if k in SHARES_KEYS and sh_idx is None:
                sh_idx = i
        if tk_idx is None:
            raise CSVLintError(f'找不到 Ticker 欄位（支援：{", ".join(sorted(TICKER_KEYS))}）')
        if sh_idx is None:
            raise CSVLintError(f'找不到 Shares 欄位（支援：{", ".join(sorted(SHARES_KEYS))}）')
        data_rows = rows[1:]
    else:
        # 沒有 header：兩欄 = (Ticker, Shares)
        if len(first) < 2:
            raise CSVLintError('無 header CSV 必須至少兩欄 (Ticker, Shares)')
        tk_idx, sh_idx = 0, 1
        data_rows = rows

    holdings: list[Holding] = []
    seen: set[str] = set()
    for line_no, row in enumerate(data_rows, start=2 if has_header else 1):
        if len(row) <= max(tk_idx, sh_idx):
            continue
        ticker = row[tk_idx].strip().strip('"').strip()
        if not ticker:
            continue
        try:
            shares = _to_int_shares(row[sh_idx])
        except CSVLintError as e:
            raise CSVLintError(f'第 {line_no} 行：{e}') from None
        if shares <= 0:
            continue
        if ticker in seen:
            # 去重：同 ticker 累加
            for i, h in enumerate(holdings):
                if h.ticker == ticker:
                    holdings[i] = Holding(ticker, h.shares + shares)
                    break
        else:
            seen.add(ticker)
            holdings.append(Holding(ticker, shares))

    if not holdings:
        raise CSVLintError('CSV 沒有有效資料')
    return holdings


def list_profile_csvs(profile_dir: Path) -> list[str]:
    """列出 user_profile/*.csv 檔名（不含副檔名）"""
    if not profile_dir.is_dir():
        return []
    return sorted(p.stem for p in profile_dir.glob('*.csv') if p.is_file())
