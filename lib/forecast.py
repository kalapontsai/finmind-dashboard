"""
Historical N-Year Rolling Outcome Forecast
- 從 Portfolio NAV 建立所有 N-Year rolling periods
- 計算每段 CAGR → 取 P10/P25/P50/P75/P90
- 對應 Bear / Conservative / Base / Optimistic / Bull
- 計算 N 年後終值 FV = PV * (1 + r)^N
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# 終值情境名稱（與 SKILL.md 對應）
SCENARIOS = [
    ('Bear',         0.10, 'Bear (P10)'),
    ('Conservative', 0.25, 'Conservative (P25)'),
    ('Base',         0.50, 'Base (P50)'),
    ('Optimistic',   0.75, 'Optimistic (P75)'),
    ('Bull',         0.90, 'Bull (P90)'),
]


class ForecastError(ValueError):
    pass


def rolling_n_year_cagr(
    nav: pd.Series,
    n: int,
    min_year_coverage: float = 0.95,
) -> pd.DataFrame:
    """
    從 NAV 建立所有 N-Year rolling periods。
    Returns DataFrame: [start, end, years, cagr]
    """
    if not isinstance(nav, pd.Series) or nav.empty:
        raise ForecastError('NAV 為空')
    if n < 1:
        raise ForecastError('N 必須 >= 1')
    if len(nav) < 2:
        raise ForecastError('NAV 至少需 2 個資料點')

    idx = nav.index
    out = []
    for i, d in enumerate(idx):
        target = d + pd.DateOffset(years=n)
        # 找第一個 >= target 的位置
        j = idx.searchsorted(target, side='left')
        if j >= len(idx):
            break
        end = idx[j]
        years = (end - d).days / 365.25
        if years < n * min_year_coverage:
            continue
        v0 = nav.iloc[i]
        v1 = nav.iloc[j]
        if v0 <= 0:
            continue
        cagr = (v1 / v0) ** (1 / years) - 1
        out.append((d, end, years, cagr))
    if not out:
        raise ForecastError(f'歷史資料不足以建立 N={n} 年 rolling outcome（最少 {min_year_coverage*100:.0f}% 覆蓋）')
    return pd.DataFrame(out, columns=['start', 'end', 'years', 'cagr'])


def scenario_percentiles(rolling: pd.DataFrame) -> dict[str, float]:
    """給定 [cagr] 的 rolling df，回傳 {情境: cagr}"""
    out = {}
    for name, q, _full in SCENARIOS:
        out[name] = float(rolling['cagr'].quantile(q))
    return out


def future_value(pv: float, r: float, n: int) -> float:
    """FV = PV * (1+r)^N"""
    if pv < 0:
        raise ForecastError('目前資產不得為負')
    return pv * (1 + r) ** n


def build_forecast(nav: pd.Series, n: int, pv: float) -> dict:
    """
    完整 N-Year forecast 結果：
    {
      'n': int,
      'pv': float,
      'rolling_count': int,
      'rolling': [{start, end, years, cagr}] (給前端畫圖，全部)
      'percentiles': {Bear: ..., P10: ..., ...},
      'scenarios': [{scenario, percentile, cagr, future_value, multiple}]
    }
    """
    rolling = rolling_n_year_cagr(nav, n)
    pct = scenario_percentiles(rolling)
    scenarios = []
    for name, q, _full_name in SCENARIOS:
        r = pct[name]
        fv = future_value(pv, r, n)
        scenarios.append({
            # 'scenario' 保留作 compatibility，但主名稱以 'label' 為準
            'scenario': f'{name} (P{int(q*100)})',
            'label': name,
            'quantile': q,
            'cagr': r,
            'fv': fv,
            'multiplier': fv / pv if pv > 0 else float('nan'),
        })
    rolling_list = [
        {
            'start': str(r.start.date()),
            'end': str(r.end.date()),
            'years': round(float(r.years), 2),
            'cagr': float(r.cagr),
        }
        for r in rolling.itertuples(index=False)
    ]
    return {
        'n': n,
        'pv': pv,
        'rolling_count': len(rolling),  # 保留舊名作 compatibility
        'r_count': len(rolling),         # 主名稱（驗收標準 #5）
        'percentiles': pct,
        'scenarios': scenarios,
        'rolling': rolling_list,
    }
