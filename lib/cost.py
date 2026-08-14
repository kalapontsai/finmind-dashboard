"""
統一成本計算模型
- 個股回測（lib/backtest.py）與量化回測（quant/quant.py）共用這份
- 台股實際費率：買入手續費 0.1425%，賣出手續費 0.1425% + 證交稅 0.3%，滑價 0.1%
"""

from __future__ import annotations


# ─── 預設值（台股實際費率） ───
DEFAULT_FEE_BUY: float = 0.001425   # 買入手續費 0.1425%
DEFAULT_FEE_SELL: float = 0.001425  # 賣出手續費 0.1425%
DEFAULT_TAX_SELL: float = 0.003     # 證交稅 0.3%
DEFAULT_SLIPPAGE: float = 0.001     # 滑價 0.1%（下單價與成交價差）


def cost(
    buy_turnover: float,
    sell_turnover: float,
    fee_buy: float = DEFAULT_FEE_BUY,
    fee_sell: float = DEFAULT_FEE_SELL,
    tax_sell: float = DEFAULT_TAX_SELL,
    slippage: float = DEFAULT_SLIPPAGE,
) -> dict:
    """
    計算完整交易成本。

    買入：cost_buy = turnover * (fee_buy + slippage)
          實際可用於買股的金額 = turnover - cost_buy
          干擾金額（ fees + slippage ）也從 cash 扣除

    賣出：cost_sell = turnover * (fee_sell + tax_sell + slippage)
          實際收到 cash = turnover - cost_sell

    Args:
        buy_turnover:  買入時的名义成交金額（shares * buy_price）
        sell_turnover: 賣出時的名义成交金額（shares * sell_price）
        fee_buy:       買入手續費率（預設 0.1425%）
        fee_sell:      賣出手續費率（預設 0.1425%）
        tax_sell:      賣出證交稅率（預設 0.3%）
        slippage:      滑價率（預設 0.1%，買賣雙方都計）

    Returns:
        dict: {
            'cost_buy':      float,   # 買入端總成本（手續費 + 滑價）
            'cost_sell':     float,   # 賣出端總成本（手續費 + 證交稅 + 滑價）
            'total_cost':    float,   # 來回總成本
            'net_buy_qty':   float,   # 扣除成本後，每單位 turnover 可買到的股數（= 1 - fee_buy - slippage）
            'net_sell_rate': float,   # 扣除成本後，每單位 turnover 實收比例（= 1 - fee_sell - tax_sell - slippage）
        }
    """
    cost_buy = buy_turnover * (fee_buy + slippage)
    cost_sell = sell_turnover * (fee_sell + tax_sell + slippage)
    total_cost = cost_buy + cost_sell

    # 每單位 turnover 扣除成本後的比例（可用來算「多少现金能買到多少股」）
    net_buy_qty = 1.0 - fee_buy - slippage          # 買入時
    net_sell_rate = 1.0 - fee_sell - tax_sell - slippage  # 賣出時

    return {
        'cost_buy':     cost_buy,
        'cost_sell':    cost_sell,
        'total_cost':   total_cost,
        'net_buy_qty':  net_buy_qty,
        'net_sell_rate': net_sell_rate,
    }


def buy_amount(cash: float, price: float, **kwargs) -> tuple[int, float]:
    """
    根據「有上限的現金」計算可買股數及實際成本。
    適用於 lib/backtest.py（全現金買入情境）。

    Returns:
        (shares, actual_cost)
        actual_cost 含手續費 + 滑價，直接從 cash 扣除
    """
    fee_buy   = kwargs.get('fee_buy',   DEFAULT_FEE_BUY)
    slippage  = kwargs.get('slippage',  DEFAULT_SLIPPAGE)

    # 買入時滑價：假設成交價比報價高（對使用者不利）
    buy_price = price * (1 + slippage)
    gross_turnover = cash
    c = cost(
        buy_turnover=gross_turnover,
        sell_turnover=0,
        fee_buy=fee_buy,
        slippage=slippage,
        **{k: v for k, v in kwargs.items() if k in ('fee_sell', 'tax_sell')}
    )

    # 可用於買股的淨額（扣成本）
    net_cash = gross_turnover - c['cost_buy']
    shares = int(net_cash / buy_price)
    if shares == 0:
        return 0, 0.0

    # 重新算精確成本（用實際買入量）
    actual_turnover = shares * buy_price
    actual_cost = actual_turnover * (fee_buy + slippage)
    return shares, actual_cost


def sell_amount(shares: int, price: float, **kwargs) -> tuple[float, float]:
    """
    根據股數計算賣出後實收現金。
    適用於 lib/backtest.py（全部賣出情境）。

    Returns:
        (proceeds, actual_cost)
        proceeds 為扣除成本後實拿金額
        actual_cost 含手續費 + 證交稅 + 滑價
    """
    fee_sell  = kwargs.get('fee_sell',  DEFAULT_FEE_SELL)
    tax_sell  = kwargs.get('tax_sell',  DEFAULT_TAX_SELL)
    slippage  = kwargs.get('slippage',  DEFAULT_SLIPPAGE)

    # 賣出時滑價：假設成交價比報價低（對使用者不利）
    sell_price = price * (1 - slippage)
    gross_turnover = shares * sell_price
    actual_cost = gross_turnover * (fee_sell + tax_sell + slippage)
    proceeds = gross_turnover - actual_cost
    return proceeds, actual_cost
