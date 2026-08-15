"""cost.py unit tests — v1.4 P3-2"""
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
    total_cost_round_trip,
)


def test_defaults_are_positive():
    assert DEFAULT_FEE_BUY > 0
    assert DEFAULT_FEE_SELL > 0
    assert DEFAULT_TAX_SELL > 0
    assert DEFAULT_SLIPPAGE > 0


def test_buy_amount_subtracts_fee_and_slippage():
    # 10000 * (1 - 0.001425 - 0.001) = 10000 * 0.997575 = 9975.75
    amount = buy_amount(10000)
    assert abs(amount - 9975.75) < 0.01


def test_sell_amount_subtracts_fee_tax_and_slippage():
    # 10000 * (1 - 0.001425 - 0.003 - 0.001) = 10000 * 0.994575 = 9945.75
    amount = sell_amount(10000)
    assert abs(amount - 9945.75) < 0.01


def test_round_trip_cost_matches_calibration():
    # 驗證 default fees/tax/slippage 的 round-trip cost
    rt = total_cost_round_trip(10000)
    # 買 0.1425% + 賣 0.1425% + 證交稅 0.3% + 滑價 0.2%（雙邊）
    # = 0.7850% of 10000 = 78.5
    assert abs(rt - 78.50) < 0.01


def test_zero_amount_returns_zero():
    assert buy_amount(0) == 0
    assert sell_amount(0) == 0
    assert total_cost_round_trip(0) == 0
