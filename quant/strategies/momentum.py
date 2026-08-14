"""
Momentum 策略：N 日動能（漲幅）越高越好
- 過去 N 日漲幅高的股票傾向繼續上漲
"""
from __future__ import annotations

import pandas as pd

from .base import BaseStrategy, StrategyResult


class MomentumStrategy(BaseStrategy):
    type_name = 'momentum'
    required_inputs = ('close',)
    ascending = False  # 漲幅越高越好

    @property
    def default_params(self) -> dict:
        return {
            'lookback_days': 120,  # 動能回看天數
            'weight': 0.30,
        }

    def compute(
        self,
        close: pd.DataFrame,
        per: pd.DataFrame | None = None,
        fin: pd.DataFrame | None = None,
        volume: pd.DataFrame | None = None,
    ) -> StrategyResult:
        lookback = max(int(self.params.get('lookback_days', 120)), 5)

        # N 日漲幅
        raw = close.pct_change(periods=lookback, fill_method=None)

        score = self.rank_pct(raw, ascending=self.ascending)
        return StrategyResult(
            score=score,
            raw=raw,
            type=self.type_name,
            params=dict(self.params),
        )

    def __init__(self, params: dict | None = None):
        self.params = {**self.default_params, **(params or {})}