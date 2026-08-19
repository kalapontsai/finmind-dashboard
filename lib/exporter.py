"""
Report Exporter
- HTML: Jinja2 模板（templates/report.html）
- PDF:  reportlab Platypus（純 Python，無 binary deps）

不依賴 Flask，方便測試；吃 analyze 回傳的 result dict 直接輸出檔案
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

# reportlab imports（延遲到函式內，避免冷啟動慢 / 缺套件時早炸）
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
    )


def save_html_report(analyze: dict, out_path: Path, profile_name: str = '') -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html_report(analyze, profile_name), encoding='utf-8')
    return out_path


# ───────── PDF ─────────
def _fmt_pct(x) -> str:
    if x is None or (isinstance(x, float) and (x != x)):
        return '—'
    return f'{x * 100:.2f}%'


def _fmt_money(x) -> str:
    if x is None or (isinstance(x, float) and (x != x)):
        return '—'
    return f'{int(round(x)):,}'


def _fmt_float(x, digits: int = 3) -> str:
    if x is None or (isinstance(x, float) and (x != x)):
        return '—'
    return f'{x:.{digits}f}'


def _mode_summary(analyze: dict, mode: str) -> dict | None:
    """analyze 結果結構：{ common: {...}, dynamic: {...}, full: {...} }"""
    return analyze.get(mode)


def render_pdf_report(analyze: dict, out_path: Path, profile_name: str = '') -> Path:
    """
    用 reportlab 產出 PDF。
    analyze: 來自 /api/analyze 的結果（包含 3 模式 + forecast + history 摘要）
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak,
    )

    # 註冊中文字型（reportlab 內建 STSong-Light 簡中；繁中也吃）
    try:
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        cn_font = 'STSong-Light'
    except Exception:
        cn_font = 'Helvetica'

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title='Portfolio Historical Forecast Report',
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=styles['Heading1'], fontName=cn_font, fontSize=18, leading=22, spaceAfter=10)
    h2 = ParagraphStyle('h2', parent=styles['Heading2'], fontName=cn_font, fontSize=14, leading=18, spaceAfter=8, textColor=colors.HexColor('#17365d'))
    body = ParagraphStyle('body', parent=styles['Normal'], fontName=cn_font, fontSize=10, leading=14)
    small = ParagraphStyle('small', parent=styles['Normal'], fontName=cn_font, fontSize=8, leading=11, textColor=colors.HexColor('#555'))
    note = ParagraphStyle('note', parent=styles['Normal'], fontName=cn_font, fontSize=9, leading=12, textColor=colors.HexColor('#7a5b00'))

    story = []
    fc = analyze.get('forecast') or {}
    inputs = analyze.get('inputs') or {}
    history = analyze.get('history') or {}

    # ───── 標題 ─────
    story.append(Paragraph('股票組合歷史回測 + N 年後情境報告', h1))
    sub = f"用戶名單：{profile_name or '（未指定）'}　｜　N = {fc.get('n', '—')} 年　｜　目前資產：{_fmt_money(fc.get('pv'))}　｜　生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    story.append(Paragraph(sub, small))
    story.append(Spacer(1, 6 * mm))

    # ───── 個股歷史摘要 ─────
    story.append(Paragraph('一、個股歷史長度診斷', h2))
    diag = history.get('all_per_stock') or {}
    if diag:
        rows = [['股票代號', '歷史年數']]
        for t, yrs in sorted(diag.items()):
            rows.append([t, f'{yrs:.2f}'])
        hist_overview = history.get('overview') or {}
        rows.append(['─── 統計 ───', '───'])
        rows.append(['股票數', f"{hist_overview.get('stocks', len(diag))}"])
        rows.append(['最短 / 中位 / 最長', f"{hist_overview.get('min_years', 0):.2f} / {hist_overview.get('median_years', 0):.2f} / {hist_overview.get('max_years', 0):.2f} 年"])
        t = Table(rows, colWidths=[50 * mm, 80 * mm])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), cn_font),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef3f8')),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, -3), (-1, -3), colors.HexColor('#fff7e6')),
        ]))
        story.append(t)
    story.append(Spacer(1, 5 * mm))

    # ───── 三模式 → 三表 ─────
    story.append(Paragraph('二、歷史回測三模式結果', h2))
    mode_names = {'common': 'Common Period（共同期間）', 'dynamic': 'Dynamic Entry（動態加入）', 'full': 'Full Available History（可觀測歷史）'}
    for key in ('common', 'dynamic', 'full'):
        m = _mode_summary(analyze, key)
        if not m:
            continue
        story.append(Paragraph(f'▶ {mode_names[key]}', h2))
        mtr = m.get('metrics') or {}
        rows = [
            ['起始', '結束', '年數', 'CAGR', 'MDD', 'Vol', 'Sharpe'],
            [
                str(mtr.get('start', '—')),
                str(mtr.get('end', '—')),
                _fmt_float(mtr.get('years'), 2),
                _fmt_pct(mtr.get('cagr')),
                _fmt_pct(mtr.get('mdd')),
                _fmt_pct(mtr.get('volatility')),
                _fmt_float(mtr.get('sharpe'), 3),
            ],
        ]
        t = Table(rows, colWidths=[28 * mm, 28 * mm, 16 * mm, 24 * mm, 24 * mm, 24 * mm, 22 * mm])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), cn_font),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef3f8')),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
            ('ALIGN', (0, 1), (-1, -1), 'RIGHT'),
        ]))
        story.append(t)
        story.append(Spacer(1, 4 * mm))
    story.append(PageBreak())

    # ───── Forecast ─────
    story.append(Paragraph('三、未來 N 年情境終值', h2))
    story.append(Paragraph(
        '取 Portfolio NAV 的歷史 N-Year rolling CAGR 分布對應分位數，'
        '再以 PV × (1+r)^N 計算 N 年後終值。',
        note,
    ))
    story.append(Spacer(1, 3 * mm))

    if not fc:
        story.append(Paragraph('（無 forecast 結果）', body))
    else:
        rows = [['情境', '分位數', '歷史 N-Year CAGR', '目前資產', 'N 年後', '倍數']]
        for s in fc.get('scenarios', []):
            rows.append([
                s.get('scenario', '—'),
                f"P{int(s.get('percentile', 0) * 100)}",
                _fmt_pct(s.get('cagr')),
                _fmt_money(fc.get('pv')),
                _fmt_money(s.get('future_value')),
                f"{s.get('multiple', 0):.2f}x",
            ])
        t = Table(rows, colWidths=[40 * mm, 20 * mm, 30 * mm, 28 * mm, 32 * mm, 16 * mm])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), cn_font),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef3f8')),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#fff7e6')),  # Base 高亮
        ]))
        story.append(t)
        story.append(Spacer(1, 4 * mm))

        # rolling 樣本數
        story.append(Paragraph(
            f'歷史 N-Year rolling 樣本數：<b>{fc.get("rolling_count", 0)}</b>',
            body,
        ))

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        '研究解讀：上述結果為「歷史 N-Year 持有期間曾經出現的結果分布」，'
        '不代表未來一定達成；也不構成任何投資建議。',
        small,
    ))

    doc.build(story)
    return out_path
