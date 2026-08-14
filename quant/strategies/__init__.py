"""
Quant strategies 套件
- 每個 strategy 是獨立 class，介面：
    compute_score(close, per, fin, ...) -> pd.DataFrame
    回傳排名矩陣（Index=date, Columns=stock_id, Values=0–1）
- 透過 STRATEGY_REGISTRY 註冊與查詢
"""
from .base import BaseStrategy, StrategyResult
from .value import ValueStrategy
from .momentum import MomentumStrategy
from .quality import QualityStrategy

# 註冊表（type 字串 → class）
STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    'value': ValueStrategy,
    'momentum': MomentumStrategy,
    'quality': QualityStrategy,
}

__all__ = [
    'BaseStrategy', 'StrategyResult',
    'ValueStrategy', 'MomentumStrategy', 'QualityStrategy',
    'STRATEGY_REGISTRY',
]


def get_strategy_class(type_name: str) -> type[BaseStrategy]:
    """從 type 名稱取得 strategy class，找不到拋 ValueError。"""
    cls = STRATEGY_REGISTRY.get(type_name)
    if cls is None:
        raise ValueError(
            f'unknown strategy type: {type_name!r}; '
            f'available: {sorted(STRATEGY_REGISTRY.keys())}'
        )
    return cls