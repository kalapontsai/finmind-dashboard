"""
Report Exporter
- HTML: Jinja2 模板（templates/report.html）
- 內含 SVG 折線圖（⑦ 歷史滾動 N 年收益分布）：純 Python 生成，
  不依賴 matplotlib / chart.js，self-contained。

不依賴 Flask，方便測試；吃 analyze 回傳的 result dict 直接輸出檔案
"""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = _PROJECT_ROOT / 'templates'


# ───────── HTML ─────────
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(['html', 'xml']),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html_report(analyze: dict, profile_name: str = '') -> str:
    """
    將 analyze 結果（{common, dynamic, full, forecast, ...}）轉成 HTML 字串。
    模板：templates/report.html
    """
    env = _env()
    tpl = env.get_template('report.html')
    return tpl.render(
        analyze=analyze,
        profile_name=profile_name,
        generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        rolling_chart_svg=_render_rolling_chart_svg(analyze.get('forecast') or {}),
    )


def save_html_report(analyze: dict, out_path: Path, profile_name: str = '') -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html_report(analyze, profile_name), encoding='utf-8')
    return out_path


# ───────── ⑦ 滾動 N 年收益分布圖（純 SVG）─────────
def _render_rolling_chart_svg(forecast: dict, width: int = 720, height: int = 280) -> str:
    """
    把 forecast.rolling（list of {start, end, years, cagr}）畫成 SVG 折線圖，
    再疊上 5 條水平分位線（Bear / Conservative / Base / Optimistic / Bull）。

    - 純 Python，無第三方依賴（matplotlib / chart.js 都不必裝）
    - self-contained: 所有樣式 inline
    - 顏色/虛線 與 web UI Chart.js 配色對齊（GitHub dark 配色系）
    """
    rolling = forecast.get('rolling') or []
    scenarios = forecast.get('scenarios') or []
    if not rolling or not scenarios:
        return ''

    # 取 X/Y 範圍
    cagrs_pct = [r['cagr'] * 100 for r in rolling]
    pct_band = [s['cagr'] * 100 for s in scenarios]
    y_min = min(cagrs_pct + pct_band)
    y_max = max(cagrs_pct + pct_band)
    span = max(y_max - y_min, 0.5)  # 避免全相等時除以 0
    y_min -= span * 0.08
    y_max += span * 0.08

    margin_l, margin_r, margin_t, margin_b = 56, 24, 16, 36
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    def x_of(i: int) -> float:
        if len(rolling) <= 1:
            return margin_l + plot_w / 2
        return margin_l + (i / (len(rolling) - 1)) * plot_w

    def y_of(v: float) -> float:
        return margin_t + (1 - (v - y_min) / (y_max - y_min)) * plot_h

    parts: list[str] = []

    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" height="auto" '
        f'style="font-family:Arial,Microsoft JhengHei,sans-serif;font-size:11px">'
    )

    # 座標軸背景
    parts.append(
        f'<rect x="{margin_l}" y="{margin_t}" width="{plot_w}" height="{plot_h}" '
        f'fill="#f8fafc" stroke="#cbd5e1" stroke-width="1"/>'
    )
    # Y 格線 + 標籤
    n_ticks = 5
    for k in range(n_ticks + 1):
        yv = y_min + (y_max - y_min) * k / n_ticks
        y = y_of(yv)
        parts.append(
            f'<line x1="{margin_l}" y1="{y:.2f}" x2="{margin_l + plot_w}" y2="{y:.2f}" '
            f'stroke="#e2e8f0" stroke-width="0.5"/>'
        )
        parts.append(
            f'<text x="{margin_l - 6:.2f}" y="{y + 4:.2f}" text-anchor="end" '
            f'fill="#475569">{yv:+.2f}%</text>'
        )

    # X 軸標籤（最多 6 個）
    n_x_ticks = min(6, len(rolling))
    if n_x_ticks > 0:
        step = max(1, (len(rolling) - 1) // (n_x_ticks - 1)) if n_x_ticks > 1 else 1
        for k in range(n_x_ticks):
            idx = min(k * step, len(rolling) - 1)
            x = x_of(idx)
            parts.append(
                f'<text x="{x:.2f}" y="{margin_t + plot_h + 16:.2f}" text-anchor="middle" '
                f'fill="#475569">{html.escape(rolling[idx]["end"])}</text>'
            )

    # 5 條水平分位線（虛線）
    pct_colors = {
        'Bear':         '#f85149',  # P10 紅
        'Conservative': '#d29922',  # P25 橘
        'Base':         '#58a6ff',  # P50 藍
        'Optimistic':   '#3fb950',  # P75 �
        'Bull':         '#8957e5',  # P90 紫
    }
    for s in scenarios:
        label = s.get('label') or s.get('scenario', '—')
        yv = s['cagr'] * 100
        y = y_of(yv)
        color = pct_colors.get(label, '#888')
        parts.append(
            f'<line x1="{margin_l}" y1="{y:.2f}" x2="{margin_l + plot_w}" y2="{y:.2f}" '
            f'stroke="{color}" stroke-width="1.2" stroke-dasharray="5,4" opacity="0.85"/>'
        )
        # 行尾 label: 情境名 + 分位 + CAGR
        q = int((s.get('quantile') or s.get('percentile') or 0) * 100)
        tag = f'{label} P{q} {yv:+.2f}%'
        parts.append(
            f'<rect x="{margin_l + plot_w - 118:.2f}" y="{y - 9:.2f}" width="116" height="14" '
            f'fill="white" opacity="0.9" rx="2"/>'
        )
        parts.append(
            f'<text x="{margin_l + plot_w - 4:.2f}" y="{y + 3:.2f}" text-anchor="end" '
            f'fill="{color}" font-weight="bold">{html.escape(tag)}</text>'
        )

    # 主折線（滾動 CAGR）
    pts: list[str] = []
    for i, r in enumerate(rolling):
        pts.append(f'{x_of(i):.2f},{y_of(r["cagr"] * 100):.2f}')
    if pts:
        parts.append(
            f'<polyline fill="none" stroke="#58a6ff" stroke-width="1.6" '
            f'points="{" ".join(pts)}"/>'
        )

    # 右上小字（N / 樣本數）
    n = forecast.get('n', '—')
    rc = len(rolling)
    parts.append(
        f'<text x="{margin_l + plot_w:.2f}" y="{margin_t + 10:.2f}" text-anchor="end" '
        f'fill="#64748b">N = {n} 年　樣本數 = {rc}</text>'
    )

    # Y 軸標題（旋轉）
    parts.append(
        f'<text x="{margin_l - 44}" y="{margin_t + plot_h / 2:.2f}" '
        f'transform="rotate(-90 {margin_l - 44},{margin_t + plot_h / 2:.2f})" '
        f'text-anchor="middle" fill="#64748b">年化報酬率（CAGR）</text>'
    )

    parts.append('</svg>')
    return ''.join(parts)
