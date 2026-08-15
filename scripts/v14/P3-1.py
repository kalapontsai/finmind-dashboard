"""
P3-1: 把 quant/quant.py 中硬編碼的快取路徑改成讀 app_config.QUANT_CACHE_DIR

驗收：
- grep "QUANT_CACHE_DIR" quant/quant.py 至少出現 1 次（import 或參考）
- py_compile 通過
"""
from __future__ import annotations

import re
from pathlib import Path

QUANT_PY = Path(__file__).resolve().parents[2] / "quant" / "quant.py"
APP_CONFIG_PY = Path(__file__).resolve().parents[2] / "app_config.py"


def main() -> None:
    if not QUANT_PY.is_file():
        raise SystemExit(f"找不到 {QUANT_PY}")

    src = QUANT_PY.read_text(encoding="utf-8")

    # 已經 import 了 → 跳過
    if "QUANT_CACHE_DIR" in src and "from app_config" in src:
        print(f"P3-1: {QUANT_PY.name} 已用 app_config.QUANT_CACHE_DIR，跳過")
        return

    # 找 import 區塊：在第一個 def / class 前插入
    insert_marker = re.search(r"^(def |class )", src, re.MULTILINE)
    if not insert_marker:
        raise SystemExit("找不到 def/class marker，無法安全插入 import")

    insert_pos = insert_marker.start()
    new_import = "from app_config import QUANT_CACHE_DIR\n"
    src_new = src[:insert_pos] + new_import + src[insert_pos:]

    # 找硬編碼的 'quant/cache' 路徑 → 改用 QUANT_CACHE_DIR
    src_new = re.sub(
        r"['\"]quant/cache['\"]",
        "str(QUANT_CACHE_DIR)",
        src_new,
    )
    src_new = re.sub(
        r"cache_dir\s*=\s*['\"][^'\"]*cache['\"]",
        "cache_dir = str(QUANT_CACHE_DIR)",
        src_new,
    )

    QUANT_PY.write_text(src_new, encoding="utf-8")
    print(f"P3-1: 已更新 {QUANT_PY.name} → 從 app_config 讀 QUANT_CACHE_DIR")


if __name__ == "__main__":
    main()
