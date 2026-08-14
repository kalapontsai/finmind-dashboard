"""
Quality 策略：ROE（股東權益報酬率）越高越好
- ROE = 淨利 / 歸屬母公司權益
- ROE 高的公司通常基本面較強
"""
from __future__ import annotations

import pandas as pd

from .base import BaseStrategy, StrategyResult


class QualityStrategy(BaseStrategy):
    type_name = 'quality'
    required_inputs = ('roe',)  # 預處理過的 ROE 寬表
    ascending = False  # ROE 越高越好

    @property
    def default_params(self) -> dict:
        return {
            'lookback_days': 90,   # ROE ffill 天數（季報發布間隔）
            'weight': 0.30,
        }

    def compute(
        self,
        close: pd.DataFrame,
        per: pd.DataFrame | None = None,
        fin: pd.DataFrame | None = None,
        volume: pd.DataFrame | None = None,
    ) -> StrategyResult:
        # ROE 直接由 build_wide_tables 回傳（已是寬表）
        # 但這裡介面簽名只接 fin（長表），為保持一致性，從 fin 自己算
        if fin is None:
            raise ValueError('QualityStrategy 需要 fin 輸入（三大財報長表）')

        # 計算 ROE
        fin_wide = fin.pivot_table(
            index=['date', 'stock_id'], columns='type', values='value',
        ).reset_index()
        fin_wide['ROE'] = (
            fin_wide['IncomeAfterTaxes'] / fin_wide['EquityAttributableToOwnersOfParent']
        )
        fin_wide['date'] = pd.to_datetime(fin_wide['date']).dt.strftime('%Y-%m-%d')
        roe = fin_wide.pivot(index='date', columns='stock_id', values='ROE').astype(float)

        # 對齊 + ffill（與 quant.py build_wide_tables 一致：無 limit）
        raw = roe.reindex(close.index).ffill()

        score = self.rank_pct(raw, ascending=self.ascending)
        return StrategyResult(
            score=score,
            raw=raw,
            type=self.type_name,
            params=dict(self.params),
        )

    def __init__(self, params: dict | None = None):
        self.params = {**self.default_params, **(params or {})}