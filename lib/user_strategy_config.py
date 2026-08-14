"""
使用者策略啟用/權重設定
- 獨立於 params/<name>.json（純因子參數）
- 儲存「啟用與否」與「組合權重」（前端 UI 來回編輯）
- 寫入 quant/user_strategies.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app_config import QUANT_DIR


CONFIG_FILE: Path = QUANT_DIR / 'user_strategies.json'


# 預設：3 個策略全開，權重 0.4 / 0.3 / 0.3
DEFAULT_CONFIG: dict = {
    'strategies': [
        {'name': 'value',    'enabled': True, 'weight': 0.40},
        {'name': 'momentum', 'enabled': True, 'weight': 0.30},
        {'name': 'quality',  'enabled': True, 'weight': 0.30},
    ],
    'updated_at': None,
}


def load() -> dict:
    """載入使用者策略設定；檔案不存在時回預設值。"""
    if not CONFIG_FILE.is_file():
        return json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy

    try:
        data = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    except Exception:
        return json.loads(json.dumps(DEFAULT_CONFIG))

    strategies = data.get('strategies')
    if not isinstance(strategies, list):
        return json.loads(json.dumps(DEFAULT_CONFIG))

    # 確保三個 strategy 都存在（缺項補預設）
    by_name = {s.get('name'): s for s in strategies if isinstance(s, dict) and s.get('name')}
    merged = []
    for default in DEFAULT_CONFIG['strategies']:
        existing = by_name.get(default['name'])
        if existing:
            merged.append({
                'name': default['name'],
                'enabled': bool(existing.get('enabled', default['enabled'])),
                'weight': float(existing.get('weight', default['weight'])),
            })
        else:
            merged.append(dict(default))

    return {
        'strategies': merged,
        'updated_at': data.get('updated_at'),
    }


def save(strategies: list[dict]) -> dict:
    """
    儲存使用者策略設定。
    strategies: list of { name, enabled, weight }
    只接受已知的 3 個名稱，其他忽略。
    """
    allowed = {'value', 'momentum', 'quality'}
    cleaned = []
    for s in strategies or []:
        if not isinstance(s, dict):
            continue
        name = s.get('name')
        if name not in allowed:
            continue
        cleaned.append({
            'name': name,
            'enabled': bool(s.get('enabled', False)),
            'weight': max(0.0, min(1.0, float(s.get('weight', 0)))),
        })

    # 確保三個都存在
    by_name = {s['name']: s for s in cleaned}
    merged = []
    for default in DEFAULT_CONFIG['strategies']:
        merged.append(by_name.get(default['name'], dict(default)))

    payload = {
        'strategies': merged,
        'updated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return payload
