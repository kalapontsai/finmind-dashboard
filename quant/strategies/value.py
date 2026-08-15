"""
Value 策略：本益比（PER）越低越好
- PER 反映股價相對於獲利的便宜程度
- 回看 N 天內最便宜的 N 檔應該超額報酬
"""
from __future__ import annotations

import pandas as pd

from .base import BaseStrategy, StrategyResult


class ValueStrategy(BaseStrategy):
    type_name = 'value'
    required_inputs = ('per',)
    ascending = False  # 排名輸出：值越低 → pct 越高（pandas ascending=False：小值拿高 pct）

    @property
    def default_params(self) -> dict:
        return {
            'lookback_days': 60,   # 回看天數（用來 ffill 缺值）
            'weight': 0.40,
        }

    def compute(
        self,
        close: pd.DataFrame,
        per: pd.DataFrame | None = None,
        fin: pd.DataFrame | None = None,
        volume: pd.DataFrame | None = None,
    ) -> StrategyResult:
        if per is None:
            raise ValueError('ValueStrategy 需要 per 輸入')

        lookback = max(int(self.params.get('lookback_days', 60)), 1)

        # PER 寬表：build_wide_tables 已 ffill 過；直接 reindex 對齊交易日曆
        # ascending=False → pandas 把「值最小」排到最高 pct，正好符合「低 PE = 高分」
        raw = per.reindex(close.index).ffill()

        score = self.rank_pct(raw, ascending=self.ascending)
        return StrategyResult(
            score=score,
            raw=raw,
            type=self.type_name,
            params=dict(self.params),
        )

    def __init__(self, params: dict | None = None):
        self.params = {**self.default_params, **(params or {})}