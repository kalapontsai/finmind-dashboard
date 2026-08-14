"""
Strategy 抽象基類
- 純設定：每個 strategy 自己描述需要的輸入與計算方式
- 不實際跑回測 → 回測由 quant/runner.py 統一負責
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class StrategyResult:
    """Strategy 計算結果"""
    score: pd.DataFrame           # 排名矩陣（0–1，1=最佳）
    raw: pd.DataFrame             # 原始因子值（未排名）
    type: str                     # 'value' / 'momentum' / 'quality'
    params: dict                  # 當次跑用的參數


class BaseStrategy(ABC):
    """
    量化策略抽象基類

    每個 strategy 必須實作：
    - type_name: 策略識別（'value' / 'momentum' / 'quality'）
    - required_inputs: 列出需要的輸入（'close' / 'per' / 'fin' / 'volume'）
    - default_params: 預設參數
    - compute(close, per, fin, ...) -> StrategyResult

    排名方式：
    - ascending=True → 原始值越低分數越高（value / PER）
    - ascending=False → 原始值越高分數越高（momentum / quality）
    """
    type_name: str = ''
    required_inputs: tuple[str, ...] = ()
    ascending: bool = False  # 大多數策略都是值越高越好

    @property
    @abstractmethod
    def default_params(self) -> dict:
        """預設參數 dict（含 lookback_days / weight 等）"""
        ...

    @abstractmethod
    def compute(
        self,
        close: pd.DataFrame,
        per: pd.DataFrame | None = None,
        fin: pd.DataFrame | None = None,
        volume: pd.DataFrame | None = None,
    ) -> StrategyResult:
        """
        計算排名矩陣。
        必須回傳 StrategyResult，其中 score 為 0–1 排名。
        缺資料的股票在該日為 NaN（不參與排名）。
        """
        ...

    # ─── 共用工具 ───

    @staticmethod
    def rank_pct(values: pd.DataFrame, ascending: bool) -> pd.DataFrame:
        """
        橫斷面百分比排名（0~1，1=最佳）。
        NaN 不參與排名，保持 NaN。
        """
        return values.rank(axis=1, pct=True, ascending=ascending)