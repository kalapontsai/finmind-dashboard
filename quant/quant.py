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

from config import (
    COMMISSION, EQUAL_WEIGHT, END_DATE, MIN_LIQUIDITY_SHARES, MOMENTUM_LOOKBACK,
    START_DATE, STOCK_POOL, TAX, TOP_N, WEIGHTS, load_finmind_token,
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
    cum_benchmark: pd.Series
    selected_monthly: dict  # {date: [stock_ids]}
    monthly_turnover: pd.Series
    monthly_cost: pd.Series
    kpis: dict


def fetch_data(token: str, stock_list: list[str], start: str, end: str, use_cache: bool = True):
    """用 FinMind.DataLoader 逐檔同步抓資料（帶磁碟快取 + retry）。

    注意：
    - 同 IP 使用多 token 會導致多個 token 都被封鎖 → 只用一個 token
    - FinMind Python package 的 `use_async=True` 批次會靜默吞掉例外 → 改為逐檔同步
    """
    import time

    CACHE_DIR.mkdir(exist_ok=True)
    cache_key = f"{'-'.join(sorted(stock_list))}_{start}_{end}".replace('/', '_').replace(' ', '_')[:120]

    def _fetch_with_retry(name, fetch_fn_single, max_retry=3):
        cache_path = CACHE_DIR / f"{name}_{cache_key}.parquet"
        if use_cache and cache_path.exists():
            log.info(f"  {name} 讀快取：{cache_path.name}")
            return pd.read_parquet(cache_path)

        all_dfs = []
        skipped = []
        for stock_id in stock_list:
            for attempt in range(max_retry):
                try:
                    dl = DataLoader()
                    dl.login_by_token(api_token=token)
                    df = fetch_fn_single(dl, stock_id)
                    if df is None or df.empty:
                        log.info(f"  [{name}/{stock_id}] 無資料（跳過）")
                        skipped.append(stock_id)
                        break    # 跳過這個股票但不報錯
                    all_dfs.append(df)
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
            time.sleep(0.5)

        if not all_dfs:
            raise RuntimeError(f"{name} 全部回傳空")
        if skipped:
            log.warning(f"  {name} 跳過 {len(skipped)} 檔無資料股票：{skipped}")
        df_combined = pd.concat(all_dfs, ignore_index=True)
        df_combined.to_parquet(cache_path)
        return df_combined

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

    return df_price, df_per, df_fin


def build_wide_tables(df_price: pd.DataFrame, df_per: pd.DataFrame, df_fin: pd.DataFrame):
    """把長表 pivot 為寬表（Index=date, Columns=stock_id）。"""
    log.info("建寬表")

    close = df_price.pivot(index='date', columns='stock_id', values='close').astype(float)
    volume = df_price.pivot(index='date', columns='stock_id', values='Trading_Volume').astype(float)
    pe = df_per.pivot(index='date', columns='stock_id', values='PER').astype(float)

    # 清理：close 0 代表該日沒交易或資料缺失 → 轉 NaN，避免 pct_change 出現 inf
    close = close.replace(0, np.nan)
    log.info(f"  清理 close 0 值後有 NaN: {close.isna().sum().sum()} cells")

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


def build_position(close: pd.DataFrame, total_score: pd.DataFrame, volume: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """每月第一個交易日依總分選出 Top N，建持倉矩陣。"""
    log.info(f"每月選股 Top {TOP_N}，等權重 {EQUAL_WEIGHT:.0%}")

    close.index = pd.to_datetime(close.index)
    total_score.index = pd.to_datetime(total_score.index)
    volume.index = pd.to_datetime(volume.index)

    # 流動性過濾（20 日均量）
    liq_filter = volume.rolling(20).mean() >= MIN_LIQUIDITY_SHARES if MIN_LIQUIDITY_SHARES > 0 else pd.DataFrame(True, index=volume.index, columns=volume.columns)
    valid_score = total_score.where(liq_filter)

    # 每月第一個交易日（用 close.index 處理 datetime mismatch）
    monthly_dates = pd.DatetimeIndex(close.index).to_period('M').drop_duplicates().to_timestamp().normalize()
    # 取每月該月內第一個交易日（與 close 重疊的那一天）
    available = pd.DatetimeIndex(close.index)
    actual_monthly = []
    for m_start in monthly_dates:
        mask = (available >= m_start) & (available < m_start + pd.offsets.MonthBegin(1))
        if mask.any():
            actual_monthly.append(available[mask][0])

    position = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    selected = {}
    for d in actual_monthly:
        if d not in valid_score.index:
            continue
        row = valid_score.loc[d].dropna()
        if len(row) == 0:
            continue
        top = row.nlargest(min(TOP_N, len(row))).index.tolist()
        # 從 d 當天開始持倉（每月第一個交易日買進）
        position.loc[d:, top] = EQUAL_WEIGHT
        selected[d.strftime('%Y-%m-%d')] = top

    position = position.ffill().fillna(0)
    log.info(f"  → 共 {len(selected)} 次換倉，總交易組數 {sum(len(v) for v in selected.values())}")
    return position, selected


def run_backtest(close: pd.DataFrame, position: pd.DataFrame, total_score: pd.DataFrame = None) -> BacktestResult:
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

    # 換倉成本：pos_diff 絕對值，買+賣各半
    pos_diff = position.diff().abs()
    cost_per_unit = COMMISSION + TAX / 2          # 平均成本率（手續費 + 一半稅）
    daily_cost = pos_diff.sum(axis=1) * cost_per_unit
    strategy_net_ret = strategy_ret - daily_cost

    cum_benchmark = (1 + bench_ret).cumprod()
    cum_strategy = (1 + strategy_net_ret.fillna(0)).cumprod()

    # KPI
    total_ret = cum_strategy.iloc[-1] - 1
    bench_total = cum_benchmark.iloc[-1] - 1
    mdd = (cum_strategy / cum_strategy.cummax() - 1).min()
    bench_mdd = (cum_benchmark / cum_benchmark.cummax() - 1).min()
    sharpe = (strategy_net_ret.mean() * 252) / (strategy_net_ret.std() * np.sqrt(252)) if strategy_net_ret.std() > 0 else 0

    monthly_turnover = position.diff().abs().sum(axis=1).resample('MS').sum()
    monthly_cost = daily_cost.resample('MS').sum()

    kpis = {
        'total_return':     total_ret,
        'benchmark_return': bench_total,
        'excess_return':    total_ret - bench_total,
        'mdd':              mdd,
        'benchmark_mdd':    bench_mdd,
        'sharpe':           sharpe,
        'trading_days':     len(strategy_net_ret),
        'rebalance_count':  int(monthly_turnover[monthly_turnover > 0].count()),  # 月換倉次數（與 log 一致）
        'avg_monthly_turnover': monthly_turnover.mean(),
        'total_cost':       daily_cost.sum(),
    }

    return BacktestResult(
        close=close,
        total_score=total_score,
        position=position,
        strategy_ret=strategy_ret,
        strategy_net_ret=strategy_net_ret,
        cum_strategy=cum_strategy,
        cum_benchmark=cum_benchmark,
        selected_monthly={},
        monthly_turnover=monthly_turnover,
        monthly_cost=monthly_cost,
        kpis=kpis,
    )


def run() -> BacktestResult:
    """主入口：抓資料 → 算因子 → 建倉 → 回測 → KPI。"""
    token = load_finmind_token()
    log.info(f"使用 FinMind token ...{token[-8:]}")

    df_price, df_per, df_fin = fetch_data(token, STOCK_POOL, START_DATE, END_DATE)
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

    result = run_backtest(close, position, total_score)
    result.selected_monthly = selected

    # 印 KPI
    k = result.kpis
    log.info("=" * 60)
    log.info(f"策略總報酬:   {k['total_return']:+.2%}")
    log.info(f"B&H 對照:    {k['benchmark_return']:+.2%}")
    log.info(f"超額報酬:    {k['excess_return']:+.2%}")
    log.info(f"MDD:        {k['mdd']:.2%}")
    log.info(f"Sharpe:     {k['sharpe']:.2f}")
    log.info(f"換倉次數:   {k['rebalance_count']}")
    log.info("=" * 60)

    return result


if __name__ == '__main__':
    result = run()
    print("\nSelected monthly:")
    for d, stocks in result.selected_monthly.items():
        print(f"  {d}: {stocks}")