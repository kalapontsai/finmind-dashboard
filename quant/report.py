"""
HTML 報表生成器
- 用 plotly 產生互動圖
- 單一自包含 HTML 檔（含圖表 + 表格 + 設定）
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import (
    COMMISSION, END_DATE, MOMENTUM_LOOKBACK, OUTPUT_DIR,
    REPORT_FILE, RESULTS_JSON, SLIPPAGE, START_DATE, STOCK_POOL, TAX, TOP_N, WEIGHTS,
)


def _fmt_pct(v: float, dec: int = 2) -> str:
    return f"{v * 100:.{dec}f}%"


def _fmt_num(v: float, dec: int = 2) -> str:
    return f"{v:,.{dec}f}"


def build_charts(result) -> dict:
    """回傳所有 plotly figure 的 HTML 字串。"""
    close = result.close
    cum_strategy = result.cum_strategy
    cum_benchmark = result.cum_benchmark

    # 1. 累計淨值曲線（策略 + 雙基準 B&H）
    fig_equity = go.Figure()
    fig_equity.add_trace(go.Scatter(
        x=cum_strategy.index, y=cum_strategy.values,
        name='多因子策略', line=dict(color='#58a6ff', width=2),
        fill='tozeroy', fillcolor='rgba(88, 166, 255, 0.1)',
    ))
    # 雙基準 B&H：池子等權重
    fig_equity.add_trace(go.Scatter(
        x=cum_benchmark.index, y=cum_benchmark.values,
        name='B&H（池子等權）', line=dict(color='#8b949e', width=1.5, dash='dash'),
    ))
    # 雙基準 B&H：0050 市場
    if result.cum_market_0050 is not None:
        fig_equity.add_trace(go.Scatter(
            x=result.cum_market_0050.index, y=result.cum_market_0050.values,
            name='B&H（0050 市場）', line=dict(color='#d29922', width=1.5, dash='dot'),
        ))
    fig_equity.update_layout(
        title='累計淨值曲線',
        xaxis_title='日期', yaxis_title='淨值（初始 = 1.0）',
        hovermode='x unified', template='plotly_dark',
        height=450, margin=dict(l=60, r=20, t=50, b=40),
    )

    # 2. Drawdown
    dd_strategy = cum_strategy / cum_strategy.cummax() - 1
    dd_benchmark = cum_benchmark / cum_benchmark.cummax() - 1
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(
        x=dd_strategy.index, y=dd_strategy.values * 100,
        name='策略 Drawdown', line=dict(color='#f85149', width=1.5),
        fill='tozeroy', fillcolor='rgba(248, 81, 73, 0.15)',
    ))
    fig_dd.add_trace(go.Scatter(
        x=dd_benchmark.index, y=dd_benchmark.values * 100,
        name='B&H Drawdown', line=dict(color='#8b949e', width=1, dash='dash'),
    ))
    fig_dd.update_layout(
        title='Drawdown (%)',
        xaxis_title='日期', yaxis_title='回撤 (%)',
        hovermode='x unified', template='plotly_dark',
        height=350, margin=dict(l=60, r=20, t=50, b=40),
    )

    # 3. 月度換倉成本
    fig_cost = go.Figure()
    fig_cost.add_trace(go.Bar(
        x=result.monthly_cost.index, y=result.monthly_cost.values * 100,
        marker_color='#d29922', name='月度換倉成本 (%)',
    ))
    fig_cost.update_layout(
        title='每月換倉成本',
        xaxis_title='月份', yaxis_title='成本 (%)',
        template='plotly_dark', height=300,
        margin=dict(l=60, r=20, t=50, b=40),
    )

    return {
        'equity': fig_equity.to_html(include_plotlyjs='cdn', full_html=False),
        'drawdown': fig_dd.to_html(include_plotlyjs=False, full_html=False),
        'cost': fig_cost.to_html(include_plotlyjs=False, full_html=False),
    }


def render_html(result) -> str:
    """組 HTML 字串。"""
    charts = build_charts(result)
    k = result.kpis

    selected_rows = ''
    for date_str in sorted(result.selected_monthly.keys()):
        stocks = result.selected_monthly[date_str]
        chips = ' '.join(f'<span class="chip">{s}</span>' for s in stocks)
        # v1.4 walk-forward：驗證期的選股以淡化顯示（鎖倉不換倉，但 selected 仍記錄原候選）
        is_validation = (
            k.get('walk_forward_enabled')
            and k.get('walk_forward_split_date')
            and date_str >= k['walk_forward_split_date']
        )
        row_class = ' class="wf-val"' if is_validation else ''
        selected_rows += f'<tr{row_class}><td>{date_str}</td><td>{chips}</td></tr>'

    # 雙基準 alpha 格式化
    pool_alpha_val = k.get('pool_excess_return', 0)
    market_alpha_val = k.get('market_alpha')
    market_bench_val = k.get('market_benchmark_return')
    pool_bench_val = k.get('pool_benchmark_return', 0)
    market_alpha_html = ''
    if market_alpha_val is not None and market_bench_val is not None:
        market_alpha_html = f'''
        <div class="kpi">
            <div class="label">市場 alpha（vs 0050）</div>
            <div class="value {"pos" if market_alpha_val >= 0 else "neg"}">{_fmt_pct(market_alpha_val)}</div>
        </div>
        <div class="kpi">
            <div class="label">0050 B&amp;H</div>
            <div class="value {"pos" if market_bench_val >= 0 else "neg"}">{_fmt_pct(market_bench_val)}</div>
        </div>'''

    config_html = f"""
    <div class="config">
        <div class="row"><span class="lbl">回測區間</span><span>{START_DATE} ~ {END_DATE}</span></div>
        <div class="row"><span class="lbl">股票池</span><span>{len(STOCK_POOL)} 檔</span></div>
        <div class="row"><span class="lbl">Top N</span><span>{TOP_N} 檔（等權 {1/TOP_N:.0%}）</span></div>
        <div class="row"><span class="lbl">動能回看</span><span>{MOMENTUM_LOOKBACK} 日</span></div>
        <div class="row"><span class="lbl">因子權重</span><span>價值 {WEIGHTS['value']:.0%} / 動能 {WEIGHTS['momentum']:.0%} / 品質 {WEIGHTS['quality']:.0%}</span></div>
        <div class="row"><span class="lbl">費率</span><span>買 {COMMISSION:.4%} / 賣 {COMMISSION:.4%}+{TAX:.3%} / 滑價 {SLIPPAGE:.3%}</span></div>
        <div class="row"><span class="lbl">除權息調整</span><span>{getattr(result, 'adjust_method', 'none')}</span></div>
        <div class="row"><span class="lbl">交易日</span><span>{k['trading_days']}</span></div>
        {('<div class="row"><span class="lbl">🔬 Walk-forward</span>'
          '<span>訓練 {train_pct:.0%} / 驗證 {val_pct:.0%}（切點 {split_date}）</span></div>').format(
              train_pct=k.get('train_pct', 0.7),
              val_pct=1 - k.get('train_pct', 0.7),
              split_date=k.get('walk_forward_split_date', '—'),
          ) if k.get('walk_forward_enabled') else ''}
    </div>
    """

    kpi_html = f"""
    <div class="kpis">
        <div class="kpi">
            <div class="label">策略總報酬</div>
            <div class="value {'pos' if k['total_return'] >= 0 else 'neg'}">{_fmt_pct(k['total_return'])}</div>
        </div>
        <div class="kpi">
            <div class="label">B&amp;H（池子等權）</div>
            <div class="value {'pos' if pool_bench_val >= 0 else 'neg'}">{_fmt_pct(pool_bench_val)}</div>
        </div>
        <div class="kpi">
            <div class="label">池子 alpha</div>
            <div class="value {'pos' if pool_alpha_val >= 0 else 'neg'}">{_fmt_pct(pool_alpha_val)}</div>
        </div>
        {market_alpha_html}
        <div class="kpi">
            <div class="label">MDD</div>
            <div class="value neg">{_fmt_pct(k['mdd'])}</div>
        </div>
        <div class="kpi">
            <div class="label">Sharpe</div>
            <div class="value">{k['sharpe']:.2f}</div>
        </div>
        <div class="kpi">
            <div class="label">總換倉次數</div>
            <div class="value">{k['rebalance_count']}</div>
        </div>
        {('<div class="kpi wf" style="border-left-color:#d29922;">'
          '<div class="label">🔬 訓練期報酬</div>'
          '<div class="value {cls1}">{v1}</div>'
          '</div>'
          '<div class="kpi wf" style="border-left-color:#d29922;">'
          '<div class="label">🔬 驗證期報酬</div>'
          '<div class="value {cls2}">{v2}</div>'
          '</div>'
          '<div class="kpi wf" style="border-left-color:#d29922;">'
          '<div class="label">🔬 衰退 (val-train)</div>'
          '<div class="value {cls3}">{v3}</div>'
          '</div>').format(
              cls1='pos' if k.get('training_return', 0) >= 0 else 'neg',
              v1=_fmt_pct(k.get('training_return', 0)),
              cls2='pos' if k.get('validation_return', 0) >= 0 else 'neg',
              v2=_fmt_pct(k.get('validation_return', 0)),
              cls3='pos' if k.get('walk_forward_decay', 0) >= 0 else 'neg',
              v3=_fmt_pct(k.get('walk_forward_decay', 0)),
          ) if k.get('walk_forward_enabled') else ''}
    </div>
    """

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>FinMind 多因子回測報告</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Microsoft JhengHei', sans-serif;
    background: #0d1117; color: #c9d1d9; margin: 0; padding: 20px;
}}
.wrap {{ max-width: 1280px; margin: 0 auto; }}
h1 {{ color: #58a6ff; margin: 0 0 6px; font-size: 22px; }}
.subtitle {{ color: #8b949e; font-size: 13px; margin-bottom: 24px; }}
.card {{
    background: #161b22; border: 1px solid #30363d; border-radius: 12px;
    padding: 20px; margin-bottom: 16px;
}}
.card-title {{ color: #8b949e; font-size: 12px; text-transform: uppercase;
               letter-spacing: 0.5px; font-weight: 600; margin-bottom: 16px; }}
.config {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 8px; }}
.config .row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #21262d; }}
.config .lbl {{ color: #8b949e; font-size: 12px; }}
.config span:last-child {{ color: #c9d1d9; font-size: 13px; font-family: 'SF Mono', Monaco, Consolas, monospace; }}
.kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
.kpi {{
    background: #21262d; padding: 14px 16px; border-radius: 8px;
    border-left: 4px solid #30363d;
}}
.kpi .label {{ color: #8b949e; font-size: 11px; margin-bottom: 6px; }}
.kpi .value {{ font-size: 22px; font-weight: 700; font-family: 'SF Mono', Monaco, Consolas, monospace; }}
.kpi .value.pos {{ color: #3fb950; }}
.kpi .value.neg {{ color: #f85149; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ padding: 6px 10px; text-align: left; border-bottom: 1px solid #21262d; }}
th {{ color: #8b949e; font-weight: 600; background: #21262d; position: sticky; top: 0; }}
.chip {{
    display: inline-block; background: #21262d; color: #58a6ff;
    padding: 2px 8px; border-radius: 4px; margin: 2px;
    font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 12px;
    border: 1px solid #30363d;
}}
tr.wf-val td {{ opacity: 0.45; }}
tr.wf-val td:first-child::after {{ content: ' 🔒'; color: #d29922; font-size: 10px; }}
.footer {{ color: #6e7681; font-size: 11px; margin-top: 30px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
    <h1>FinMind 多因子回測報告</h1>
    <div class="subtitle">產生時間 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>

    {('<div style="background:rgba(63, 185, 80, 0.15); border:1px solid #3fb950; border-radius:6px; padding:10px 14px; margin:8px 0 20px 0; font-size:13px; color:#3fb950;">'
      '✓ <strong>含息總報酬</strong>：已套用 <code>TaiwanStockDividend</code> 資料，'
      '採用 <code>' + getattr(result, 'adjust_method', 'none') + '</code> 調整方式，'
      '現金股利與股票股利皆計入報酬。'
      '</div>') if getattr(result, 'include_dividends', False) else (
      '<div style="background:rgba(210, 153, 34, 0.15); border:1px solid #d29922; border-radius:6px; padding:10px 14px; margin:8px 0 20px 0; font-size:13px; color:#d29922;">'
      '⚠ <strong>未含息報酬</strong>：本回測未計入現金股利 / 股票股利 / 除權息調整。'
      '實際長期持有報酬會高於本報表顯示的價格報酬。'
      '</div>'
    )}

    <div class="card">
        <div class="card-title">回測設定</div>
        {config_html}
    </div>

    <div class="card">
        <div class="card-title">關鍵指標</div>
        {kpi_html}
    </div>

    <div class="card">
        {charts['equity']}
    </div>

    <div class="card">
        {charts['drawdown']}
    </div>

    <div class="card">
        {charts['cost']}
    </div>

    <div class="card">
        <div class="card-title">每月選股（Top {TOP_N}）</div>
        <div style="max-height: 360px; overflow-y: auto;">
        <table>
            <thead><tr><th style="width:120px;">月份</th><th>選股</th></tr></thead>
            <tbody>{selected_rows}</tbody>
        </table>
        </div>
    </div>

    <div class="footer">
        資料來源：FinMind API · 策略：價值 40% / 動能 30% / 品質 30% · 月頻調倉
    </div>
</div>
</body>
</html>
"""
    return html


def save(result):
    """存 HTML + JSON。"""
    html = render_html(result)
    REPORT_FILE.write_text(html, encoding='utf-8')

    # JSON（方便之後程式讀取）
    payload = {
        'generated_at': datetime.now().isoformat(),
        'kpis': result.kpis,
        'selected_monthly': result.selected_monthly,
    }
    cs = result.cum_strategy.reset_index()
    cs.columns = ['date', 'nav']
    cb = result.cum_benchmark.reset_index()
    cb.columns = ['date', 'nav']
    payload['cum_strategy'] = cs.to_dict('records')
    payload['cum_benchmark'] = cb.to_dict('records')
    if result.cum_market_0050 is not None:
        cm = result.cum_market_0050.reset_index()
        cm.columns = ['date', 'nav']
        payload['cum_market_0050'] = cm.to_dict('records')

    RESULTS_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    print(f"📄 HTML 報告：{REPORT_FILE}")
    print(f"📦 JSON 結果：{RESULTS_JSON}")