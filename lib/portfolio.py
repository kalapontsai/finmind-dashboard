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
    """動態加入：每日只用當天有資料的股票，權重重新正規化"""
    r = _safe_pct_change(p)
    vals: list[float] = []
    n_active_list: list[int] = []
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
        w_valid = w_valid / s
        vals.append(float((valid_rets * w_valid).sum()))
        n_active_list.append(int(len(valid_prices)))
    pr = pd.Series(vals, index=p.index, name='portfolio_return')
    n_active = pd.Series(n_active_list, index=p.index, dtype=float)
    return pr, n_active


def _safe_pct_change(p: pd.DataFrame) -> pd.DataFrame:
    """pct_change + 過濾 inf（FinMind 偶爾回傳壞資料，造成單股 return=inf）"""
    r = p.pct_change(fill_method=None)
    return r.replace([np.inf, -np.inf], np.nan)


def _mode_full(p: pd.DataFrame, w: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Full Available History：每支股票從最早資料開始算（!= 0 報酬）"""
    # 跟 dynamic 一樣：每日只看當天有資料的股票、權重正規化
    # 但 history_diag 會反映每支股票自己的「完整歷史長度」
    return _mode_dynamic(p, w)


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
