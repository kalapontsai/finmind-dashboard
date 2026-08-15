"""
P3-3: routes/api.py 中寬 try/except 縮到具體例外範圍

策略：
- 找出所有 bare `except Exception:` 或 `except:` 行
- 自動替換為 `except (FinMindError, KeyError, ValueError, TypeError, json.JSONDecodeError):`
  （常見的「這層該處理的」例外）
- 保留原有的 except 區塊結構

驗收：
- grep "except Exception" routes/api.py 數量下降或維持 0
- py_compile 通過
"""
from __future__ import annotations

import re
from pathlib import Path

API_PY = Path(__file__).resolve().parents[2] / "routes" / "api.py"


# 常見的「這層該接的」例外，依 FinMind / Flask 慣例
TARGET_EXCEPTIONS = (
    "FinMindError",
    "KeyError",
    "ValueError",
    "TypeError",
    "json.JSONDecodeError",
)


def main() -> None:
    if not API_PY.is_file():
        raise SystemExit(f"找不到 {API_PY}")

    src = API_PY.read_text(encoding="utf-8")
    original = src

    # 確保 json 已 import
    if "import json" not in src:
        src = "import json\n" + src
        print("P3-3: 補上 import json")

    # 確保 FinMindError 已 import
    if "from lib.finmind" in src and "FinMindError" not in src:
        src = src.replace(
            "from lib.finmind import FinMindClient",
            "from lib.finmind import FinMindClient, FinMindError",
            1,
        )
        print("P3-3: 補上 FinMindError import")

    # 替換 bare except / except Exception
    new_src = re.sub(
        r"except\s+Exception\s*:",
        f"except ({', '.join(TARGET_EXCEPTIONS)}):",
        src,
    )
    new_src = re.sub(
        r"(?m)^(\s*)except\s*:\s*$",
        f"\\1except ({', '.join(TARGET_EXCEPTIONS)}):",
        new_src,
    )

    if new_src == src:
        print(f"P3-3: {API_PY.name} 沒有寬 except 需替換")
        return

    # py_compile 確認語法 OK
    import py_compile
    try:
        py_compile.compile(str(API_PY), doraise=True)
    except py_compile.PyCompileError as e:
        raise SystemExit(f"原本檔案就有語法錯誤：{e}")

    API_PY.write_text(new_src, encoding="utf-8")
    diff_count = sum(1 for a, b in zip(original.splitlines(), new_src.splitlines()) if a != b)
    print(f"P3-3: {API_PY.name} 已收緊 except（{diff_count} 處變更）")


if __name__ == "__main__":
    main()
