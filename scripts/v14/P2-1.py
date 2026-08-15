"""
P2-1: 策略對比獨立 /compare 分頁
- 新增 routes/api.py `POST /api/quant_compare`（跑多策略組合，回傳對照）
- 新增 templates/compare.html（最小可用 UI）
- 新增 static/js/compare.js（fetch + render）

驗收：
- routes/api.py 有 `quant_compare` handler
- templates/compare.html 存在
- static/js/compare.js 存在
- py_compile 通過
"""
from __future__ import annotations

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
API_PY = PROJECT_DIR / "routes" / "api.py"
COMPARE_HTML_PATH = PROJECT_DIR / "templates" / "compare.html"
COMPARE_JS_PATH = PROJECT_DIR / "static" / "js" / "compare.js"


# ───── /api/quant_compare handler ─────
QUANT_COMPARE_HANDLER = '''

@api_bp.post("/quant_compare")
def quant_compare():
    """
    策略對比：一次跑 value / momentum / quality 三組，回傳三條淨值曲線 + KPI 對照表。
    Body: {
        "pool": ["2330", "0050", ...],
        "weights": {"value": 0.4, "momentum": 0.3, "quality": 0.3},
        "start": "2023-01-01",
        "end": "2026-08-15",
        "top_n": 5,
        "fee_buy": 0.001425,
        "fee_sell": 0.001425,
        "tax_sell": 0.003,
        "slippage": 0.001,
        "standardize": "rank"
    }
    """
    try:
        body = request.get_json(force=True, silent=False) or {}
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "invalid json body"}), 400

    pool = body.get("pool") or []
    weights = body.get("weights") or {"value": 0.4, "momentum": 0.3, "quality": 0.3}
    start = body.get("start", "2023-01-01")
    end = body.get("end", "")
    top_n = int(body.get("top_n", 5))
    standardize = body.get("standardize", "rank")

    # 三組：value only / momentum only / quality only + 用户指定權重的組合
    combos = [
        {"name": "value",    "strategies": [{"name": "value",    "enabled": True, "weight": 1.0, "params": {}}]},
        {"name": "momentum", "strategies": [{"name": "momentum", "enabled": True, "weight": 1.0, "params": {}}]},
        {"name": "quality",  "strategies": [{"name": "quality",  "enabled": True, "weight": 1.0, "params": {}}]},
        {
            "name": "blend",
            "strategies": [
                {"name": k, "enabled": True, "weight": v, "params": {}}
                for k, v in weights.items() if v > 0
            ],
        },
    ]

    results = []
    for combo in combos:
        if not combo["strategies"]:
            continue
        try:
            from lib.quant_runner import run_quant_sync  # type: ignore
            r = run_quant_sync(
                pool=pool, strategies=combo["strategies"], rebalance_freq="monthly",
                top_n=top_n, start=start, end=end,
                fee_buy=body.get("fee_buy", 0.001425),
                fee_sell=body.get("fee_sell", 0.001425),
                tax_sell=body.get("tax_sell", 0.003),
                slippage=body.get("slippage", 0.001),
                standardize=standardize,
            )
            results.append({
                "name": combo["name"],
                "kpis": r.get("kpis", {}) if isinstance(r, dict) else {},
                "nav_curve": r.get("nav_curve", []) if isinstance(r, dict) else [],
            })
        except (ImportError, KeyError, ValueError, TypeError) as exc:
            results.append({"name": combo["name"], "error": str(exc)})

    return jsonify({"ok": True, "results": results})
'''


# ───── compare.html ─────
COMPARE_HTML_CONTENT = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="utf-8">
  <title>策略對比 — FinMind</title>
  <link rel="stylesheet" href="/static/css/finlab.css">
  <link rel="stylesheet" href="/static/css/quant.css">
  <script src="/static/js/compare.js" defer></script>
</head>
<body>
  <header class="topbar">
    <h1>策略對比 (v1.4 P2-1)</h1>
    <nav><a href="/">回首頁</a></nav>
  </header>

  <main>
    <section class="compare-form">
      <label>股票池（逗號分隔）
        <input id="pool-input" type="text" placeholder="2330,0050,2884">
      </label>
      <label>回測起 <input id="start-input" type="date" value="2023-01-01"></label>
      <label>回測迄 <input id="end-input" type="date"></label>
      <label>top_n <input id="topn-input" type="number" min="1" max="20" value="5"></label>

      <fieldset>
        <legend>策略權重</legend>
        <label>value <input id="w-value" type="number" step="0.05" value="0.4"></label>
        <label>momentum <input id="w-momentum" type="number" step="0.05" value="0.3"></label>
        <label>quality <input id="w-quality" type="number" step="0.05" value="0.3"></label>
        <span id="weight-sum">總和: 1.00</span>
        <button id="run-btn" type="button">執行對比</button>
      </fieldset>
    </section>

    <section class="compare-result">
      <table id="kpi-table" border="1">
        <thead>
          <tr>
            <th>策略</th><th>累計報酬</th><th>Sharpe</th><th>MDD</th><th>換倉次數</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
      <div id="nav-chart"></div>
    </section>
  </main>
</body>
</html>
"""


# ───── compare.js ─────
COMPARE_JS_CONTENT = """// /compare page — v1.4 P2-1
const $ = (id) => document.getElementById(id);

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function readForm() {
  const pool = $('pool-input').value.split(',').map(s => s.trim()).filter(Boolean);
  const weights = {
    value: parseFloat($('w-value').value) || 0,
    momentum: parseFloat($('w-momentum').value) || 0,
    quality: parseFloat($('w-quality').value) || 0,
  };
  const wsum = (weights.value + weights.momentum + weights.quality).toFixed(2);
  $('weight-sum').textContent = '總和: ' + wsum;
  return {
    pool, weights,
    start: $('start-input').value || '2023-01-01',
    end:   $('end-input').value || new Date().toISOString().slice(0, 10),
    top_n: parseInt($('topn-input').value, 10) || 5,
  };
}

const updateWeightSum = debounce(() => readForm(), 200);
['w-value', 'w-momentum', 'w-quality'].forEach(id => $(id).addEventListener('input', updateWeightSum));

async function runCompare() {
  const body = readForm();
  $('run-btn').disabled = true;
  $('run-btn').textContent = '執行中...';
  try {
    const res = await fetch('/api/quant_compare', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!data.ok) {
      alert('對比失敗：' + (data.error || '未知錯誤'));
      return;
    }
    renderTable(data.results);
    renderChart(data.results);
  } catch (err) {
    alert('網路錯誤：' + err.message);
  } finally {
    $('run-btn').disabled = false;
    $('run-btn').textContent = '執行對比';
  }
}

function renderTable(results) {
  const tbody = document.querySelector('#kpi-table tbody');
  tbody.innerHTML = '';
  for (const r of results) {
    if (r.error) {
      tbody.insertAdjacentHTML('beforeend',
        `<tr><td>${r.name}</td><td colspan="4" style="color:red">${r.error}</td></tr>`);
      continue;
    }
    const k = r.kpis || {};
    tbody.insertAdjacentHTML('beforeend',
      `<tr>
        <td>${r.name}</td>
        <td>${(k.cum_return * 100 || 0).toFixed(2)}%</td>
        <td>${(k.sharpe || 0).toFixed(2)}</td>
        <td>${(k.mdd * 100 || 0).toFixed(2)}%</td>
        <td>${k.rebalance_count || 0}</td>
      </tr>`);
  }
}

function renderChart(results) {
  const el = $('nav-chart');
  el.innerHTML = '<pre>' + JSON.stringify(
    results.map(r => ({ name: r.name, n_points: (r.nav_curve || []).length })),
    null, 2) + '</pre>';
}

$('run-btn').addEventListener('click', runCompare);
"""


def patch_api() -> None:
    """最簡：在檔末追加 /api/quant_compare handler（避免 regex 切壞 def）"""
    src = API_PY.read_text(encoding="utf-8")

    if "/quant_compare" in src or "def quant_compare" in src:
        print(f"P2-1: {API_PY.name} 已有 /api/quant_compare，跳過")
        return

    # append-at-end 是最穩的做法，避免 regex 切壞 def 開頭
    new_src = src.rstrip() + "\n" + QUANT_COMPARE_HANDLER + "\n"
    API_PY.write_text(new_src, encoding="utf-8")
    print(f"P2-1: {API_PY.name} 已 append /api/quant_compare 到檔末")


def write_templates() -> None:
    COMPARE_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMPARE_HTML_PATH.write_text(COMPARE_HTML_CONTENT, encoding="utf-8")
    print(f"P2-1: 寫入 {COMPARE_HTML_PATH.relative_to(PROJECT_DIR)}")


def write_js() -> None:
    COMPARE_JS_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMPARE_JS_PATH.write_text(COMPARE_JS_CONTENT, encoding="utf-8")
    print(f"P2-1: 寫入 {COMPARE_JS_PATH.relative_to(PROJECT_DIR)}")


def main() -> None:
    patch_api()
    write_templates()
    write_js()

    # py_compile 確認
    import py_compile
    try:
        py_compile.compile(str(API_PY), doraise=True)
        print("P2-1: py_compile OK")
    except py_compile.PyCompileError as e:
        raise SystemExit(f"routes/api.py 語法錯誤：{e}")


if __name__ == "__main__":
    main()
