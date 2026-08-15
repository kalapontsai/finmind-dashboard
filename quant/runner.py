"""
Quant Runner — 接 strategies 組合與回測參數
- 從 lib.strategy_store 載入 params
- 用 strategies/ 模組計算各 strategy 分數
- 加權組合成總分（支援 z-score / rank 標準化）
- 跑回測算 KPI

介面：
    run(config: dict) -> BacktestResult
    config = {
        'pool': ['2330', '2317', ...],                  # 股票池
        'strategies': [                                  # 啟用的 strategy 列表
            {'name': 'value', 'enabled': True, 'weight': 0.4, 'params': {...}},
            {'name': 'momentum', 'enabled': True, 'weight': 0.3},
            {'name': 'quality', 'enabled': True, 'weight': 0.3},
        ],
        'rebalance_freq': 'monthly',                    # 'daily' / 'monthly'
        'top_n': 5,
        'fee_buy': 0.001425, 'fee_sell': 0.001425,
        'tax_sell': 0.003, 'slippage': 0.001,
        'start': '2023-01-01', 'end': '2026-08-12',
        'use_cache': True,
        'token': '...',                                 # 預設從 app_config 讀
    }
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

# 讓 runner 可獨立 import（也讓 quant.quant 可 import）
import sys
_ROOT = Path(__file__).resolve().parent.parent
_QUANT_DIR = Path(__file__).resolve().parent
# 重要：quant/ 需先於 root，否則 quant.py 內 `from config import` 找不到
if str(_QUANT_DIR) not in sys.path:
    sys.path.insert(0, str(_QUANT_DIR))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app_config import FINMIND_TOKEN  # noqa: E402
from lib.cost import (  # noqa: E402
    DEFAULT_FEE_BUY, DEFAULT_FEE_SELL, DEFAULT_TAX_SELL, DEFAULT_SLIPPAGE,
)
from lib.strategy_store import load as load_strategy_params  # noqa: E402

from quant.strategies import get_strategy_class  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('runner')


# ─── 預設 config ───
DEFAULT_CONFIG = {
    'pool': None,                 # None → 從 pool.txt 載入
    'strategies': [
        {'name': 'value', 'enabled': True, 'weight': 0.40},
        {'name': 'momentum', 'enabled': True, 'weight': 0.30},
        {'name': 'quality', 'enabled': True, 'weight': 0.30},
    ],
    'rebalance_freq': 'monthly',
    'top_n': 5,
    'equal_weight': None,         # None = 1 / top_n
    'min_liquidity_shares': 0,
    'fee_buy': DEFAULT_FEE_BUY,
    'fee_sell': DEFAULT_FEE_SELL,
    'tax_sell': DEFAULT_TAX_SELL,
    'slippage': DEFAULT_SLIPPAGE,
    'start': '2023-01-01',
    'end': '2026-08-12',
    'use_cache': True,
    'token': None,                # None → 用 FINMIND_TOKEN
    'include_dividends': False,   # v1.4：是否含息（True 多抓 TaiwanStockDividend）
    'adjust_method': 'backward',  # v1.4：除權息調整方式 backward/forward/none
    'walk_forward': False,        # v1.4：walk-forward 樣本外驗證（預設關閉）
    'train_pct': 0.7,             # v1.4：訓練期占比（驗證期 = 1 - train_pct）
}


def merge_config(user_cfg: dict) -> dict:
    """合併使用者 config 與預設值（深度 merge strategies list 的 params）。"""
    cfg = {k: (v if not isinstance(v, (list, dict)) else list(v) if isinstance(v, list) else {**v})
           for k, v in DEFAULT_CONFIG.items()}

    if not user_cfg:
        return cfg

    for k, v in user_cfg.items():
        if k == 'strategies' and isinstance(v, list):
            # 以 user 為主（整個 list 替換）
            cfg[k] = list(v)
        else:
            cfg[k] = v

    return cfg


def load_strategies(strategies_cfg: list[dict]) -> list:
    """從 config 載入啟用的 strategy 實例（套用 params）。"""
    instances = []
    for s in strategies_cfg:
        if not s.get('enabled', True):
            continue

        name = s.get('name')
        if not name:
            raise ValueError(f'strategy 必須有 name 欄位: {s}')

        # 從硬碟 params 載入預設，再覆蓋使用者指定
        try:
            stored = load_strategy_params(name)
            base_params = stored.get('params', {})
        except FileNotFoundError:
            base_params = {}

        # user 提供的 params 優先
        merged_params = {**base_params, **(s.get('params') or {})}

        cls = get_strategy_class(name)
        inst = cls(params=merged_params)
        instances.append(inst)
        log.info(f'  ✓ {name} (weight={s.get("weight", 0):.2f}, params={merged_params})')

    if not instances:
        raise ValueError('沒有啟用的 strategy')

    total_weight = sum(s.get('weight', 0) for s in strategies_cfg if s.get('enabled', True))
    if abs(total_weight - 1.0) > 0.01:
        log.warning(f'啟用 strategy 權重總和 = {total_weight:.3f}（建議 = 1.0）')

    return instances


def _zscore_standardize(score: pd.DataFrame) -> pd.DataFrame:
    """
    對每個時間點（row）橫斷面 z-score 標準化：(x - mean) / std
    - NaN 不參與 mean/std 計算，標準化後仍 NaN
    - 若該 row 全為 NaN 或 std=0，回 NaN / 0
    """
    mean = score.mean(axis=1)
    std = score.std(axis=1)
    # 避免除以 0
    std = std.replace(0, np.nan)
    standardized = score.sub(mean, axis=0).div(std, axis=0)
    return standardized


def combine_scores(
    strategy_results: list,
    weights: dict[str, float],
    standardize: str = 'rank',
) -> pd.DataFrame:
    """
    加權組合各 strategy 的排名矩陣。

    Args:
        strategy_results: list of StrategyResult
        weights: {strategy_type: weight}
        standardize: 'rank' (預設，向後相容) 或 'zscore'
            - 'rank': 直接加權（與舊 quant.py 相容）；NaN → 0
            - 'zscore': 每個 strategy 先 z-score 標準化（mean=0, std=1），
              再加權組合成 total_score

    Returns:
        DataFrame (Index=date, Columns=stock_id)，加權後的綜合分數
    """
    if standardize not in ('rank', 'zscore'):
        raise ValueError(f'standardize 必須是 rank 或 zscore, got {standardize!r}')

    score_df = None

    for sr in strategy_results:
        w = weights.get(sr.type, 0)
        if w == 0:
            continue

        if standardize == 'zscore':
            # 先 z-score 標準化（NaN 不參與計算）
            score_use = _zscore_standardize(sr.score)
            # NaN → 0 加權（參與綜合分數計算）
            masked = score_use.fillna(0)
        else:
            # rank 模式：直接 NaN → 0 加權
            masked = sr.score.fillna(0)

        if score_df is None:
            score_df = masked * w
        else:
            score_df = score_df.add(masked * w, fill_value=0)

    if score_df is None:
        raise RuntimeError('沒有 strategy 計算出結果')

    return score_df


def run(user_cfg: dict | None = None):
    """
    跑完整回測（從抓資料到算 KPI）。
    回傳 BacktestResult（沿用 quant.quant 的 dataclass）。
    """
    # 動態 import 避免循環依賴
    from quant.quant import (
        BacktestResult, fetch_data, build_wide_tables,
        build_position, run_backtest, fetch_0050_data,
    )
    from lib.pool_loader import load_pool

    cfg = merge_config(user_cfg)

    # ── 1. 股票池 ──
    pool = cfg['pool']
    if pool is None:
        pool = load_pool()
        log.info(f'從 pool.txt 載入 {len(pool)} 檔')

    # ── 2. Strategy 載入 ──
    log.info(f'載入 strategies...')
    instances = load_strategies(cfg['strategies'])
    weights = {s['name']: s.get('weight', 0) for s in cfg['strategies'] if s.get('enabled', True)}

    # ── 3. Token ──
    token = cfg['token'] or FINMIND_TOKEN
    if not token:
        raise ValueError('FINMIND_TOKEN 未設定')

    # ── 4. 抓資料 ──
    df_price, df_per, df_fin, df_div = fetch_data(
        token=token,
        stock_list=pool,
        start=cfg['start'],
        end=cfg['end'],
        use_cache=cfg['use_cache'],
        include_dividends=cfg.get('include_dividends', False),
    )

    # ── 5. 建寬表 + 過濾只有價量的股票（ETF 沒 PE/ROE） ──
    close, volume, pe, roe = build_wide_tables(
        df_price, df_per, df_fin,
        df_div=df_div,
        adjust_method=cfg.get('adjust_method', 'backward'),
    )
    valid_stocks = (
        close.columns[close.notna().any()]
        .intersection(pe.columns)
        .intersection(roe.columns)
    )
    if len(valid_stocks) < len(close.columns):
        dropped = set(close.columns) - set(valid_stocks)
        log.info(f'过滤 {len(dropped)} 檔無 PE/ROE 股票: {sorted(dropped)}')
        close = close[valid_stocks]
        volume = volume[valid_stocks]
        pe = pe[valid_stocks]
        roe = roe[valid_stocks]

    # ── 6. 各 strategy 計算分數 ──
    log.info('計算各 strategy 分數...')
    strategy_results = []
    for inst in instances:
        result = inst.compute(close=close, per=pe, fin=df_fin, volume=volume)
        strategy_results.append(result)

    # ── 7. 加權組合 ──
    total_score = combine_scores(
        strategy_results,
        weights,
        standardize=cfg.get('standardize', 'rank'),
    )

    # ── 8. 建持倉 + 抓 0050 ──
    walk_forward = cfg.get('walk_forward', False)
    train_pct = cfg.get('train_pct', 0.7)
    split_date = None
    rebalance_until = None
    top_n = cfg.get('top_n', 5)

    if walk_forward:
        start_ts = pd.Timestamp(cfg['start'])
        end_ts = pd.Timestamp(cfg['end'])
        split_ts = start_ts + (end_ts - start_ts) * train_pct
        split_date = split_ts.strftime('%Y-%m-%d')
        rebalance_until = split_date
        log.info(f'🔬 Walk-forward 啟用：訓練期 {cfg["start"]} ~ {split_date}（{train_pct:.0%}），'
                 f'驗證期 {split_date} ~ {cfg["end"]}（驗證期鎖倉不換倉）')

    position, selected = build_position(
        close=close,
        total_score=total_score,
        volume=volume,
        rebalance_freq=cfg.get('rebalance_freq', 'monthly'),
        min_liquidity_shares=cfg.get('min_liquidity_shares', 0),
        top_n=top_n,
        equal_weight=1.0 / top_n,
        rebalance_until=rebalance_until,
    )
    market_close = fetch_0050_data(token=token, start=cfg['start'], end=cfg['end']) if cfg.get('use_0050_benchmark', True) else None

    # ── 9. 跑回測算 KPI ──
    bt = run_backtest(
        close=close,
        position=position,
        total_score=total_score,
        market_close=market_close,
    )
    # v1.4：標註除權息調整設定（供 report.py 顯示）
    bt.include_dividends = cfg.get('include_dividends', False)
    bt.adjust_method = cfg.get('adjust_method', 'none') if cfg.get('include_dividends', False) else 'none'
    bt.walk_forward_split_date = split_date

    # v1.4：Walk-forward KPI（若啟用）
    if walk_forward and split_date is not None:
        _inject_walk_forward_kpis(bt, split_date, train_pct)

    return bt


def _inject_walk_forward_kpis(bt, split_date: str, train_pct: float):
    """計算 walk-forward 訓練期 / 驗證期 / 衰退 KPI 並寫入 bt.kpis。

    設計：
      - training_return：split_date（含）之前的累積報酬（cum_strategy.loc[split] - 1）
      - validation_return：split_date 之後的報酬（cum_strategy.iloc[-1] / cum_strategy.loc[split] - 1）
      - combined_return：等同 total_return（整段 cum_strategy.iloc[-1] - 1）
      - walk_forward_decay：validation_return - training_return（負值 = 過擬合）
    """
    cum = bt.cum_strategy
    if split_date not in cum.index:
        # split_date 當天沒交易，向前找最近的交易日
        split_ts = pd.Timestamp(split_date)
        valid = cum.index[cum.index <= split_ts]
        if len(valid) == 0:
            log.warning(f'walk-forward：找不到 split_date {split_date} 之前的交易日')
            return
        split_actual = valid[-1]
        log.info(f'walk-forward：split_date {split_date} 非交易日，'
                 f'改用最近的交易日 {split_actual.strftime("%Y-%m-%d")}')
    else:
        split_actual = pd.Timestamp(split_date)

    train_nav = float(cum.loc[split_actual])
    full_nav = float(cum.iloc[-1])

    training_return = train_nav - 1.0
    if train_nav > 0:
        validation_return = (full_nav / train_nav) - 1.0
    else:
        validation_return = 0.0
    combined_return = full_nav - 1.0
    walk_forward_decay = validation_return - training_return

    walk_forward_kpis = {
        'walk_forward_enabled': True,
        'walk_forward_split_date': split_actual.strftime('%Y-%m-%d'),
        'train_pct': train_pct,
        'training_return': training_return,
        'validation_return': validation_return,
        'combined_return': combined_return,
        'walk_forward_decay': walk_forward_decay,
    }
    bt.kpis.update(walk_forward_kpis)

    log.info('─' * 56)
    log.info('🔬 Walk-forward 結果：')
    log.info(f'   訓練期報酬: {training_return:+.2%}')
    log.info(f'   驗證期報酬: {validation_return:+.2%}')
    log.info(f'   衰退 (val - train): {walk_forward_decay:+.2%}（負值 = 過擬合）')
    log.info('─' * 56)


if __name__ == '__main__':
    # 直接跑：python -m quant.runner
    result = run()
    print('\n=== KPI ===')
    for k, v in result.kpis.items():
        if isinstance(v, float):
            print(f'  {k}: {v:.4f}')
        else:
            print(f'  {k}: {v}')