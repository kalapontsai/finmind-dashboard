"""cost.py unit tests — v1.4 P3-2（股寶重寫，2026-08-15）

原始版本（d0990fd）呼叫了不存在的 total_cost_round_trip + cash-only API，
與 lib/cost.py 實際 (cash, price) 雙參數介面不符，pytest 收集直接失敗。
重寫後用實際存在的 cost() / buy_amount(cash, price) / sell_amount(shares, price) API。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 確保 lib 可被 import
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.cost import (  # noqa: E402
    DEFAULT_FEE_BUY,
    DEFAULT_FEE_SELL,
    DEFAULT_TAX_SELL,
    DEFAULT_SLIPPAGE,
    buy_amount,
    sell_amount,
    cost,
)


def test_defaults_are_positive():
    assert DEFAULT_FEE_BUY > 0
    assert DEFAULT_FEE_SELL > 0
    assert DEFAULT_TAX_SELL > 0
    assert DEFAULT_SLIPPAGE > 0


def test_defaults_match_tw_stock_fees():
    """台股實際費率：買 0.1425% / 賣 0.1425% + 證交稅 0.3% / 滑價 0.1%"""
    assert DEFAULT_FEE_BUY == 0.001425
    assert DEFAULT_FEE_SELL == 0.001425
    assert DEFAULT_TAX_SELL == 0.003
    assert DEFAULT_SLIPPAGE == 0.001


def test_cost_round_trip_dict():
    """cost() 回傳 dict，round-trip 總成本 = 買 (fee+slip) + 賣 (fee+tax+slip)
    對 10000 名義成交：10000 × (0.001425+0.001) + 10000 × (0.001425+0.003+0.001)
    = 10000 × 0.002425 + 10000 × 0.005425
    = 24.25 + 54.25 = 78.50
    """
    c = cost(buy_turnover=10000, sell_turnover=10000)
    assert abs(c['cost_buy'] - 24.25) < 0.01
    assert abs(c['cost_sell'] - 54.25) < 0.01
    assert abs(c['total_cost'] - 78.50) < 0.01
    assert abs(c['net_buy_qty'] - 0.997575) < 1e-6
    assert abs(c['net_sell_rate'] - 0.994575) < 1e-6


def test_buy_amount_subtracts_fee_and_slippage():
    """buy_amount(cash, price) 回傳 (shares, actual_cost)
    10000 元 @ 50 元/股：gross=10000，cost_buy=10000×0.002425=24.25
    net_cash=9975.75，buy_price=50×1.001=50.05
    shares=int(9975.75/50.05)=199，actual_cost=199×50.05×0.002425
    """
    shares, actual_cost = buy_amount(10000, 50)
    assert shares == 199  # int(9975.75 / 50.05) = 199
    assert actual_cost > 0
    assert actual_cost < 24.25  # actual ≤ theoretical


def test_sell_amount_subtracts_fee_tax_and_slippage():
    """sell_amount(shares, price) 回傳 (proceeds, actual_cost)
    100 股 @ 50 元/股：sell_price=50×0.999=49.95
    gross=4995，actual_cost=4995×0.005425=27.097
    proceeds=4995-27.097=4967.903
    """
    proceeds, actual_cost = sell_amount(100, 50)
    assert abs(actual_cost - 27.097) < 0.01
    assert abs(proceeds - 4967.90) < 0.01


def test_zero_shares_returns_zero_proceeds():
    """賣 0 股 → proceeds 應為 0"""
    proceeds, actual_cost = sell_amount(0, 50)
    assert proceeds == 0
    assert actual_cost == 0