"""
策略回測引擎
- 支援 MA / RSI / KD / MACD 四種策略
- AND / OR 觸發模式
- 頻率：每日 / 每月指定日期
- 每次觸發「全部現金買入」或「全部庫存賣出」（不支援部位管理）
"""
from __future__ import annotations

import json
import math
import time
import uuid
from datetime import datetime
from pathlib import Path

from app_config import BACKTEST_RESULTS_FILE, BACKTEST_RESULTS_MAX


# ────────────────────────── 指標計算 ──────────────────────────
def calc_ma(closes: list[float], short: int, long: int) -> tuple[list, list]:
    """簡單移動平均（與前端 Indicators.sma 等效）"""
    n = len(closes)
    ma_s = [None] * n
    ma_l = [None] * n
    sum_s = 0.0
    sum_l = 0.0
    for i, c in enumerate(closes):
        sum_s += c
        if i >= short:
            sum_s -= closes[i - short]
        sum_l += c
        if i >= long:
            sum_l -= closes[i - long]
        if i >= short - 1:
            ma_s[i] = sum_s / short
        if i >= long - 1:
            ma_l[i] = sum_l / long
    return ma_s, ma_l


def calc_rsi(closes: list[float], period: int) -> list:
    """RSI (Wilder smoothing)"""
    n = len(closes)
    rsi = [None] * n
    if n < period + 1:
        return rsi
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_g = gains / period
    avg_l = losses / period
    rsi[period] = 100 - 100 / (1 + avg_g / avg_l) if avg_l > 0 else 100
    for i in range(period + 1, n):
        diff = closes[i] - closes[i - 1]
        g = diff if diff > 0 else 0
        l = -diff if diff < 0 else 0
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
        rsi[i] = 100 - 100 / (1 + avg_g / avg_l) if avg_l > 0 else 100
    return rsi


def calc_kd(highs: list[float], lows: list[float], closes: list[float],
            period: int, k_sm: int, d_sm: int) -> tuple[list, list]:
    """KD 隨機指標（EMA 型平滑）"""
    n = len(closes)
    k = [None] * n
    d = [None] * n
    prev_k = 50.0
    prev_d = 50.0
    for i in range(n):
        if i < period - 1:
            continue
        h = max(highs[i - period + 1:i + 1])
        l = min(lows[i - period + 1:i + 1])
        rsv = 50.0 if h == l else round((closes[i] - l) / (h - l) * 100, 2)
        k[i] = round(prev_k * (k_sm - 1) / k_sm + rsv / k_sm, 2)
        d[i] = round(prev_d * (d_sm - 1) / d_sm + k[i] / d_sm, 2)
        prev_k = k[i]
        prev_d = d[i]
    return k, d


def calc_macd(closes: list[float], fast: int, slow: int, signal: int) -> tuple[list, list, list]:
    """MACD"""
    n = len(closes)
    k_f = 2 / (fast + 1)
    k_s = 2 / (slow + 1)
    k_m = 2 / (signal + 1)

    ema_f = []
    ema_s = []
    prev_f = closes[0]
    prev_s = closes[0]
    for i in range(n):
        if i == 0:
            prev_f = closes[i]
            prev_s = closes[i]
        else:
            prev_f = closes[i] * k_f + prev_f * (1 - k_f)
            prev_s = closes[i] * k_s + prev_s * (1 - k_s)
        ema_f.append(prev_f)
        ema_s.append(prev_s)

    dif = [ema_f[i] - ema_s[i] for i in range(n)]
    macd = []
    prev_m = dif[0]
    for i in range(n):
        if i == 0:
            prev_m = dif[i]
        else:
            prev_m = dif[i] * k_m + prev_m * (1 - k_m)
        macd.append(prev_m)

    osc = [dif[i] - macd[i] for i in range(n)]
    return dif, macd, osc


# ────────────────────────── 主回測函數 ──────────────────────────
def run_backtest(
    rows: list[dict],
    capital: float,
    strategies: dict,
    combine_mode: str = 'OR',
    frequency: str = 'day',
    month_day: int = 15,
) -> dict:
    """
    執行回測

    Args:
        rows: FinMind TaiwanStockPrice 回傳的原始 list
              每筆含 date / open / max / min / close / ... 等
        capital: 初始資金
        strategies: {
            'ma':   {'enabled': bool, 'short': int, 'long': int},
            'rsi':  {'enabled': bool, 'period': int, 'low': float, 'high': float},
            'kd':   {'enabled': bool, 'period': int, 'k_smooth': int, 'd_smooth': int, 'low': float, 'high': float},
            'macd': {'enabled': bool, 'fast': int, 'slow': int, 'signal': int},
        }
        combine_mode: 'OR' 或 'AND'
        frequency: 'day' 或 'month'
        month_day: 1-31 (frequency=month 才有)

    Returns:
        dict: 完整回測結果
    """
    n = len(rows)
    if n == 0:
        raise ValueError('No price data')

    dates = [r['date'] for r in rows]
    opens = [float(r['open']) for r in rows]
    highs = [float(r['max']) for r in rows]
    lows = [float(r['min']) for r in rows]
    closes = [float(r['close']) for r in rows]

    # ── 動作日索引 ──
    frequency = frequency.lower()
    if frequency not in ('day', 'month'):
        frequency = 'day'
    month_day = max(1, min(31, int(month_day)))

    action_day_idx = []
    action_dates = []
    if frequency == 'month':
        processed_months = set()
        for i in range(n):
            ym = dates[i][:7]
            if ym in processed_months:
                continue
            processed_months.add(ym)
            for j in range(i, n):
                if dates[j][:7] != ym:
                    break
                day = int(dates[j][8:10])
                if day >= month_day:
                    action_day_idx.append(j)
                    action_dates.append(dates[j])
                    break
    else:
        action_day_idx = list(range(n))
        action_dates = list(dates)
    action_set = set(action_day_idx)

    # ── 計算指標 ──
    ma_s, ma_l = (calc_ma(closes, int(strategies['ma']['short']), int(strategies['ma']['long']))
                  if strategies['ma'].get('enabled') else (None, None))
    rsi = calc_rsi(closes, int(strategies['rsi']['period'])) if strategies['rsi'].get('enabled') else None
    kd_k, kd_d = (calc_kd(highs, lows, closes,
                          int(strategies['kd']['period']),
                          int(strategies['kd']['k_smooth']),
                          int(strategies['kd']['d_smooth']))
                  if strategies['kd'].get('enabled') else (None, None))
    macd_def = (calc_macd(closes,
                          int(strategies['macd']['fast']),
                          int(strategies['macd']['slow']),
                          int(strategies['macd']['signal']))
                if strategies['macd'].get('enabled') else None)
    macd_dif, macd_line, macd_osc = macd_def if macd_def else (None, None, None)

    # ── 每日訊號評估 ──
    signals = [{'buy': [], 'sell': []} for _ in range(n)]
    for i in range(1, n):
        # MA 黃金 / 死亡交叉
        if ma_s is not None and ma_s[i - 1] is not None and ma_l[i - 1] is not None and ma_s[i] is not None and ma_l[i] is not None:
            if ma_s[i - 1] <= ma_l[i - 1] and ma_s[i] > ma_l[i]:
                signals[i]['buy'].append('MA_GOLDEN')
            if ma_s[i - 1] >= ma_l[i - 1] and ma_s[i] < ma_l[i]:
                signals[i]['sell'].append('MA_DEATH')

        # RSI 超賣 / 超買
        if rsi is not None and rsi[i] is not None:
            if rsi[i] < strategies['rsi']['low']:
                signals[i]['buy'].append('RSI_OVERSOLD')
            if rsi[i] > strategies['rsi']['high']:
                signals[i]['sell'].append('RSI_OVERBOUGHT')

        # KD
        if kd_k is not None and kd_k[i] is not None and kd_d[i] is not None:
            if kd_k[i] < strategies['kd']['low'] and kd_k[i] > kd_d[i]:
                signals[i]['buy'].append('KD_OVERSOLD')
            if kd_k[i] > strategies['kd']['high'] and kd_k[i] < kd_d[i]:
                signals[i]['sell'].append('KD_OVERBOUGHT')

        # MACD 柱狀翻正 / 翻負
        if macd_osc is not None and macd_osc[i - 1] is not None and macd_osc[i] is not None:
            if macd_osc[i - 1] <= 0 and macd_osc[i] > 0:
                signals[i]['buy'].append('MACD_BUY')
            if macd_osc[i - 1] >= 0 and macd_osc[i] < 0:
                signals[i]['sell'].append('MACD_SELL')

    # ── AND / OR 組合 ──
    combine_mode = 'AND' if str(combine_mode).upper() == 'AND' else 'OR'
    enabled_count = sum(int(bool(strategies[k].get('enabled'))) for k in ('ma', 'rsi', 'kd', 'macd'))

    final_buy = [False] * n
    final_sell = [False] * n
    for i in range(n):
        b = len(signals[i]['buy']) > 0
        s = len(signals[i]['sell']) > 0
        if combine_mode == 'AND':
            b_match = len(signals[i]['buy']) == enabled_count
            s_match = len(signals[i]['sell']) == enabled_count
            final_buy[i] = enabled_count > 0 and b_match
            final_sell[i] = enabled_count > 0 and s_match
        else:
            final_buy[i] = b
            final_sell[i] = s

    # ── 逐日交易 ──
    cash = float(capital)
    shares = 0
    nav = [0.0] * n
    buy_hold_nav = [0.0] * n
    trades = []

    init_buy_hold_shares = int(math.floor(capital / closes[0]))

    for i in range(n):
        price = closes[i]
        is_action_day = i in action_set

        if is_action_day and final_buy[i] and shares == 0 and cash > 0:
            qty = int(math.floor(cash / price))
            if qty > 0:
                cost = qty * price
                cash -= cost
                shares += qty
                trades.append({
                    'date': dates[i],
                    'action': 'BUY',
                    'price': price,
                    'qty': qty,
                    'amount': cost,
                })
        elif is_action_day and final_sell[i] and shares > 0:
            proceeds = shares * price
            cash += proceeds
            trades.append({
                'date': dates[i],
                'action': 'SELL',
                'price': price,
                'qty': shares,
                'amount': proceeds,
            })
            shares = 0

        nav[i] = cash + shares * price
        buy_hold_nav[i] = init_buy_hold_shares * price + (capital - init_buy_hold_shares * closes[0])

    # ── KPI ──
    final_nav = nav[n - 1]
    total_ret = (final_nav - capital) / capital

    # 年化報酬：用實際天數（不考慮 252 交易日，224 數值差別小）
    days = max(1, (datetime.strptime(dates[n - 1], '%Y-%m-%d') - datetime.strptime(dates[0], '%Y-%m-%d')).days)
    ann_ret = (final_nav / capital) ** (365.0 / days) - 1 if days > 0 else 0

    # MDD
    peak = nav[0]
    mdd = 0.0
    for v in nav:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > mdd:
            mdd = dd

    # 勝率（逐對計算 buy/sell pair）
    buys = [t for t in trades if t['action'] == 'BUY']
    sells = [t for t in trades if t['action'] == 'SELL']
    pairs = min(len(buys), len(sells))
    wins = 0
    losses = 0
    for i in range(pairs):
        if sells[i]['price'] > buys[i]['price']:
            wins += 1
        else:
            losses += 1
    win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0

    bh_final = buy_hold_nav[n - 1]
    bh_ret = (bh_final - capital) / capital

    return {
        'start_date': dates[0],
        'end_date': dates[n - 1],
        'trading_days': n,
        'action_days': len(action_day_idx),
        'frequency': frequency,
        'month_day': month_day if frequency == 'month' else None,
        'capital': capital,
        'final_nav': round(final_nav, 0),
        'total_return': round(total_ret * 100, 2),
        'annual_return': round(ann_ret * 100, 2),
        'max_drawdown': round(mdd * 100, 2),
        'win_rate': round(win_rate * 100, 2),
        'trade_count': len(trades),
        'buy_hold_return': round(bh_ret * 100, 2),
        'equity_curve': [round(v, 0) for v in nav],
        'buy_hold_curve': [round(v, 0) for v in buy_hold_nav],
        'dates': dates,
        'prices': [round(v, 2) for v in closes],
        'trades': trades,
        'signals': [{'buy': s['buy'], 'sell': s['sell']} for s in signals],
        'indicators': {
            'ma': (
                [{'short': round(ma_s[i], 2) if ma_s[i] is not None else None,
                  'long': round(ma_l[i], 2) if ma_l[i] is not None else None}
                 for i in range(n)]
                if ma_s is not None else None
            ),
            'rsi': [round(v, 2) if v is not None else None for v in rsi] if rsi else None,
            'kd': (
                [{'k': round(kd_k[i], 2) if kd_k[i] is not None else None,
                  'd': round(kd_d[i], 2) if kd_d[i] is not None else None}
                 for i in range(n)]
                if kd_k is not None else None
            ),
            'macd': (
                [{'dif': round(macd_dif[i], 3),
                  'macd': round(macd_line[i], 3),
                  'osc': round(macd_osc[i], 3)}
                 for i in range(n)]
                if macd_dif is not None else None
            ),
        },
        'combine_mode': combine_mode,
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }


# ────────────────────────── 儲存歷史 ──────────────────────────
def save_backtest_summary(stock_id: str, result: dict) -> None:
    """append-only 儲存回測摘要（最多 50 筆）"""
    summary = {
        'id': 'bt_' + uuid.uuid4().hex[:12],
        'stock_id': stock_id,
        'start_date': result['start_date'],
        'end_date': result['end_date'],
        'total_return': result['total_return'],
        'annual_return': result['annual_return'],
        'max_drawdown': result['max_drawdown'],
        'win_rate': result['win_rate'],
        'trade_count': result['trade_count'],
        'buy_hold_return': result['buy_hold_return'],
        'combine_mode': result['combine_mode'],
        'frequency': result['frequency'],
        'month_day': result['month_day'],
        'created_at': result['created_at'],
    }

    history = []
    if BACKTEST_RESULTS_FILE.is_file():
        try:
            history = json.loads(BACKTEST_RESULTS_FILE.read_text(encoding='utf-8'))
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []

    history.insert(0, summary)
    history = history[:BACKTEST_RESULTS_MAX]

    BACKTEST_RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    BACKTEST_RESULTS_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
