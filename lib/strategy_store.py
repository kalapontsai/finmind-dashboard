"""
Strategy 參數儲存與載入
- 讀寫 `quant/strategies/params/<name>.json`
- 每次寫入自動帶 schema_version / type / updated_at
- 每次讀取自動執行 migrate（舊 JSON 自動升級）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app_config import QUANT_DIR

from .strategy_schema import current_schema, migrate, validate


STRATEGIES_DIR: Path = QUANT_DIR / 'strategies' / 'params'


def _ensure_dir():
    STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)


def _file_path(name: str) -> Path:
    """sanitize name，避免路徑 traversal。"""
    safe = ''.join(c for c in name if c.isalnum() or c in ('_', '-'))
    if not safe:
        raise ValueError(f'invalid strategy name: {name!r}')
    return STRATEGIES_DIR / f'{safe}.json'


def load(name: str) -> dict:
    """
    載入策略 JSON，自動 migrate 到最新 schema。
    Returns: { schema_version, type, params, updated_at }
    Raises FileNotFoundError if not found.
    Raises ValueError if data is corrupt/unrecoverable.
    """
    path = _file_path(name)
    if not path.is_file():
        raise FileNotFoundError(f'strategy not found: {name}')

    raw = json.loads(path.read_text(encoding='utf-8'))
    validated = validate(raw)
    return validated


def save(name: str, data: dict) -> dict:
    """
    寫入策略 JSON（含 schema_version / updated_at）。
    data 只需要包含 type + params（不含 schema_version，會自動補）。
    Returns the written record.
    """
    _ensure_dir()

    # 確保 type
    strategy_type = data.get('type')
    if not strategy_type:
        raise ValueError('data must contain type')

    # 合併進 current_schema → 確保所有欄位正確
    record = current_schema(strategy_type)
    incoming_params = data.get('params', {})
    record['params'] = {**record['params'], **incoming_params}
    record['updated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')

    path = _file_path(name)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def list_strategies() -> list[dict]:
    """
    回傳所有已儲存的策略摘要（不含 params，只含 meta）。
    Returns list of { name, type, schema_version, updated_at }
    """
    _ensure_dir()
    results = []
    for path in sorted(STRATEGIES_DIR.glob('*.json')):
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
            results.append({
                'name': path.stem,
                'type': raw.get('type', 'unknown'),
                'schema_version': raw.get('schema_version', 0),
                'updated_at': raw.get('updated_at'),
            })
        except Exception:
            # skip corrupt files
            continue
    return results


def delete(name: str) -> bool:
    """刪除策略檔。成功返回 True，找不到返回 False。"""
    path = _file_path(name)
    if not path.is_file():
        return False
    path.unlink()
    return True
