"""
HTML 報表生成器
- 用 plotly 產生互動圖
- 單一自包含 HTML 檔（含圖表 + 表格 + 設定）
- v1.4 P3-5：報表加時間流水號 (report_YYYYMMDD_HHMMSS.html) + 同時寫 report.html (latest)
- v1.4 P3-5：報表內容顯示「實際」跑過的參數（由 runner 傳入 cfg），不再讀 config.py 硬寫
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import MOMENTUM_LOOKBACK, OUTPUT_DIR, REPORT_FILE, RESULTS_JSON


def _fmt_pct(v: float, dec: int = 2) -> str:
    return f"{v * 100:.{dec}f}%"


def _fmt_num(v: float, dec: int = 2) -> str:
    return f"{v:,.{dec}f}"


def _clip_series(s: pd.Series, start: str | None, end: str | None) -> pd.Series:
    """v1.4 P3-7：按請求區間裁剪 series（cache 可能含比請求更廣的日期）。
    start/end 為 None 或 series 空 → 不裁剪。
    """
    if s is None or s.empty or not start or not end:
        return s
    try:
        s_ts = pd.Timestamp(start)
        e_ts = pd.Timestamp(end)
        # index 為 datetime 或 date 都吃
        idx = s.index
        mask = (idx >= s_ts) & (idx <= e_ts)
        return s[mask]
    except Exception:
        return s


def build_charts(result, start: str | None = None, end: str | None = None) -> dict:
    """回傳所有 plotly figure 的 HTML 字串。

    v1.4 P3-7：start / end 傳入時 → 裁剪所有 X 軸資料到 [start, end]。
    """
    close = result.close
    # v1.4 P3-7：裁剪 cum_* / monthly_* 到請求區間
    cum_strategy = _clip_series(result.cum_strategy, start, end)
    cum_benchmark = _clip_series(result.cum_benchmark, start, end)

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
        cum_market_0050 = _clip_series(result.cum_market_0050, start, end)
        fig_equity.add_trace(go.Scatter(
            x=cum_market_0050.index, y=cum_market_0050.values,
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
    monthly_cost = _clip_series(result.monthly_cost, start, end)
    fig_cost.add_trace(go.Bar(
        x=monthly_cost.index, y=monthly_cost.values * 100,
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


def _per_stock_returns(result, top_n: int = 10) -> tuple[str, list[dict]]:
    """
    v1.4 P3-6：Top 選股個別報酬表。

    計算邏輯：
    - 對 selected_monthly 中所有出現的個股，記錄「首次入選」與「最後出場」月份
    - 抓該期間 close 第一天 / 最後一天的價格（若在 rebalance 月份沒交易日，
      用最近的可得交易日）
    - 個別報酬 = (last_close / first_close) - 1
    - 依報酬降序排序，畫表格

    Returns:
        (html_string, rows_list) — rows 供除錯 / 之後擴充用
    """
    selected = getattr(result, 'selected_monthly', None) or {}
    close = getattr(result, 'close', None)

    if not selected or close is None or close.empty:
        return '<div style="color:var(--text-muted); font-size:12px;">（無選股紀錄或缺收盤價）</div>', []

    # 個股 → [list of months it was selected]
    stock_months: dict[str, list[str]] = {}
    for date_str, stocks in selected.items():
        for sid in stocks:
            stock_months.setdefault(sid, []).append(date_str)

    rows: list[dict] = []
    for sid, months in stock_months.items():
        if sid not in close.columns:
            continue
        first_month = min(months)
        last_month = max(months)
        # 抓 first / last 那天（或後一天）的收盤價
        price_series = close[sid].dropna()
        if price_series.empty:
            continue
        idx = price_series.index
        # first_month 是 '%Y-%m-%d' 字串；idx 是 datetime
        first_ts = pd.Timestamp(first_month)
        last_ts = pd.Timestamp(last_month)
        valid_first = idx[idx >= first_ts]
        valid_last = idx[idx <= last_ts]
        if len(valid_first) == 0 or len(valid_last) == 0:
            continue
        entry_price = float(price_series.loc[valid_first[0]])
        exit_price = float(price_series.loc[valid_last[-1]])
        if entry_price <= 0:
            continue
        ret = (exit_price / entry_price) - 1.0
        rows.append({
            'stock_id': sid,
            'first_month': first_month,
            'last_month': last_month,
            'hold_count': len(months),
            'entry_price': entry_price,
            'exit_price': exit_price,
            'return': ret,
        })

    rows.sort(key=lambda r: r['return'], reverse=True)
    # 只顯示 top_n + bottom_n，避免表格過長
    show_rows = rows[:max(top_n, 10)]
    if len(rows) > top_n * 2:
        show_rows = rows[:top_n] + [{'_sep': True, 'return': None}] + rows[-top_n:]

    if not show_rows:
        return '<div style="color:var(--text-muted); font-size:12px;">（無有效選股紀錄）</div>', []

    def _fmt(v): return '—' if v is None or (isinstance(v, float) and (v != v)) else v
    def _ret_cls(v): return '' if v is None else ('pos' if v >= 0 else 'neg')

    body_rows = []
    for r in show_rows:
        if r.get('_sep'):
            body_rows.append('<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:4px;">⋯ 中間略 ⋯</td></tr>')
            continue
        body_rows.append(
            f'<tr>'
            f'<td><strong>{_fmt(r["stock_id"])}</strong></td>'
            f'<td>{_fmt(r["first_month"])} → {_fmt(r["last_month"])}</td>'
            f'<td style="text-align:right;">{r["hold_count"]}</td>'
            f'<td style="text-align:right;">{_fmt(r["entry_price"]):.2f}</td>'
            f'<td style="text-align:right;">{_fmt(r["exit_price"]):.2f}</td>'
            f'<td class="{_ret_cls(r["return"])}" style="text-align:right; font-weight:600;">{_fmt(r["return"])*100:+.2f}%</td>'
            f'</tr>'
        )

    html = (
        '<div style="max-height:420px; overflow-y:auto;">'
        '<table>'
        '<thead><tr>'
        '<th>代碼</th><th>期間</th><th style="text-align:right;">持有月數</th>'
        '<th style="text-align:right;">進場價</th><th style="text-align:right;">出場價</th>'
        '<th style="text-align:right;">個別報酬</th>'
        '</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody>'
        '</table>'
        f'<div style="margin-top:8px; font-size:11px; color:var(--text-muted);">總計 {len(rows)} 檔被選過；'
        f'表中顯示前 {min(top_n, len(rows))} 名 + 後 {min(top_n, max(0, len(rows)-top_n))} 名（依個別報酬排序）</div>'
        '</div>'
    )
    return html, rows


def render_html(result, cfg: dict | None = None) -> str:
    """
    組 HTML 字串。

    v1.4 P3-5：cfg 是 merge_config 後的「實際」配置。
    - 若不傳 → fallback 讀 config.py（向後相容）
    - 顯示的區間 / Top N / 股票池大小 / 費率 都以 cfg 為準
    """
    # ── 取實際值（cfg 優先，否則 fallback config.py / load_pool）──
    from config import (
        COMMISSION, END_DATE, SLIPPAGE, START_DATE, STOCK_POOL, TAX, TOP_N, WEIGHTS,
    )
    actual_start = (cfg or {}).get('start') or START_DATE
    actual_end = (cfg or {}).get('end') or END_DATE
    actual_top_n = int((cfg or {}).get('top_n') or TOP_N)
    # v1.4 P3-7：build_charts / selected_monthly / close 都按請求區間裁剪
    charts = build_charts(result, start=actual_start, end=actual_end)
    k = result.kpis
    # v1.4 P3-6：pool 從 cfg 或動態 load_pool() 來；不再 fallback STOCK_POOL (26 檔硬寫)
    cfg_pool = (cfg or {}).get('pool')
    if isinstance(cfg_pool, list) and cfg_pool:
        actual_pool = cfg_pool
    else:
        try:
            from lib.pool_loader import load_pool
            actual_pool = load_pool()
        except Exception:
            actual_pool = STOCK_POOL  # 終極 fallback（不該走到這）
    actual_pool_size = len(actual_pool) if isinstance(actual_pool, list) else 0

    # v1.4 P3-7：selected_monthly 按請求區間過濾，避免 X 軸拉到 2016 的舊資料
    raw_selected = getattr(result, 'selected_monthly', None) or {}
    s_ts = pd.Timestamp(actual_start) if actual_start else None
    e_ts = pd.Timestamp(actual_end) if actual_end else None
    if s_ts or e_ts:
        s_str = s_ts.strftime('%Y-%m-%d') if s_ts else None
        e_str = e_ts.strftime('%Y-%m-%d') if e_ts else None
        clipped_selected = {
            k_: v for k_, v in raw_selected.items()
            if (not s_str or k_ >= s_str) and (not e_str or k_ <= e_str)
        }
    else:
        clipped_selected = raw_selected

    # v1.4 P3-6 + P3-7：Top N 選股個別報酬表（用 clipped selected + clipped close）
    # 讓 _per_stock_returns 計算的「首次入選 → 最後出場」不會落到請求區間外
    if clipped_selected is not raw_selected:
        # 構造一個 lightweight wrapper 給 _per_stock_returns 用
        class _ResultProxy:
            pass
        _proxy = _ResultProxy()
        _proxy.selected_monthly = clipped_selected
        _proxy.close = _clip_series(getattr(result, 'close', None), actual_start, actual_end)
        per_stock_table_html, _per_stock_rows = _per_stock_returns(_proxy, top_n=actual_top_n)
    else:
        per_stock_table_html, _per_stock_rows = _per_stock_returns(result, top_n=actual_top_n)
    actual_fee_buy = float((cfg or {}).get('fee_buy') if (cfg or {}).get('fee_buy') is not None else COMMISSION)
    actual_fee_sell = float((cfg or {}).get('fee_sell') if (cfg or {}).get('fee_sell') is not None else COMMISSION)
    actual_tax_sell = float((cfg or {}).get('tax_sell') if (cfg or {}).get('tax_sell') is not None else TAX)
    actual_slippage = float((cfg or {}).get('slippage') if (cfg or {}).get('slippage') is not None else SLIPPAGE)
    actual_min_liq = int((cfg or {}).get('min_liquidity_shares') or 0)
    actual_rebalance = (cfg or {}).get('rebalance_freq') or 'monthly'
    actual_weights = {s['name']: s.get('weight', 0) for s in (cfg or {}).get('strategies', []) if s.get('enabled', True)} \
        if (cfg or {}).get('strategies') else WEIGHTS
    wf_enabled = (cfg or {}).get('walk_forward', False)

    selected_rows = ''
    for date_str in sorted(clipped_selected.keys()):
        stocks = clipped_selected[date_str]
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

    # 因子權重字串（用實際）
    w_value = actual_weights.get('value', 0)
    w_momentum = actual_weights.get('momentum', 0)
    w_quality = actual_weights.get('quality', 0)
    weight_str = f'價值 {w_value:.0%} / 動能 {w_momentum:.0%} / 品質 {w_quality:.0%}'

    config_html = f"""
    <div class="config">
        <div class="row"><span class="lbl">回測區間</span><span>{actual_start} ~ {actual_end}</span></div>
        <div class="row"><span class="lbl">股票池</span><span>{actual_pool_size} 檔</span></div>
        <div class="row"><span class="lbl">Top N</span><span>{actual_top_n} 檔（等權 {1/actual_top_n:.0%}）</span></div>
        <div class="row"><span class="lbl">換倉頻率</span><span>{actual_rebalance}</span></div>
        <div class="row"><span class="lbl">動能回看</span><span>{MOMENTUM_LOOKBACK} 日</span></div>
        <div class="row"><span class="lbl">因子權重</span><span>{weight_str}</span></div>
        <div class="row"><span class="lbl">費率</span><span>買 {actual_fee_buy:.4%} / 賣 {actual_fee_sell:.4%}+{actual_tax_sell:.3%} / 滑價 {actual_slippage:.3%}</span></div>
        <div class="row"><span class="lbl">最低 20 日均量</span><span>{actual_min_liq} 張</span></div>
        <div class="row"><span class="lbl">除權息調整</span><span>{getattr(result, 'adjust_method', 'none')}</span></div>
        <div class="row"><span class="lbl">交易日</span><span>{k['trading_days']}</span></div>
        {('<div class="row"><span class="lbl">🔬 Walk-forward</span>'
          '<span>訓練 {train_pct:.0%} / 驗證 {val_pct:.0%}（切點 {split_date}）</span></div>').format(
              train_pct=k.get('train_pct', 0.7),
              val_pct=1 - k.get('train_pct', 0.7),
              split_date=k.get('walk_forward_split_date', '—'),
          ) if wf_enabled or k.get('walk_forward_enabled') else ''}
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
        <div class="card-title">每月選股（Top {actual_top_n}）</div>
        <div style="max-height: 360px; overflow-y: auto;">
        <table>
            <thead><tr><th style="width:120px;">月份</th><th>選股</th></tr></thead>
            <tbody>{selected_rows}</tbody>
        </table>
        </div>
    </div>

    <div class="card">
        <div class="card-title">Top {actual_top_n} 選股個別報酬（v1.4 P3-6 新增）</div>
        <div style="color:var(--text-muted); font-size:12px; margin-bottom:8px;">
            統計所有月份被選入 Top N 的個股，計算其在「首次入選」到「最後出場」期間的個別報酬。
            注意：實際投組是月頻換倉，個別持股不一定跨月被持有；這裡是「純選股能力」的概略指標。
        </div>
        {per_stock_table_html}
    </div>

    <div class="footer">
        資料來源：FinMind API · 策略：價值 40% / 動能 30% / 品質 30% · 月頻調倉
    </div>
</div>
</body>
</html>
"""
    return html


def _ts_filename(prefix: str = 'report', ext: str = 'html') -> str:
    """
    v1.4 P3-5：時間流水號檔名
    範例：report_20260815_094823.html
    """
    return f'{prefix}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.{ext}'


def save(result, cfg: dict | None = None) -> dict:
    """
    存 HTML + JSON（v1.4 P3-5 加時間流水號）。

    寫入策略：
    - HTML 寫入兩份：
        * report_YYYYMMDD_HHMMSS.html（時間序，保留歷史）
        * report.html（latest，供 iframe / 舊 API 讀）
    - JSON 寫入兩份：
        * backtest_results_YYYYMMDD_HHMMSS.json（時間序）
        * backtest_results.json（latest）

    Returns:
        dict: { html_latest, html_archive, json_latest, json_archive }
    """
    html = render_html(result, cfg)

    html_archive_name = _ts_filename('report', 'html')
    json_archive_name = _ts_filename('backtest_results', 'json')

    html_archive = OUTPUT_DIR / html_archive_name
    json_archive = OUTPUT_DIR / json_archive_name

    html_archive.write_text(html, encoding='utf-8')
    REPORT_FILE.write_text(html, encoding='utf-8')

    # JSON（方便之後程式讀取）
    payload = {
        'generated_at': datetime.now().isoformat(),
        'archive_html': html_archive_name,
        'cfg': cfg or {},   # v1.4 P3-5：把實際跑的 cfg 寫進 JSON，方便後續 audit
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

    json_text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    json_archive.write_text(json_text, encoding='utf-8')
    RESULTS_JSON.write_text(json_text, encoding='utf-8')

    print(f"📄 HTML 報告 (latest):  {REPORT_FILE}")
    print(f"📄 HTML 報告 (archive): {html_archive}")
    print(f"📦 JSON 結果 (latest):  {RESULTS_JSON}")
    print(f"📦 JSON 結果 (archive): {json_archive}")

    return {
        'html_latest': REPORT_FILE.name,
        'html_archive': html_archive_name,
        'json_latest': RESULTS_JSON.name,
        'json_archive': json_archive_name,
    }


def list_recent_reports(limit: int = 10) -> list[dict]:
    """
    v1.4 P3-5：列出 output/ 內最近的時間序報告
    Returns:
        [{ name, mtime, size_kb }, ...]（新到舊）
    """
    if not OUTPUT_DIR.is_dir():
        return []
    items = []
    for p in OUTPUT_DIR.glob('report_*.html'):
        try:
            st = p.stat()
            items.append({
                'name': p.name,
                'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'size_kb': round(st.st_size / 1024, 1),
            })
        except OSError:
            continue
    items.sort(key=lambda x: x['mtime'], reverse=True)
    return items[:limit]