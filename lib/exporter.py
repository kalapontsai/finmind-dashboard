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
    analyze: 來自 /api/analyze 的結果
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
    h3 = ParagraphStyle('h3', parent=styles['Heading3'], fontName=cn_font, fontSize=12, leading=16, spaceAfter=6, textColor=colors.HexColor('#17365d'))
    body = ParagraphStyle('body', parent=styles['Normal'], fontName=cn_font, fontSize=10, leading=14)
    small = ParagraphStyle('small', parent=styles['Normal'], fontName=cn_font, fontSize=8, leading=11, textColor=colors.HexColor('#555'))
    note = ParagraphStyle('note', parent=styles['Normal'], fontName=cn_font, fontSize=9, leading=12, textColor=colors.HexColor('#7a5b00'))
    warn = ParagraphStyle('warn', parent=styles['Normal'], fontName=cn_font, fontSize=9, leading=13, textColor=colors.HexColor('#8b4500'))

    story = []
    fc = analyze.get('forecast') or {}
    inputs = analyze.get('inputs') or {}
    history = analyze.get('history') or {}
    mv = analyze.get('market_value') or {}

    # ───── 標題 ─────
    story.append(Paragraph('股票組合歷史回測 + N 年後情境報告', h1))
    pv_text = _fmt_money(fc.get('pv')) + f"（{inputs.get('pv_source', '—')}）"
    sub = (f"用戶名單：{profile_name or '（未指定）'}　｜　"
           f"N = {fc.get('n', '—')} 年　｜　目前資產：{pv_text}　｜　"
           f"生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    story.append(Paragraph(sub, small))
    story.append(Spacer(1, 6 * mm))

    # ───── 0. 起始市值 ─────
    story.append(Paragraph('零、組合起始市值', h2))
    if mv:
        rows = [
            ['估值日', _fmt_money(mv.get('total')), '總市值'],
        ]
        t = Table(rows, colWidths=[40 * mm, 50 * mm, 40 * mm])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), cn_font),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef3f8')),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
        ]))
        story.append(t)
        # per-stock 細節
        ps_rows = [['股票', '股數', '收盤價', '市值', '權重']]
        total = mv.get('total', 0) or 1
        for s in sorted(mv.get('per_stock', []), key=lambda x: -x['value']):
            ps_rows.append([
                s.get('ticker', '—'),
                f"{s.get('shares', 0):,}",
                _fmt_float(s.get('close'), 2),
                _fmt_money(s.get('value')),
                f"{s.get('value', 0) / total * 100:.1f}%",
            ])
        t = Table(ps_rows, colWidths=[25 * mm, 35 * mm, 30 * mm, 40 * mm, 25 * mm])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), cn_font),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef3f8')),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#cccccc')),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ]))
        story.append(t)
    story.append(Spacer(1, 5 * mm))

    # ───── 0.5. Ticker 驗證 ─────
    tm = inputs.get('ticker_match') or {}
    short = set(inputs.get('short_history') or [])
    if tm:
        story.append(Paragraph('零點五、Ticker 驗證結果', h2))
        rows = [['stock_id', '名稱', '市場', '使用者原始', '備註']]
        for m in sorted(tm.values(), key=lambda x: x['stock_id']):
            tag = '（原 ' + m['matched_from'][0] + '）' if m['source'] != 'exact' else ''
            warn_mark = ' ⚠️ < ' + str(fc.get('n', 10)) + '年' if m['stock_id'] in short else ''
            rows.append([
                m['stock_id'] + tag,
                m.get('stock_name', '—'),
                m.get('type', '—'),
                ', '.join(m.get('matched_from', [])),
                warn_mark,
            ])
        t = Table(rows, colWidths=[35 * mm, 50 * mm, 18 * mm, 30 * mm, 25 * mm])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), cn_font),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef3f8')),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#cccccc')),
            ('TEXTCOLOR', (4, 1), (4, -1), colors.HexColor('#b42318')),
        ]))
        story.append(t)
    story.append(Spacer(1, 5 * mm))

    # ───── 1. 個股歷史長度 ─────
    story.append(Paragraph('一、個股歷史長度診斷', h2))
    psh = history.get('per_stock') or {}
    if psh:
        rows = [['股票', '第一天', '最後一天', '資料點', '歷史年數', '首日收盤']]
        for t in sorted(psh.keys()):
            info = psh[t]
            rows.append([
                t + (' ⚠️' if t in short else ''),
                info.get('first_date') or '—',
                info.get('last_date') or '—',
                str(info.get('rows', 0)),
                f"{info.get('years', 0):.2f}",
                _fmt_float(info.get('first_close'), 2),
            ])
        ov = history.get('overview') or {}
        rows.append([
            f"統計（{ov.get('stocks', 0)} 檔）",
            '—', '—', '—',
            f"{ov.get('min_years', 0):.2f} / {ov.get('median_years', 0):.2f} / {ov.get('max_years', 0):.2f}",
            '—',
        ])
        t = Table(rows, colWidths=[25 * mm, 30 * mm, 30 * mm, 22 * mm, 32 * mm, 25 * mm])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), cn_font),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef3f8')),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fff7e6')),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#cccccc')),
            ('TEXTCOLOR', (0, 1), (0, -2), colors.HexColor('#b42318')),
        ]))
        story.append(t)
    story.append(Spacer(1, 5 * mm))

    # ───── 2. 三模式 → 三表 ─────
    story.append(Paragraph('二、歷史回測三模式結果', h2))
    mode_names = {'common': 'Common Period（共同期間）', 'dynamic': 'Dynamic Entry（動態加入）', 'full': 'Full Available History（可觀測歷史）'}
    for key in ('common', 'dynamic', 'full'):
        m = _mode_summary(analyze, key)
        if not m:
            continue
        story.append(Paragraph(f'▶ {mode_names[key]}', h3))
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

    # ───── 3. Forecast ─────
    story.append(Paragraph('三、未來 N 年情境終值', h2))
    basis_text = f"（基於 {fc.get('basis', '—')} 模式）" if fc.get('basis') else ''
    story.append(Paragraph(
        f'取 Portfolio NAV 的歷史 N-Year rolling CAGR 分布對應分位數，'
        f'以 PV × (1+r)^N 計算 N 年後終值 {basis_text}。不模擬逐年路徑。',
        note,
    ))
    story.append(Spacer(1, 3 * mm))

    if not fc:
        story.append(Paragraph('（無 forecast 結果）', body))
    else:
        scenarios = fc.get('scenarios', [])
        rows = [['情境', '分位數', '歷史 N-Year CAGR', '目前資產', 'N 年後', '倍數']]
        for s in scenarios:
            rows.append([
                s.get('scenario', '—'),
                f"P{int(s.get('percentile', 0) * 100)}",
                _fmt_pct(s.get('cagr')),
                _fmt_money(fc.get('pv')),
                _fmt_money(s.get('future_value')),
                f"{s.get('multiple', 0):.2f}x",
            ])
        t = Table(rows, colWidths=[40 * mm, 20 * mm, 30 * mm, 28 * mm, 32 * mm, 16 * mm])
        styles = [
            ('FONTNAME', (0, 0), (-1, -1), cn_font),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef3f8')),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ]
        # 只在 scenarios >= 4 row(Base 在 row 3)時才高亮(避免 index out of range)
        if len(scenarios) >= 4:
            styles.append(('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#fff7e6')))
        t.setStyle(TableStyle(styles))
        story.append(t)
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(
            f'歷史 N-Year rolling 樣本數：<b>{fc.get("rolling_count", 0)}</b>',
            body,
        ))

    story.append(Spacer(1, 8 * mm))

    # ───── 4. 研究限制提醒 ─────
    story.append(Paragraph('四、研究限制提醒', h2))
    limits = [
        '<b>Survivorship Bias</b>：本名單是 2026 年仍存在的持股。若用來回測 2010-2020，'
        '這段期間下市的股票已被默默排除，會高估歷史報酬。',
        '<b>Look-Ahead Bias</b>：本工具使用的權重 / 持股是「現在的決定」，'
        '不模擬「當時不知道的未來」。',
        '<b>股利/除權息</b>：FinMind TaiwanStockPrice 的 close 為「調整後收盤價」（adj_close），'
        '已含除權息還原。CAGR 含股利再投資效果。',
        '<b>交易成本</b>：本版未計手續費 / 證交稅 / 滑價。'
        '實際買入需扣 0.1425% 手續費、賣出再扣 0.3% 證交稅。',
        '<b>Forecast 語意</b>：P10/P50/P90 是「歷史上相同 N 年持有期間的結果分布」，'
        '<b>不是未來保證</b>。',
    ]
    for txt in limits:
        story.append(Paragraph('• ' + txt, warn))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        '本工具為歷史回測情境參考，<b>不構成投資建議</b>。',
        small,
    ))

    doc.build(story)
    return out_path
