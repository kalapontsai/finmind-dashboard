"""
Strategy 參數 schema 版本控管
- 所有策略 JSON 格式：{ schema_version, type, params }
- migrate() 自動將舊版資料升級到最新 schema
- validate() 確保載入的資料結構正確，缺欄位自動補預設值
"""
from __future__ import annotations

from typing import Any


# ─── 目前 schema 版本 ───
CURRENT_SCHEMA_VERSION = 1


# ─── 各策略預設參數 ───
DEFAULT_PARAMS = {
    'value': {
        'lookback_days': 60,        # PER 回看天數（天）
        'weight': 0.40,             # 預設權重
    },
    'momentum': {
        'lookback_days': 120,       # 動能回看天數
        'weight': 0.30,
    },
    'quality': {
        'lookback_days': 90,        # ROE 回看天數
        'weight': 0.30,
    },
}


# ─── Schema 遷移腳本（版本 → 下一版本要做什麼） ───
_MIGRATIONS: dict[int, callable[[dict], dict]] = {
    # v0 → v1：首次建立 schema，新增 schema_version / type / params
    0: lambda data: {
        'schema_version': 1,
        'type': data.get('type', 'value'),
        'params': _migrate_v0_params(data),
    },
}


def _migrate_v0_params(data: dict) -> dict:
    """
    v0 params：拿最上層非 meta 的 keys 作為 params。
    若已有 params 節點，取其值（避免被 validate._fill_defaults 覆蓋）。
    """
    # 過濾掉 meta 欄位
    meta = {'type', 'schema_version', 'version', 'updated_at', 'created_at', 'name', 'params'}
    params = {k: v for k, v in data.items() if k not in meta}
    # 若本來就有 params 節點（巢狀殘留），保留其內容
    if 'params' in data and isinstance(data['params'], dict):
        params = dict(data['params'])
    return params


# ─── 公開 API ───

def current_schema(type: str = 'value') -> dict:
    """回傳目前 schema 版本 + 該 type 的預設參數（不含 runtime 欄位）。"""
    return {
        'schema_version': CURRENT_SCHEMA_VERSION,
        'type': type,
        'params': DEFAULT_PARAMS.get(type, {}).copy(),
    }


def migrate(data: dict) -> dict:
    """
    將任意版本的 strategy JSON 遷移到目前版本。
    - 已是最新的 schema_version → 直接補預設值後回傳
    - 低於目前版本 → 依序套用每個版本的 migration
    """
    if not isinstance(data, dict):
        raise ValueError('strategy data 必須是 dict')

    # 沒有 schema_version → 視為 v0
    schema_version: int = int(data.get('schema_version', 0))

    result = dict(data)

    # 依序套用 migration 直到抵達目標版本
    while schema_version < CURRENT_SCHEMA_VERSION:
        migrator = _MIGRATIONS.get(schema_version)
        if migrator is None:
            raise ValueError(f'找不到 schema v{schema_version} 的 migrator')
        result = migrator(result)
        schema_version = result['schema_version']

    # 確保所有 params 欄位都有預設值（migrate 完的最後一道防線）
    result = _fill_defaults(result)

    return result


def _fill_defaults(data: dict) -> dict:
    """確保 params 不缺欄位，缺了就補預設值。"""
    strategy_type = data.get('type', 'value')
    default_params = DEFAULT_PARAMS.get(strategy_type, {})

    params = data.get('params', {})
    if not isinstance(params, dict):
        params = {}

    filled_params = dict(default_params)
    filled_params.update(params)  # 使用者提供的值優先

    data = dict(data)
    data['params'] = filled_params
    data['schema_version'] = CURRENT_SCHEMA_VERSION
    return data


def validate(data: dict) -> dict:
    """
    驗證 strategy JSON 結構。
    - 缺 schema_version / type → 自動 migrate
    - type 不在允許清單 → 拋例外
    - params 缺欄位 → 自動補預設值
    Returns the validated (and possibly migrated) data.
    Raises ValueError on unrecoverable errors.
    """
    allowed_types = set(DEFAULT_PARAMS.keys())
    raw_type = data.get('type', '')

    # type 無效 → 不可 migrate，直接失敗
    if raw_type and raw_type not in allowed_types:
        raise ValueError(f'unknown strategy type: {raw_type!r}')

    migrated = migrate(data)

    # 最終欄位檢查
    if migrated['schema_version'] != CURRENT_SCHEMA_VERSION:
        raise ValueError(
            f'schema_version 仍不符合預期：got {migrated["schema_version"]}, '
            f'expected {CURRENT_SCHEMA_VERSION}'
        )
    if migrated['type'] not in allowed_types:
        raise ValueError(f'invalid type after migrate: {migrated["type"]!r}')

    return migrated
