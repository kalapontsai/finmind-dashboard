"""
P3-4: static/js/quant.js — input debounce

策略：
- 在每個 `addEventListener('input', ...)` 或 `addEventListener('change', ...)`
  換成 debounce wrapper（200ms）
- 提供 `debounce(fn, ms)` 工具函式（如果還沒有）

驗收：
- quant.js 開頭（或 module 內）有 `function debounce(`
- 至少 1 個 listener 被 debounce 包起來
"""
from __future__ import annotations

import re
from pathlib import Path

QUANT_JS = Path(__file__).resolve().parents[2] / "static" / "js" / "quant.js"


DEBOUNCE_FN = """
// ===== debounce（v1.4 P3-4） =====
function debounce(fn, ms) {
  let t;
  return function (...args) {
    clearTimeout(t);
    t = setTimeout(() => fn.apply(this, args), ms);
  };
}
"""


def main() -> None:
    if not QUANT_JS.is_file():
        raise SystemExit(f"找不到 {QUANT_JS}")

    src = QUANT_JS.read_text(encoding="utf-8")

    if "function debounce(" in src:
        print(f"P3-4: {QUANT_JS.name} 已有 debounce 工具函式，跳過工具新增")
    else:
        # 找合適插入點：jQuery / file head 第一個 function 前
        m = re.search(r"^(\(function|document\.|const |let |var )", src, re.MULTILINE)
        insert_pos = m.start() if m else 0
        src = src[:insert_pos] + DEBOUNCE_FN + "\n" + src[insert_pos:]
        print(f"P3-4: 補上 debounce 工具函式到 {QUANT_JS.name}")

    # 包 'input' listener
    def wrap(m: re.Match) -> str:
        prefix, body = m.group(1), m.group(2)
        if "debounce(" in body:
            return m.group(0)  # 已 debounce
        return f"{prefix}debounce({body}, 250)"

    src_new = re.sub(
        r"(\.addEventListener\(\s*['\"]input['\"]\s*,\s*)([^,)]+)(\s*[,\)])",
        wrap,
        src,
    )
    src_new = re.sub(
        r"(\.addEventListener\(\s*['\"]change['\"]\s*,\s*)([^,)]+)(\s*[,\)])",
        wrap,
        src_new,
    )
    # oninput="..." 形式（少見但預防）
    src_new = re.sub(
        r'on(input|change)="([^"]+)"',
        lambda m: f'on{m.group(1)}="debounce({m.group(2)}, 250)"',
        src_new,
    )

    if src_new == src:
        print(f"P3-4: {QUANT_JS.name} 沒有 input/change listener 可包")
        return

    QUANT_JS.write_text(src_new, encoding="utf-8")
    print(f"P3-4: {QUANT_JS.name} 已加 debounce")


if __name__ == "__main__":
    main()
