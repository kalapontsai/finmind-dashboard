"""
股票池載入器
- 從 `pool.txt` 讀取 comma-separated 股票代碼
- 去重、驗證格式（純 4 位數字）
- 找不到檔案 → 拋 FileNotFoundError
- `save_pool()`：把 pool 同步寫成 `pool.json`（給前端 fetch 用）
"""
from __future__ import annotations

import json
from pathlib import Path

from app_config import QUANT_DIR


POOL_FILE: Path = QUANT_DIR / 'pool.txt'
POOL_JSON: Path = QUANT_DIR / 'pool.json'  # 前端 /api/quant_pool 讀這個
VALID_STOCK_PATTERN = __import__('re').compile(r'^\d{4,6}[A-Za-z]?$')


def load_pool(path: Path | str | None = None) -> list[str]:
    """
    載入股票池。

    Args:
        path: 自訂池檔路徑（None = 自動選 pool.json / pool.txt）

    讀取順序（v1.4 P3-5）：
    1. 若 `path` 指定 → 直接讀該檔
    2. 否則：
       a. 若 `pool.json` 存在 且 比 `pool.txt` 新（或 pool.txt 不存在）→ 讀 pool.json
       b. 否則讀 `pool.txt` 並順手 regenerate `pool.json`（保證 sync）
    3. 兩者都不存在 → 拋 FileNotFoundError

    Returns:
        去重 + 驗證後的股票代碼 list

    Raises:
        FileNotFoundError: 找不到檔案
        ValueError: 行內有空字串或無效格式
    """
    if path:
        return _load_from_text_file(Path(path))

    # 自動挑檔：pool.json 優先（v1.4 P3-5）
    if POOL_JSON.is_file() and _pool_json_is_fresh():
        try:
            data = json.loads(POOL_JSON.read_text(encoding='utf-8'))
            if isinstance(data, list) and data:
                # 簡單驗證（不打破現有 contract）
                return [str(s).strip() for s in data if VALID_STOCK_PATTERN.match(str(s).strip())]
        except (ValueError, OSError):
            pass  # 壞 JSON → fallback pool.txt

    # 讀 pool.txt（單一真相），順手 sync 回 pool.json
    result = _load_from_text_file(POOL_FILE)
    try:
        save_pool(result)
    except OSError:
        pass  # 寫 cache 失敗不阻塞讀取
    return result


def _load_from_text_file(p: Path) -> list[str]:
    """讀取 pool.txt（comma-separated / 每行 10 個）格式。"""
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
                raise ValueError(f'{p.name} 第 {lineno} 行有非法股票代碼: {tok!r}')
            if tok not in seen:
                seen.add(tok)
                out.append(tok)

    if not out:
        raise ValueError(f'{p.name} 沒有有效股票代碼: {p}')

    return out


def _pool_json_is_fresh() -> bool:
    """
    pool.json 是否比 pool.txt 新（且 pool.txt 不存在 → 視為新）。
    - 兩者皆不存在 → False（呼叫端會 fallback）
    """
    if not POOL_JSON.is_file():
        return False
    if not POOL_FILE.is_file():
        return True
    return POOL_JSON.stat().st_mtime >= POOL_FILE.stat().st_mtime


def pool_size(path: Path | str | None = None) -> int:
    """回傳池大小（不拋例外；找不到檔案返回 0）。"""
    try:
        return len(load_pool(path))
    except Exception:
        return 0


def save_pool(stocks: list[str] | None = None,
              pool_file: Path | str | None = None,
              json_file: Path | str | None = None) -> Path:
    """
    把股票池同步寫成 `pool.json`（方便前端 / API 直接讀）。
    - 若 `stocks` 為 None → 從 pool.txt 載入後寫入
    - 若 `pool_file` / `json_file` 為 None → 用預設 pool.txt / pool.json
    - 去重 + 排序後寫入（indented JSON，UTF-8）
    - 回寫寫入的 json 路徑
    """
    src = Path(pool_file) if pool_file else POOL_FILE
    dst = Path(json_file) if json_file else POOL_JSON

    if stocks is None:
        stocks = load_pool(src)

    # 去重 + 排序（保留原順序也合理，這裡採排序方便比對）
    dedup_sorted = sorted({str(s).strip() for s in stocks if str(s).strip()})

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(
        json.dumps(dedup_sorted, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return dst


def sync_pool_json() -> Path:
    """
    一鍵 sync：讀 pool.txt → 寫 pool.json。
    - 找不到 pool.txt → 拋 FileNotFoundError
    - 若 pool.json 已存在 → 仍覆寫（pool.txt 是 single source of truth）
    - 回寫寫入的 json 路徑
    """
    return save_pool()