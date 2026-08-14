"""
多因子回測核心邏輯
- 從 FinMind 批次抓資料
- 計算 3 個因子（價值 / 動能 / 品質）
- 橫斷面百分比排名
- 每月選出 Top N，等權重持倉
- 含手續費與證交稅計算累積報酬、MDD、Sharpe
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from FinMind.data import DataLoader

import sys
# 重要：quant/ 需先加，否則 `from config import` 找不到同目錄的 config.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.cost import (
    DEFAULT_FEE_BUY, DEFAULT_FEE_SELL, DEFAULT_TAX_SELL, DEFAULT_SLIPPAGE,
)
from config import (
    EQUAL_WEIGHT, END_DATE, MARKET_BENCHMARK, MIN_LIQUIDITY_SHARES,
    MOMENTUM_LOOKBACK, START_DATE, STOCK_POOL, TOP_N, WEIGHTS, load_finmind_token,
)

CACHE_DIR = Path(__file__).parent / 'cache'

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('quant')


@dataclass
class BacktestResult:
    """回測結果"""
    close: pd.DataFrame
    total_score: pd.DataFrame
    position: pd.DataFrame
    strategy_ret: pd.Series
    strategy_net_ret: pd.Series
    cum_strategy: pd.Series
    cum_benchmark: pd.Series   # 池子等權重 B&H（舊有）
    cum_market_0050: pd.Series | None  # 0050 買進持有（雙基準新增）
    selected_monthly: dict  # {date: [stock_ids]}
    monthly_turnover: pd.Series
    monthly_cost: pd.Series
    kpis: dict
    include_dividends: bool = False   # v1.4：是否含息報酬
    adjust_method: str = 'none'      # v1.4：除權息調整方式


def fetch_data(token: str, stock_list: list[str], start: str, end: str, use_cache: bool = True, cache_stale_days: int = 7, include_dividends: bool = False):
    """用 FinMind.DataLoader 逐檔同步抓資料（帶 per-stock 快取 + retry + staleness）。

    快取策略（P3-7）:
    - 每個 (dataset_name, stock_id) 一個 parquet 檔
    - 池子變動 / 日期變動不會整批失效，只重抓需要的股票
    - 超過 cache_stale_days 天的快取視為 stale，強制重抓

    v1.4 新增：
    - include_dividends=True 時多抓 TaiwanStockDividend（回傳值加 df_div）

    注意：
    - 同 IP 使用多 token 會導致多個 token 都被封鎖 → 只用一個 token
    - FinMind Python package 的 `use_async=True` 批次會靜默吞掉例外 → 改為逐檔同步
    """
    import time

    CACHE_DIR.mkdir(exist_ok=True)
    stale_seconds = cache_stale_days * 86400

    def _is_stale(path: Path) -> bool:
        if not path.exists():
            return True
        age = time.time() - path.stat().st_mtime
        return age > stale_seconds

    def _fetch_with_retry(name, fetch_fn_single, max_retry=3):
        all_dfs = []
        skipped = []
        fetched = 0
        cached = 0

        for stock_id in stock_list:
            cache_path = CACHE_DIR / f"{name}_{stock_id}.parquet"
            if use_cache and cache_path.exists() and not _is_stale(cache_path):
                try:
                    all_dfs.append(pd.read_parquet(cache_path))
                    cached += 1
                    continue
                except Exception:
                    pass  # cache 壞了重抓

            for attempt in range(max_retry):
                try:
                    dl = DataLoader()
                    dl.login_by_token(api_token=token)
                    df = fetch_fn_single(dl, stock_id)
                    if df is None or df.empty:
                        log.info(f"  [{name}/{stock_id}] 無資料（跳過）")
                        skipped.append(stock_id)
                        break
                    all_dfs.append(df)
                    try:
                        df.to_parquet(cache_path)
                        fetched += 1
                    except Exception:
                        pass  # 寫 cache 失敗不影響結果
                    break
                except Exception as e:
                    err = str(e).lower()
                    is_rate = 'rate' in err or 'limit' in err or '402' in err or 'upper' in err or 'banned' in err
                    if is_rate and attempt < max_retry - 1:
                        wait = 30 * (attempt + 1)
                        log.warning(f"  [{name}/{stock_id}] rate limit，等 {wait}s 重試: {str(e)[:60]}")
                        time.sleep(wait)
                    else:
                        raise
            time.sleep(0.3)

        log.info(f"  {name}: cache={cached}, 新抓={fetched}, 跳過={len(skipped)}")
        if not all_dfs:
            raise RuntimeError(f"{name} 全部回傳空")
        if skipped:
            log.warning(f"  {name} 跳過 {len(skipped)} 檔無資料股票：{skipped}")
        return pd.concat(all_dfs, ignore_index=True)

    log.info(f"抓取股價 ({len(stock_list)} 檔, {start} ~ {end})")
    df_price = _fetch_with_retry(
        '股價',
        lambda dl, sid: dl.taiwan_stock_daily(stock_id=sid, start_date=start, end_date=end),
    )
    log.info(f"  → {len(df_price)} rows, {df_price['stock_id'].nunique()} 檔")

    time.sleep(2)

    log.info("抓取 PER/PBR")
    df_per = _fetch_with_retry(
        'per',
        lambda dl, sid: dl.taiwan_stock_per_pbr(stock_id=sid, start_date=start, end_date=end),
    )
    log.info(f"  → {len(df_per)} rows")

    time.sleep(2)

    log.info("抓取三大財報（用於算 ROE）")
    df_fin = _fetch_with_retry(
        'fin',
        lambda dl, sid: dl.taiwan_stock_financial_statement(stock_id=sid, start_date=start, end_date=end),
    )
    log.info(f"  → {len(df_fin)} rows, {df_fin['stock_id'].nunique()} 檔")

    df_div = None
    if include_dividends:
        time.sleep(2)
        log.info("抓取除權息資料（TaiwanStockDividend）")
        df_div = _fetch_with_retry(
            'div',
            lambda dl, sid: dl.taiwan_stock_dividend(stock_id=sid, start_date=start, end_date=end),
        )
        # 只保留有除權息事件的股票（避免空表 concat 問題）
        if df_div is not None and not df_div.empty:
            # 過濾掉全為 NaN 的事件欄位
            cash_cols = ['CashEarningsDistribution', 'StockEarningsDistribution']
            keep = df_div[
                df_div[cash_cols].notna().any(axis=1)
            ]
            log.info(f"  → {len(keep)} 筆除權息事件，{keep['stock_id'].nunique()} 檔")
            df_div = keep.reset_index(drop=True)

    return df_price, df_per, df_fin, df_div


def build_wide_tables(df_price: pd.DataFrame, df_per: pd.DataFrame, df_fin: pd.DataFrame, df_div: pd.DataFrame | None = None, adjust_method: str = 'backward'):
    """把長表 pivot 為寬表（Index=date, Columns=stock_id）。

    v1.4 新增：
    - df_div 不為 None 時，對 close 套用除權息調整（backward / forward / none）
    - 預設 backward（學術標準）
    """
    log.info("建寬表")

    close = df_price.pivot(index='date', columns='stock_id', values='close').astype(float)
    volume = df_price.pivot(index='date', columns='stock_id', values='Trading_Volume').astype(float)
    pe = df_per.pivot(index='date', columns='stock_id', values='PER').astype(float)

    # 清理：close 0 代表該日沒交易或資料缺失 → 轉 NaN，避免 pct_change 出現 inf
    close = close.replace(0, np.nan)
    log.info(f"  清理 close 0 值後有 NaN: {close.isna().sum().sum()} cells")

    # 除權息調整（v1.4）
    if df_div is not None and not df_div.empty and adjust_method != 'none':
        close = adjust_close_for_dividends(close, df_div, method=adjust_method)

    # ROE = IncomeAfterTaxes / EquityAttributableToOwnersOfParent
    log.info("計算 ROE（淨利 / 歸屬母公司權益）")
    df_fin_wide = df_fin.pivot_table(
        index=['date', 'stock_id'], columns='type', values='value',
    ).reset_index()
    df_fin_wide['ROE'] = (
        df_fin_wide['IncomeAfterTaxes'] / df_fin_wide['EquityAttributableToOwnersOfParent']
    )
    df_fin_wide['date'] = pd.to_datetime(df_fin_wide['date']).dt.strftime('%Y-%m-%d')
    roe = df_fin_wide.pivot(index='date', columns='stock_id', values='ROE').astype(float)

    # 對齊到交易日曆 + 前向填補
    pe = pe.reindex(close.index).ffill()
    roe = roe.reindex(close.index).ffill()

    log.info(f"close shape: {close.shape}, pe shape: {pe.shape}, roe shape: {roe.shape}")
    return close, volume, pe, roe


def adjust_close_for_dividends(close: pd.DataFrame, df_div: pd.DataFrame, method: str = 'backward') -> pd.DataFrame:
    """除權息調整股價（v1.4）

    Args:
        close: 寬表（Index=date, Columns=stock_id）
        df_div: TaiwanStockDividend 長表（必含欄位：stock_id,
                CashExDividendTradingDate / StockExDividendTradingDate,
                CashEarningsDistribution / StockEarningsDistribution）
        method: 'backward' / 'forward' / 'none'
            - backward（預設，學術標準）:
              F = P[ex] / (P[ex] + cash_div) × 1/(1 + stock_div_ratio)
              對 ex-date 之前的 close 乘上 F（由舊到新累計）
              → 累積報酬含息，ex-day 當日報酬約略為 0（因為股價已跌但有股利）
            - forward:
              F = (P[ex] + cash_div) / P[ex] × (1 + stock_div_ratio)
              對 ex-date 之後的 close 乘上 F
              → 維持當前價格為準
            - none: 不調整

    Returns:
        調整後的 close（DataFrame，Index/Columns 同 close）
    """
    if method == 'none' or df_div is None or df_div.empty:
        return close.copy()

    if method not in ('backward', 'forward'):
        raise ValueError(f"adjust_method 必須是 backward / forward / none, got {method!r}")

    # 台股面額（股票股利需除以面額才變成實際比率）
    PAR_VALUE = 10

    log.info(f"除權息調整（{method}）：{df_div['stock_id'].nunique()} 檔、{len(df_div)} 事件")
    close_adj = close.copy()

    # 確保 index 是 datetime（FinMind 回傳的 date 是字串）
    close_adj.index = pd.to_datetime(close_adj.index)

    # 預先將 date 欄轉 datetime
    df_div = df_div.copy()
    df_div['CashExDividendTradingDate'] = pd.to_datetime(df_div['CashExDividendTradingDate'], errors='coerce')
    df_div['StockExDividendTradingDate'] = pd.to_datetime(df_div['StockExDividendTradingDate'], errors='coerce')

    for sid in close_adj.columns:
        sid_div = df_div[df_div['stock_id'] == sid]
        if sid_div.empty:
            continue

        # 合併除息 / 除權事件（若同日，cash + stock 同事件）
        events = {}  # ex_date → {cash, stock}
        for _, row in sid_div.iterrows():
            cash_div = float(row.get('CashEarningsDistribution', 0) or 0)
            stock_div = float(row.get('StockEarningsDistribution', 0) or 0)
            cash_ex = row.get('CashExDividendTradingDate')
            stock_ex = row.get('StockExDividendTradingDate')

            if pd.notna(cash_ex) and cash_div > 0:
                d = cash_ex
                events.setdefault(d, {'cash': 0.0, 'stock': 0.0})
                events[d]['cash'] += cash_div
            if pd.notna(stock_ex) and stock_div > 0:
                d = stock_ex
                events.setdefault(d, {'cash': 0.0, 'stock': 0.0})
                events[d]['stock'] += stock_div

        if not events:
            continue

        # 對齊到交易日曆（ex-date 若非交易日，移到下一個交易日）
        for ex_date in sorted(events.keys()):
            ex_date = pd.Timestamp(ex_date)
            if ex_date in close_adj.index:
                aligned_ex = ex_date
            else:
                future = close_adj.index[close_adj.index >= ex_date]
                if len(future) == 0:
                    continue
                aligned_ex = future[0]

            ex_close = close_adj.loc[aligned_ex, sid]
            if pd.isna(ex_close) or ex_close <= 0:
                continue

            ev = events[ex_date]
            # cash_div 單位是元/股；stock_div 單位也是元/股，需除以面額 PAR_VALUE 才變比率
            stock_ratio = ev['stock'] / PAR_VALUE if ev['stock'] > 0 else 0.0
            F_cash = ex_close / (ex_close + ev['cash']) if ev['cash'] > 0 else 1.0
            F_stock = 1.0 / (1.0 + stock_ratio) if stock_ratio > 0 else 1.0
            F = F_cash * F_stock

            if method == 'backward':
                # ex-date 之前的 close 乘上 F
                mask = close_adj.index < aligned_ex
                close_adj.loc[mask, sid] = close_adj.loc[mask, sid] * F
            else:  # forward
                # ex-date 之後的 close 乘上 (1/F)
                mask = close_adj.index > aligned_ex
                close_adj.loc[mask, sid] = close_adj.loc[mask, sid] / F

    return close_adj


def compute_factors(close: pd.DataFrame, pe: pd.DataFrame, roe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """計算三因子 + 綜合分數。"""
    log.info("計算因子 + 橫斷面百分比排名")

    factor_val = pe                                     # 價值：本益比（越低越好）
    factor_mom = close.pct_change(MOMENTUM_LOOKBACK, fill_method=None)    # 動能：120 日漲幅（越高越好）
    factor_qual = roe                                    # 品質：ROE（越高越好）

    # 橫斷面百分比排名（0~1）
    score_val = factor_val.rank(axis=1, pct=True, ascending=False)
    score_mom = factor_mom.rank(axis=1, pct=True, ascending=True)
    score_qual = factor_qual.rank(axis=1, pct=True, ascending=True)

    total_score = (
        WEIGHTS['value']    * score_val.fillna(0) +
        WEIGHTS['momentum'] * score_mom.fillna(0) +
        WEIGHTS['quality']  * score_qual.fillna(0)
    )

    return total_score, factor_val, factor_mom, factor_qual


def build_position(close: pd.DataFrame, total_score: pd.DataFrame, volume: pd.DataFrame, rebalance_freq: str = 'monthly', min_liquidity_shares: int = 0) -> tuple[pd.DataFrame, dict]:
    """每月第一個交易日依總分選出 Top N，建持倉矩陣。"""
    log.info(f"每月選股 Top {TOP_N}，等權重 {EQUAL_WEIGHT:.0%}")

    close.index = pd.to_datetime(close.index)
    total_score.index = pd.to_datetime(total_score.index)
    volume.index = pd.to_datetime(volume.index)

    # 流動性過濾（20 日均量；0 = 不過濾）
    if min_liquidity_shares > 0:
        liq_filter = volume.rolling(20).mean() >= min_liquidity_shares
        log.info(f"流動性過濾: 20 日均量 >= {min_liquidity_shares:,} 張")
    else:
        liq_filter = pd.DataFrame(True, index=volume.index, columns=volume.columns)
    valid_score = total_score.where(liq_filter)

    # 計算換倉日期（依 rebalance_freq）
    available = pd.DatetimeIndex(close.index)
    rebalance_dates: list = []
    if rebalance_freq == 'quarterly':
        # 每季（3/6/9/12 月）第一個交易日
        period_dates = pd.DatetimeIndex(close.index).to_period('Q').drop_duplicates().to_timestamp().normalize()
        for p_start in period_dates:
            mask = (available >= p_start) & (available < p_start + pd.offsets.QuarterBegin(1))
            if mask.any():
                rebalance_dates.append(available[mask][0])
        log.info(f"換倉頻率: 每季 ({len(rebalance_dates)} 次)")
    elif rebalance_freq == 'daily':
        # 每日（最貴但可選）
        rebalance_dates = list(available)
        log.info(f"換倉頻率: 每日 ({len(rebalance_dates)} 次)")
    else:  # monthly（預設）
        monthly_dates = pd.DatetimeIndex(close.index).to_period('M').drop_duplicates().to_timestamp().normalize()
        for m_start in monthly_dates:
            mask = (available >= m_start) & (available < m_start + pd.offsets.MonthBegin(1))
            if mask.any():
                rebalance_dates.append(available[mask][0])
        log.info(f"換倉頻率: 每月 ({len(rebalance_dates)} 次)")

    position = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    selected = {}
    for d in rebalance_dates:
        if d not in valid_score.index:
            continue
        row = valid_score.loc[d].dropna()
        if len(row) == 0:
            continue
        top = row.nlargest(min(TOP_N, len(row))).index.tolist()
        # 從 d 當天開始持倉
        position.loc[d:, top] = EQUAL_WEIGHT
        selected[d.strftime('%Y-%m-%d')] = top

    position = position.ffill().fillna(0)
    log.info(f"  → 共 {len(selected)} 次換倉，總交易組數 {sum(len(v) for v in selected.values())}")
    return position, selected


def fetch_0050_data(token: str, start: str, end: str) -> pd.Series | None:
    """抓 0050 收盤價，對齊交易日曆。"""
    import time
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / f"0050_{start}_{end}.parquet"
    if cache_path.exists():
        log.info("  0050 讀快取")
        df = pd.read_parquet(cache_path)
    else:
        log.info(f"  抓取 0050 ({start} ~ {end})")
        try:
            dl = DataLoader()
            dl.login_by_token(api_token=token)
            df = dl.taiwan_stock_daily(stock_id='0050', start_date=start, end_date=end)
            df.to_parquet(cache_path)
        except Exception as e:
            log.warning(f"  0050 抓取失敗：{e}")
            return None
        time.sleep(2)
    if df is None or df.empty:
        return None
    close_0050 = df.pivot(index='date', columns='stock_id', values='close')['0050'].astype(float)
    close_0050.index = pd.to_datetime(close_0050.index)
    return close_0050


def run_backtest(
    close: pd.DataFrame,
    position: pd.DataFrame,
    total_score: pd.DataFrame = None,
    market_close: pd.Series = None,
) -> BacktestResult:
    """跑回測算每日策略報酬 + 成本 + KPI。"""
    log.info("計算策略每日報酬與交易成本")

    daily_ret = close.pct_change(fill_method=None).fillna(0)

    # 策略 = 前一日持倉 × 今日市場報酬
    strategy_ret = (position.shift(1) * daily_ret).sum(axis=1)
    # NaN 處理：position 可能有 NaN（股票被停牌刪除後），避免污染 cumprod
    strategy_ret = strategy_ret.fillna(0)

    # Buy & Hold 對照：只針對價格資料齊全的股票做等權重
    valid_stocks = close.columns[close.notna().any()]
    close_valid = close[valid_stocks]
    daily_ret_valid = close_valid.pct_change(fill_method=None).fillna(0)
    bench_pos = pd.DataFrame(1.0 / len(valid_stocks), index=close_valid.index, columns=close_valid.columns)
    bench_ret = (bench_pos.shift(1) * daily_ret_valid).sum(axis=1).fillna(0)

    # 換倉成本：pos_diff 絕對值分為買入側與賣出側，各自計費
    # 買入側：手續費 + 滑價；賣出側：手續費 + 證交稅 + 滑價
    pos_diff = position.diff().abs().fillna(0)
    daily_buy_turnover  = (position.shift(1) * pos_diff * close).sum(axis=1).abs()
    daily_sell_turnover = (position * pos_diff * close).sum(axis=1).abs()
    daily_cost = (
        daily_buy_turnover  * (DEFAULT_FEE_BUY  + DEFAULT_SLIPPAGE) +
        daily_sell_turnover * (DEFAULT_FEE_SELL + DEFAULT_TAX_SELL + DEFAULT_SLIPPAGE)
    )
    strategy_net_ret = strategy_ret - daily_cost

    cum_benchmark = (1 + bench_ret).cumprod()
    cum_strategy = (1 + strategy_net_ret.fillna(0)).cumprod()

    # KPI（提前定義 total_ret，給 market_alpha 用）
    total_ret = cum_strategy.iloc[-1] - 1

    # ── 市場基準 0050 B&H（雙基準） ──
    cum_market_0050 = None
    market_benchmark_return = None
    market_alpha = None
    market_daily_ret = None
    if market_close is not None:
        # 對齊到策略交易日曆
        aligned = market_close.reindex(close.index).ffill().dropna()
        if len(aligned) > 1:
            market_daily_ret = aligned.pct_change(fill_method=None).fillna(0)
            cum_market_0050 = (1 + market_daily_ret).cumprod()
            market_benchmark_return = cum_market_0050.iloc[-1] - 1
            market_alpha = total_ret - market_benchmark_return
            log.info(f"  0050 B&H: {market_benchmark_return:+.2%}  市場 alpha: {market_alpha:+.2%}")

    # KPI 其餘
    bench_total = cum_benchmark.iloc[-1] - 1
    mdd = (cum_strategy / cum_strategy.cummax() - 1).min()
    bench_mdd = (cum_benchmark / cum_benchmark.cummax() - 1).min()
    sharpe = (strategy_net_ret.mean() * 252) / (strategy_net_ret.std() * np.sqrt(252)) if strategy_net_ret.std() > 0 else 0

    # IR (Information Ratio) = 年化超額報酬 / 年化 tracking error
    # 用 0050 作為市場基準；對齊交易日曆
    information_ratio = None
    if market_daily_ret is not None and len(market_daily_ret) > 1:
        excess_daily = (strategy_net_ret - market_daily_ret).dropna()
        if len(excess_daily) > 1 and excess_daily.std() > 0:
            information_ratio = (excess_daily.mean() * 252) / (excess_daily.std() * np.sqrt(252))

    monthly_turnover = (position.diff().abs().sum(axis=1).resample('MS').sum() / 2)
    monthly_cost = daily_cost.resample('MS').sum()
    # 年化換手率 = 平均月換倉 × 12 ÷ 平均持倉股數
    avg_position_size = position.sum(axis=1).mean()
    annual_turnover = (monthly_turnover.mean() * 12) / avg_position_size if avg_position_size > 0 else None

    kpis = {
        'total_return':           total_ret,
        'pool_benchmark_return': bench_total,        # 池子等權重 B&H
        'pool_excess_return':     total_ret - bench_total,  # 池子 alpha
        'market_benchmark_return': market_benchmark_return,  # 0050 B&H（雙基準）
        'market_alpha':           market_alpha,            # 市場 alpha
        'mdd':                    mdd,
        'pool_benchmark_mdd':    bench_mdd,
        'sharpe':                 sharpe,
        'information_ratio':     information_ratio,         # IR vs 0050
        'trading_days':           len(strategy_net_ret),
        'rebalance_count':        int(monthly_turnover[monthly_turnover > 0].count()),
        'avg_monthly_turnover':   monthly_turnover.mean(),
        'annual_turnover':        annual_turnover,
        'total_cost':             daily_cost.sum(),
    }

    return BacktestResult(
        close=close,
        total_score=total_score,
        position=position,
        strategy_ret=strategy_ret,
        strategy_net_ret=strategy_net_ret,
        cum_strategy=cum_strategy,
        cum_benchmark=cum_benchmark,
        cum_market_0050=cum_market_0050,
        selected_monthly={},
        monthly_turnover=monthly_turnover,
        monthly_cost=monthly_cost,
        kpis=kpis,
        include_dividends=False,   # 同步版不含息
        adjust_method='none',
    )


def run() -> BacktestResult:
    """主入口：抓資料 → 算因子 → 建倉 → 回測 → KPI。"""
    token = load_finmind_token()
    log.info(f"使用 FinMind token ...{token[-8:]}")

    df_price, df_per, df_fin, _ = fetch_data(token, STOCK_POOL, START_DATE, END_DATE)
    close, volume, pe, roe = build_wide_tables(df_price, df_per, df_fin)

    # 過濾：股價全空 / 全缺的股票
    valid_stocks = close.columns[close.notna().any()]
    if len(valid_stocks) < len(close.columns):
        dropped = set(close.columns) - set(valid_stocks)
        log.warning(f"以下股票完全無資料，已從 pool 移除：{sorted(dropped)}")
        close = close[valid_stocks]
        volume = volume[valid_stocks]
        pe = pe[valid_stocks]
        roe = roe[valid_stocks]

    total_score, fval, fmom, fqual = compute_factors(close, pe, roe)
    position, selected = build_position(close, total_score, volume)

    # 抓 0050 市場基準（雙基準）
    market_close = None
    if MARKET_BENCHMARK:
        market_close = fetch_0050_data(token, START_DATE, END_DATE)

    result = run_backtest(close, position, total_score, market_close=market_close)
    result.selected_monthly = selected
    result.include_dividends = False
    result.adjust_method = 'none'

    # 印 KPI
    k = result.kpis
    log.info("=" * 60)
    log.info(f"策略總報酬:   {k['total_return']:+.2%}")
    log.info(f"池子 B&H:    {k['pool_benchmark_return']:+.2%}")
    log.info(f"池子 alpha:  {k['pool_excess_return']:+.2%}")
    if k.get('market_benchmark_return') is not None:
        log.info(f"0050 B&H:    {k['market_benchmark_return']:+.2%}")
        log.info(f"市場 alpha:  {k['market_alpha']:+.2%}")
    log.info(f"MDD:         {k['mdd']:.2%}")
    log.info(f"Sharpe:      {k['sharpe']:.2f}")
    log.info(f"換倉次數:    {k['rebalance_count']}")
    log.info("=" * 60)

    return result


if __name__ == '__main__':
    result = run()
    print("\nSelected monthly:")
    for d, stocks in result.selected_monthly.items():
        print(f"  {d}: {stocks}")