"""
股票池載入器
- 從 `pool.txt` 讀取 comma-separated 股票代碼
- 去重、驗證格式（純 4 位數字）
- 找不到檔案 → 拋 FileNotFoundError
"""
from __future__ import annotations

from pathlib import Path

from app_config import QUANT_DIR


POOL_FILE: Path = QUANT_DIR / 'pool.txt'
VALID_STOCK_PATTERN = __import__('re').compile(r'^\d{4,6}[A-Za-z]?$')


def load_pool(path: Path | str | None = None) -> list[str]:
    """
    載入股票池。

    Args:
        path: 自訂池檔路徑（None = 用預設 pool.txt）

    Returns:
        去重 + 驗證後的股票代碼 list

    Raises:
        FileNotFoundError: 找不到檔案
        ValueError: 行內有空字串或無效格式
    """
    p = Path(path) if path else POOL_FILE
    if not p.is_file():
        raise FileNotFoundError(f'股票池檔不存在: {p}')

    raw = p.read_text(encoding='utf-8')
    out: list[str] = []
    seen: set[str] = set()

    for lineno, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # 支援 comma / whitespace / 換行分隔
        tokens = [t.strip() for t in line.replace(',', ' ').split() if t.strip()]
        for tok in tokens:
            if not VALID_STOCK_PATTERN.match(tok):
                raise ValueError(f'pool.txt 第 {lineno} 行有非法股票代碼: {tok!r}')
            if tok not in seen:
                seen.add(tok)
                out.append(tok)

    if not out:
        raise ValueError(f'pool.txt 沒有有效股票代碼: {p}')

    return out


def pool_size(path: Path | str | None = None) -> int:
    """回傳池大小（不拋例外；找不到檔案返回 0）。"""
    try:
        return len(load_pool(path))
    except Exception:
        return 0