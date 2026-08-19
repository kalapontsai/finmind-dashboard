"""
tests/test_portfolio.py
- 測試 3 模式 + 指標
- 用 pandas 假資料，不打 FinMind
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.portfolio import (
    BacktestError, build_portfolio, prices_to_pivot,
)


# ─────────────── 假資料產生 ───────────────
def _make_synthetic_prices(
    tickers: list[str],
    start_dates: dict[str, str],
    end_date: str = '2024-12-31',
    seed: int = 42,
) -> pd.DataFrame:
    """每支股票從自己的 start_date 開始，每天 +0.05% 噪聲"""
    rng = np.random.default_rng(seed)
    full_dates = pd.bdate_range('2000-01-01', end_date)
    df = pd.DataFrame(index=full_dates)
    for t in tickers:
        s = pd.Series(index=full_dates, dtype=float)
        start = pd.Timestamp(start_dates[t])
        idx = full_dates[full_dates >= start]
        if len(idx) == 0:
            continue
        rets = rng.normal(0.0005, 0.02, size=len(idx))
        prices = 100 * np.exp(np.cumsum(rets))
        s.loc[idx] = prices
        df[t] = s
    return df


def _make_uniform_prices(tickers: list[str], n: int = 500, seed: int = 42) -> pd.DataFrame:
    """所有股票都有完整 n 天資料（常數成長 0.05%/天）"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range('2020-01-01', periods=n)
    df = pd.DataFrame(index=dates)
    for t in tickers:
        rets = rng.normal(0.0005, 0.02, size=n)
        df[t] = 100 * np.exp(np.cumsum(rets))
    return df


# ─────────────── 測試 ───────────────
def test_mode_common_requires_overlap():
    """一支 2000 開始、一支 2023 開始 → common 模式應該裁到 2023 起，且只 1 支"""
    p = _make_synthetic_prices(
        ['A', 'B'],
        {'A': '2000-01-01', 'B': '2023-01-01'},
    )
    r = build_portfolio(p, mode='common')
    assert r.nav.index[0] >= pd.Timestamp('2023-01-01')
    assert r.metrics['years'] > 1


def test_mode_dynamic_starts_earliest():
    """dynamic 模式從最早資料日開始，會包含單獨股票的歷史"""
    p = _make_synthetic_prices(
        ['A', 'B'],
        {'A': '2000-01-01', 'B': '2023-01-01'},
    )
    r = build_portfolio(p, mode='dynamic')
    # 早期只有 A，nav 從 2000 開始
    assert r.nav.index[0] < pd.Timestamp('2023-01-01')


def test_mode_full_same_as_dynamic():
    """full 模式跟 dynamic 演算法相同（差異在 history_diag 反映完整歷史）"""
    p = _make_synthetic_prices(
        ['A', 'B'],
        {'A': '2000-01-01', 'B': '2023-01-01'},
    )
    r_dyn = build_portfolio(p, mode='dynamic')
    r_full = build_portfolio(p, mode='full')
    # NAV 應該完全一致
    pd.testing.assert_series_equal(r_dyn.nav, r_full.nav)


def test_mode_common_with_no_overlap():
    """A 跟 B 區間完全錯開 → common 模式排除 A 留下 B（單股仍可回測）"""
    p_a = _make_synthetic_prices(['A'], {'A': '2000-01-01'}, end_date='2010-12-31')
    p_b = _make_synthetic_prices(['B'], {'B': '2015-01-01'}, end_date='2020-12-31')
    p = pd.concat([p_a, p_b], axis=1)
    r = build_portfolio(p, mode='common')
    # 共同期間只能從 B 開始（2015），A 在該期間都是 NaN 被 drop
    assert r.nav.index[0] >= pd.Timestamp('2015-01-01')
    # 回測只含 B
    assert r.metrics['start'] >= '2015-01-01'


def test_metrics_basic():
    p = _make_uniform_prices(['A', 'B', 'C'], n=500)
    r = build_portfolio(p, mode='common')
    m = r.metrics
    assert m['total_return'] > 0
    assert m['cagr'] > 0
    assert m['mdd'] <= 0  # 永遠 <= 0
    assert isinstance(m['volatility'], float)
    assert m['years'] > 1


def test_history_diag_per_stock():
    p = _make_synthetic_prices(
        ['A', 'B'],
        {'A': '2000-01-01', 'B': '2023-01-01'},
    )
    r = build_portfolio(p, mode='dynamic')
    diag = r.history_diag
    assert diag['stocks'] == 2
    assert diag['per_stock']['A'] > 20
    assert diag['per_stock']['B'] < 5
    assert diag['min_years'] < diag['max_years']


def test_custom_weights_normalized():
    """自訂權重會自動 normalize"""
    p = _make_uniform_prices(['A', 'B'], n=500)
    r_equal = build_portfolio(p, mode='common')
    r_weighted = build_portfolio(
        p, mode='common',
        weights={'A': 2.0, 'B': 2.0},  # 1:1 normalize 後等於 equal
    )
    # 雖然可能不完全相等（pct_change 不連續），但長期趨勢一致
    assert abs(r_equal.metrics['total_return'] - r_weighted.metrics['total_return']) < 0.05


def test_prices_to_pivot():
    rows = {
        '2330': [
            {'date': '2024-01-02', 'close': 500.0},
            {'date': '2024-01-03', 'close': 505.0},
        ],
        '2317': [
            {'date': '2024-01-02', 'close': 80.0},
            {'date': '2024-01-03', 'close': 81.0},
        ],
    }
    pivot = prices_to_pivot(rows)
    assert pivot.shape == (2, 2)
    assert list(pivot.columns) == ['2330', '2317']
    assert pivot.iloc[0]['2330'] == 500.0


def test_prices_to_pivot_empty():
    assert prices_to_pivot({}).empty
    assert prices_to_pivot({'X': []}).empty


def test_invalid_mode():
    p = _make_uniform_prices(['A'], n=100)
    with pytest.raises(BacktestError):
        build_portfolio(p, mode='bogus')  # type: ignore[arg-type]


def test_pct_active_dynamic_varies():
    """dynamic 模式早期 active 股票數應該少"""
    p = _make_synthetic_prices(
        ['A', 'B'],
        {'A': '2000-01-01', 'B': '2023-01-01'},
    )
    r = build_portfolio(p, mode='dynamic')
    assert r.pct_active is not None
    # 第 1 天 A 已有價格（無 return）→ 算 1 檔 active
    assert r.pct_active.iloc[0] == 1
    # 2023 年以前 B 還沒進組合 → pct_active == 1
    before_2023 = r.pct_active.loc[r.pct_active.index < pd.Timestamp('2023-01-01')]
    assert (before_2023 == 1).all()
    # 2023 年以後 B 加入 → pct_active 應該是 2
    after_2023 = r.pct_active.loc[r.pct_active.index >= pd.Timestamp('2023-06-01')]
    assert (after_2023 == 2).all()
