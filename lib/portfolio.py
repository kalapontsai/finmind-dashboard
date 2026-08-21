"""
Portfolio Backtest
- 3 種歷史模式：Common / Dynamic / Full
- 共用：Portfolio NAV + 指標（CAGR / MDD / Vol / Sharpe）
- 個股歷史長度摘要
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd


Mode = Literal['common', 'dynamic', 'full']


@dataclass
class PortfolioResult:
    mode: str
    nav: pd.Series                # NAV index = Date
    daily_return: pd.Series       # daily portfolio return
    metrics: dict
    history_diag: dict            # 個股歷史長度
    pct_active: pd.Series | None = None  # 每日 active 股票數（dynamic 才有）

    def to_dict(self) -> dict:
        return {
            'mode': self.mode,
            'metrics': self.metrics,
            'history_diag': self.history_diag,
            'pct_active': self.pct_active.to_dict() if self.pct_active is not None else None,
        }


# ───────── Custom Errors ─────────
class BacktestError(ValueError):
    pass


# ───────── Entry point ─────────
def build_portfolio(
    prices: pd.DataFrame,
    mode: Mode,
    weights: dict[str, float] | None = None,
) -> PortfolioResult:
    """
    prices: pivot table，index=Date, columns=Ticker, values=Close
            必須包含所有用戶持有的 ticker，缺值表示該日該股尚未上市或缺資料

    回傳 PortfolioResult：
      - nav: Portfolio NAV（起點 1.0）
      - daily_return: 每日組合 return
      - metrics: {start, end, years, total_return, cagr, mdd, volatility, sharpe}
      - history_diag: {stocks, min_years, median_years, max_years, per_stock: {ticker: years}}
    """
    if not isinstance(prices, pd.DataFrame):
        raise BacktestError('prices 必須是 DataFrame')
    if prices.empty:
        raise BacktestError('價格資料為空')
    if mode not in ('common', 'dynamic', 'full'):
        raise BacktestError(f'mode 必須是 common / dynamic / full，得到 {mode!r}')

    p = prices.sort_index().replace([np.inf, -np.inf], np.nan)
    tickers = list(p.columns)

    # 統一權重（normalize）
    if weights:
        w = pd.Series(weights, dtype=float).reindex(tickers).fillna(0)
    else:
        w = pd.Series(1.0, index=tickers)
    if w.sum() <= 0:
        raise BacktestError('權重總和為 0，請檢查 weights 設定')
    w = w / w.sum()

    if mode == 'common':
        pr, n_active = _mode_common(p, w)
    elif mode == 'dynamic':
        pr, n_active = _mode_dynamic(p, w)
    else:  # full
        pr, n_active = _mode_full(p, w)

    if pr.empty:
        raise BacktestError(f'模式 {mode} 沒有可計算的報酬資料')

    nav = (1 + pr.fillna(0)).cumprod()

    # 個股歷史長度診斷
    history_diag = _history_diag(prices)

    return PortfolioResult(
        mode=mode,
        nav=nav,
        daily_return=pr,
        metrics=_metrics(nav),
        history_diag=history_diag,
        pct_active=n_active,
    )


# ───────── 3 種模式 ─────────
def _mode_common(p: pd.DataFrame, w: pd.Series) -> tuple[pd.Series, pd.Series]:
    """共同期間：所有股票都有資料才進組合"""
    starts = p.notna().idxmax()  # 第一個有效日期（每支股票）
    starts = starts.dropna()  # 過濾掉完全沒資料的欄位
    if starts.empty:
        raise BacktestError('所有股票都沒有歷史價格資料')
    common_start = starts.max()
    p = p.loc[common_start:].dropna(axis=1, how='any')
    if p.shape[1] == 0:
        raise BacktestError('沒有共同歷史期間（所有股票起點都不重疊）')
    w = w.reindex(p.columns).fillna(0)
    if w.sum() <= 0:
        raise BacktestError('共同期間內所有指定權重都為 0')
    w = w / w.sum()
    r = _safe_pct_change(p)
    pr = r.mul(w, axis=1).sum(axis=1, min_count=1)
    n_active = pd.Series(p.notna().sum(axis=1), index=p.index, dtype=float)
    return pr, n_active


def _mode_dynamic(p: pd.DataFrame, w: pd.Series) -> tuple[pd.Series, pd.Series]:
    """動態加入：每日只用當天有資料的股票，權重重新正規化

    加權重上限避免早期股票被放大（驗收標準 #8a）：
    - 原本: 1 個 stock active 時被正規化為 100% weight → early period MDD 被盢大
    - 修法: cap_per_stock = 1.5 / n_total（最多放大 1.5 倍）→ 早期股票不會獨大
      → 1 stock active 時上限 16.7%（vs 原本 100%）
      → 4+ stocks active 時 normal 運作

    跟 full 的差別保留：
    - dynamic: dropna + renormalize（cap 以避免極端）
    - full: fillna(0) + fixed weights（從第一天就以原重計入）
    """
    r = _safe_pct_change(p)
    vals: list[float] = []
    n_active_list: list[int] = []
    n_total = len(w)
    cap_per_stock = 1.5 / n_total if n_total > 0 else 1.0  # 最多放大 1.5 倍
    # n_active 以「當天有有效價格的股票數」算（更直觀，反映「組合含多少檔」）
    for date, row_p in p.iterrows():
        valid_prices = row_p.dropna()
        if valid_prices.empty:
            vals.append(0.0)
            n_active_list.append(0)
            continue
        # 對應的 return（已過濾 inf）
        ret_row = r.loc[date]
        valid_rets = ret_row.dropna()
        if valid_rets.empty:
            vals.append(0.0)
            n_active_list.append(int(len(valid_prices)))
            continue
        w_valid = w.reindex(valid_rets.index).fillna(0)
        s = w_valid.sum()
        if s <= 0:
            vals.append(0.0)
            n_active_list.append(int(len(valid_prices)))
            continue
        # 原本: w_valid = w_valid / s (完全正規化 → 1 個 stock 被放大為 100%)
        # 修法: 先正規化、再 cap 每檔上限
        w_normalized = w_valid / s
        w_capped = w_normalized.clip(upper=cap_per_stock)
        # 如果 cap 生效，sum 會 < 1（不是 100% allocation）→ 保留原意
        vals.append(float((valid_rets * w_capped).sum()))
        n_active_list.append(int(len(valid_prices)))
    pr = pd.Series(vals, index=p.index, name='portfolio_return')
    n_active = pd.Series(n_active_list, index=p.index, dtype=float)
    return pr, n_active


def _safe_pct_change(p: pd.DataFrame) -> pd.DataFrame:
    """pct_change + 過濾 inf（FinMind 偶爾回傳壞資料，造成單股 return=inf）"""
    r = p.pct_change(fill_method=None)
    return r.replace([np.inf, -np.inf], np.nan)


def _mode_full(p: pd.DataFrame, w: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Full Available History：每支股票從自己最早資料開始算（fixed weights, fillna(0)）

    跟 dynamic 的關鍵差別：
    - dynamic: 每日重新正規化權重（早期股票被放大）
    - full: 固定權重 + fillna(0)（早期股票不放大，避免 MDD 被讇大）

    驗收標準 #7 #8:
    - Full 跟 Dynamic 的 metrics 不會完全相同（因為 full 不重新正規化）
    - Full 的 MDD 應該比 Dynamic 小（因為沒有重複增強早期股票 contribution）
    """
    r = _safe_pct_change(p)
    # fillna(0) 而不是 dropna: 未上市的股票當天 return = 0（代表不在 portfolio）
    # 不重新正規化權重
    r_filled = r.fillna(0)
    pr = r_filled.mul(w, axis=1).sum(axis=1, min_count=1)
    n_active = pd.Series(p.notna().sum(axis=1), index=p.index, dtype=float)
    return pr, n_active


# ───────── 指標 ─────────
def _metrics(nav: pd.Series) -> dict:
    if nav.empty or len(nav) < 2:
        raise BacktestError('NAV 資料點不足')
    r = nav.pct_change().dropna()
    yrs = max((nav.index[-1] - nav.index[0]).days / 365.25, 1 / 365.25)
    peak = nav.cummax()
    dd = nav / peak - 1
    if len(r) > 1:
        vol = float(r.std(ddof=1) * np.sqrt(252))
        sharpe = float(r.mean() / r.std(ddof=1) * np.sqrt(252)) if r.std(ddof=1) > 0 else float('nan')
    else:
        vol = float('nan')
        sharpe = float('nan')
    total_return = float(nav.iloc[-1] / nav.iloc[0] - 1) if nav.iloc[0] else float('nan')
    cagr = float((nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1) if nav.iloc[0] > 0 else float('nan')
    return {
        'start': str(nav.index[0].date()),
        'end': str(nav.index[-1].date()),
        'years': float(yrs),
        'total_return': total_return,
        'cagr': cagr,
        'mdd': float(dd.min()),
        'volatility': vol,
        'sharpe': sharpe,
    }


# ───────── Benchmark 對照 ─────────
def build_benchmark(
    bench_prices: pd.DataFrame,
    ticker: str = 'BENCH',
) -> dict:
    """
    拿單一 ticker 的股價算 benchmark 指標（對照組）。
    同一個价格序列、同一套 metrics 公式。
    """
    if bench_prices.empty or ticker not in bench_prices.columns:
        return {'ticker': ticker, 'metrics': None}
    s = bench_prices[ticker].dropna()
    if len(s) < 2:
        return {'ticker': ticker, 'metrics': None}
    nav = s / s.iloc[0]
    metrics = _metrics(nav)
    return {
        'ticker': ticker,
        'stock_id': ticker,
        'metrics': metrics,
        'nav': [{'date': str(d.date()), 'nav': float(v)} for d, v in nav.items()],
    }


def _history_diag(prices: pd.DataFrame) -> dict:
    """計算每支股票的歷史長度（年）"""
    per_stock = {}
    levels = []
    for t in prices.columns:
        s = prices[t].dropna()
        if s.empty:
            per_stock[t] = 0.0
            continue
        yrs = (s.index[-1] - s.index[0]).days / 365.25
        per_stock[t] = float(yrs)
        levels.append(yrs)
    if not levels:
        return {'stocks': 0, 'min_years': 0.0, 'median_years': 0.0, 'max_years': 0.0, 'per_stock': {}}
    return {
        'stocks': int(len(levels)),
        'min_years': float(min(levels)),
        'median_years': float(pd.Series(levels).median()),
        'max_years': float(max(levels)),
        'per_stock': {k: round(v, 2) for k, v in per_stock.items()},
    }


# ───────── 工具：把 FinMind rows 轉 pivot ─────────
def prices_to_pivot(rows_by_ticker: dict[str, list[dict]], price_col: str = 'close') -> pd.DataFrame:
    """
    把 FinMind 抓回來的 {ticker: [{date, open, max, min, close, ...}]}
    轉成 pd.DataFrame：index=Date, columns=Ticker, values=price_col
    """
    frames = []
    for ticker, rows in rows_by_ticker.items():
        if not rows:
            continue
        df = pd.DataFrame(rows)
        if 'date' not in df.columns or price_col not in df.columns:
            continue
        df = df[['date', price_col]].copy()
        df['date'] = pd.to_datetime(df['date'])
        df.columns = ['Date', ticker]
        frames.append(df.set_index('Date'))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1).sort_index()


# ───────── 工具：起始市值（最後收盤價 × 股數）─────────
def compute_market_value(
    prices: pd.DataFrame,
    shares: dict[str, int],
    as_of: str | None = None,
) -> dict:
    """
    計算組合當前市值。
    prices: pivot 表（index=Date, columns=Ticker, values=close）
    shares: {ticker: 股數}
    as_of: 'YYYY-MM-DD' 或 None（None = 最後一個共同交易日）
    回傳：
      {
        'as_of': str (date),
        'total': int (總市值),
        'per_stock': [{ticker, close, shares, value}],
        'missing': [ticker, ...]  # 該 ticker 在該日沒資料
      }
    """
    if prices.empty or not shares:
        return {'as_of': None, 'total': 0, 'per_stock': [], 'missing': list(shares.keys())}

    if as_of:
        # 找 <= as_of 的最後一個共同交易日
        target = pd.Timestamp(as_of)
        mask = prices.index <= target
        if not mask.any():
            target_date = prices.index[0]
        else:
            target_date = prices.index[mask][-1]
    else:
        target_date = prices.index[-1]

    per_stock = []
    missing = []
    total = 0
    for t, n in shares.items():
        if t not in prices.columns:
            missing.append(t)
            continue
        close = float(prices.loc[:target_date, t].dropna().iloc[-1]) if prices.loc[:target_date, t].notna().any() else 0
        if close <= 0:
            missing.append(t)
            continue
        value = int(round(close * n))
        total += value
        per_stock.append({
            'ticker': t,
            'close': round(close, 2),
            'shares': n,
            'value': value,
        })

    return {
        'as_of': str(target_date.date()),
        'total': int(total),
        'per_stock': per_stock,
        'missing': missing,
    }


# ───────── 工具：個股歷史長度診斷（加強版）─────────
def per_stock_history(
    prices: pd.DataFrame,
    shares: dict[str, int] | None = None,
) -> dict:
    """
    計算每支股票的歷史長度（年）+ 在 shares 中可買到的初始市值（用最早一天的價格）
    """
    per = {}
    for t in prices.columns:
        s = prices[t].dropna()
        if s.empty:
            per[t] = {
                'years': 0.0,
                'start': None,
                'end': None,
                'rows': 0,
                'first_close': None,
                'last_close': None,
            }
            continue
        per[t] = {
            'years': round((s.index[-1] - s.index[0]).days / 365.25, 2),
            'start': str(s.index[0].date()),
            'end': str(s.index[-1].date()),
            'rows': int(len(s)),
            'first_close': round(float(s.iloc[0]), 2),
            'last_close': round(float(s.iloc[-1]), 2),
        }
    return per
