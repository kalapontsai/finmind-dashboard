"""
v1.4 P3-5 + P3-6 regression tests

涵蓋：
- pool_loader.save_pool / sync_pool_json / load_pool
- runner 寫回 cfg['pool'] 與 bt.selected_monthly
- /api/quant_pool 不再 fallback 26 檔
- report.py 用實際 cfg（不再吃 STOCK_POOL 26 檔）
- _per_stock_returns 表格 HTML 正常產出
- watchlist MAX_ITEMS >= 100（pool 已 100 檔）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 確保 lib / quant 可 import
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.pool_loader import load_pool, save_pool, sync_pool_json, POOL_FILE, POOL_JSON  # noqa: E402


# ────────────────────────── pool_loader ──────────────────────────

def test_pool_loader_save_and_reload(tmp_path):
    """save_pool 把 list 寫成 JSON；load_pool 讀得回來"""
    src = tmp_path / 'pool.txt'
    src.write_text('2330,2317\n2454\n', encoding='utf-8')
    dst = tmp_path / 'pool.json'

    # 用 path=src 強制定向讀這個檔
    pool = []
    from lib.pool_loader import _load_from_text_file
    pool = _load_from_text_file(src)
    assert pool == ['2330', '2317', '2454']

    # save_pool 寫到 tmp dst
    out = save_pool(pool, pool_file=src, json_file=dst)
    assert out == dst
    data = json.loads(dst.read_text(encoding='utf-8'))
    # save_pool 會去重 + 排序
    assert data == ['2317', '2330', '2454']


def test_sync_pool_json_roundtrip():
    """sync_pool_json：預設路徑 sync pool.txt → pool.json；不丟失股票"""
    pool = load_pool()
    sync_pool_json()  # 冪等
    assert POOL_JSON.is_file(), 'pool.json 必須存在'
    data = json.loads(POOL_JSON.read_text(encoding='utf-8'))
    assert sorted(data) == sorted(pool), f'sync 後 pool.json 與 pool.txt 內容不一致'
    # 不應為空
    assert len(data) >= 1, 'pool.json 至少要有 1 檔'


def test_load_pool_prefers_json_when_fresh():
    """load_pool() 預設行為：pool.json 存在且比 pool.txt 新 → 讀 pool.json"""
    pool = load_pool()
    assert isinstance(pool, list)
    assert len(pool) >= 50, f'pool 應至少 50 檔，實際 {len(pool)}'


def test_load_pool_syncs_when_txt_newer(monkeypatch, tmp_path):
    """若 pool.txt 比 pool.json 新 → 讀 pool.txt 並 regenerate pool.json"""
    # 用 tmp_path 模擬
    monkeypatch.setattr('lib.pool_loader.POOL_FILE', tmp_path / 'pool.txt')
    monkeypatch.setattr('lib.pool_loader.POOL_JSON', tmp_path / 'pool.json')
    tmp_path.joinpath('pool.txt').write_text('9999,8888\n7777\n', encoding='utf-8')
    tmp_path.joinpath('pool.json').write_text('["0000"]', encoding='utf-8')

    # pool.json mtime 比 pool.txt 早 → 應該讀 pool.txt 並覆寫 pool.json
    import os, time
    old = time.time() - 3600
    os.utime(tmp_path / 'pool.json', (old, old))

    pool = load_pool()
    assert pool == ['9999', '8888', '7777']
    # 同步生效
    data = json.loads(tmp_path.joinpath('pool.json').read_text(encoding='utf-8'))
    assert sorted(data) == ['7777', '8888', '9999']


# ────────────────────────── quant_runner cfg 寫回 ──────────────────────────

def test_runner_writes_cfg_pool_and_selected():
    """runner.run_and_save() 必須把實際 pool 寫回 cfg['pool']；
    且必須把 build_position 的 selected 寫進 bt.selected_monthly。
    """
    from quant.runner import merge_config, run_and_save

    cfg_in = merge_config({
        'pool': ['2317', '2454'],   # 兩者 cache 都覆蓋 2025-01-01 ~ 2025-12-31
        'strategies': [
            {'name': 'value', 'enabled': True, 'weight': 0.5},
            {'name': 'momentum', 'enabled': True, 'weight': 0.5},
        ],
        'start': '2025-01-01',
        'end': '2025-12-31',
        'top_n': 2,
        'rebalance_freq': 'monthly',
        'fee_buy': 0.001425, 'fee_sell': 0.001425,
        'tax_sell': 0.003, 'slippage': 0.001,
    })

    # 跑回測
    result, _save_meta = run_and_save(cfg_in)

    # 確認 cfg['pool'] 寫回（實際是 merge 進去的 pool）
    assert cfg_in['pool'] == ['2317', '2454']
    # 確認 selected_monthly 不是空 dict
    assert isinstance(result.selected_monthly, dict), \
        f'selected_monthly 必須是 dict，got {type(result.selected_monthly)}'
    assert len(result.selected_monthly) > 0, \
        'selected_monthly 不可為空（否則 report 沒 top N 表）'


# ────────────────────────── report.py 用實際 cfg ──────────────────────────

def test_report_uses_actual_pool_not_stock_pool_fallback():
    """report.render_html 用 cfg['pool']，不用 STOCK_POOL 26 檔 fallback"""
    import pandas as pd
    from quant.report import render_html
    # 構造假的 BacktestResult-like 物件
    class _FakeResult:
        kpis = {
            'trading_days': 200, 'total_return': 0.1,
            'pool_benchmark_return': 0.05, 'pool_excess_return': 0.05,
            'mdd': -0.1, 'sharpe': 0.5, 'rebalance_count': 5,
        }
        # 用 pandas Series 確保有 .index
        dates = pd.date_range('2024-01-01', periods=3, freq='D')
        cum_strategy = pd.Series([1.0, 1.01, 1.02], index=dates, name='nav')
        cum_benchmark = pd.Series([1.0, 1.005, 1.01], index=dates, name='nav')
        cum_market_0050 = None
        selected_monthly = {'2024-01-01': ['9999']}
        monthly_cost = pd.Series([0.001] * 3, index=dates)
        monthly_turnover = pd.Series([0.1] * 3, index=dates)
        include_dividends = False
        adjust_method = 'none'
        walk_forward_split_date = None
        close = None  # _per_stock_returns 會顯示「無選股紀錄或缺收盤價」

    result = _FakeResult()
    cfg = {'pool': ['9999', '8888', '7777'], 'top_n': 3, 'start': '2024-01-01', 'end': '2024-12-31'}

    html = render_html(result, cfg)
    # 報告應該寫出實際 pool 大小（3），不是 STOCK_POOL fallback（26）
    assert '3 檔' in html, f'報告應顯示實際 pool 大小 3 檔'
    # 不應該出現 26 檔（除非 STOCK_POOL fallback 又被觸發）
    assert '>26 檔<' not in html, f'報告不該 fallback 26 檔'


# ────────────────────────── _per_stock_returns HTML ──────────────────────────

def test_per_stock_returns_with_close_data():
    """_per_stock_returns 給 close DataFrame → 產出 table HTML"""
    import pandas as pd
    from quant.report import _per_stock_returns

    dates = pd.date_range('2024-01-01', periods=10, freq='D')
    close_df = pd.DataFrame({
        '2330': [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0],
        '2317': [50.0, 51.0, 52.0, 53.0, 54.0, 55.0, 56.0, 57.0, 58.0, 59.0],
    }, index=dates)

    class _R:
        selected_monthly = {
            '2024-01-01': ['2330', '2317'],
            '2024-01-05': ['2330'],
        }
        close = close_df

    html, rows = _per_stock_returns(_R(), top_n=3)
    assert '2330' in html
    assert '2317' in html
    # 2330: 100 (2024-01-01) → 104 (2024-01-05) = +4.00%
    # 2317: 只在 2024-01-01 選 → entry=exit=50 → +0.00%
    assert '+4.00%' in html, f'2330 應 +4.00%，html snippet: {html[html.find("2330"):html.find("2330")+200]}'
    assert '+0.00%' in html
    assert len(rows) == 2


def test_per_stock_returns_empty_when_no_selected():
    """沒 selected_monthly 時不會 crash"""
    from quant.report import _per_stock_returns
    class _R:
        selected_monthly = {}
        close = None
    html, rows = _per_stock_returns(_R(), top_n=3)
    assert '無' in html
    assert rows == []


# ────────────────────────── /api/quant_pool 不再 fallback 26 檔 ──────────────────────────

def test_api_quant_pool_no_26_fallback(monkeypatch):
    """/api/quant_pool 不該回傳 26 檔 STOCK_POOL fallback。
    真值 = pool.json 100 檔。
    """
    from routes.api import quant_pool
    # flask request context
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context('/api/quant_pool'):
        resp = quant_pool()
        data = resp.get_json()
    assert 'stocks' in data
    assert 'count' in data
    # 預設 100 檔（pool.json）
    assert data['count'] >= 50, f'預期 ≥ 50 檔，got {data["count"]}'
    assert data['count'] != 26, f'不該 fallback 26 檔 STOCK_POOL，got {data["count"]}'


# ────────────────────────── P3-7：日期裁剪 ──────────────────────────

def test_clip_series_to_range():
    """_clip_series 按 start/end 裁剪 series；start/end 為 None 時不裁剪"""
    import pandas as pd
    from quant.report import _clip_series

    dates = pd.date_range('2024-01-01', '2024-12-31', freq='D')
    s = pd.Series([1.0] * len(dates), index=dates)

    # 裁剪
    clipped = _clip_series(s, '2024-06-01', '2024-06-30')
    assert clipped.index[0] == pd.Timestamp('2024-06-01')
    assert clipped.index[-1] == pd.Timestamp('2024-06-30')
    assert len(clipped) == 30

    # 不裁剪（None）
    not_clipped = _clip_series(s, None, None)
    assert len(not_clipped) == len(s)

    # 空 series
    empty = _clip_series(pd.Series([], dtype=float), '2024-06-01', '2024-06-30')
    assert len(empty) == 0


def test_build_charts_clips_x_axis():
    """build_charts() 傳入 start/end → cum_strategy 等 X 軸資料被裁剪"""
    import pandas as pd
    from quant.report import build_charts

    # 模擬一個 BacktestResult，含跨區間資料
    wide_dates = pd.date_range('2020-01-01', '2024-12-31', freq='D')
    class _R:
        close = pd.DataFrame({f's{i}': [1.0]*len(wide_dates) for i in range(3)}, index=wide_dates)
        cum_strategy = pd.Series([1.0] * len(wide_dates), index=wide_dates)
        cum_benchmark = pd.Series([1.0] * len(wide_dates), index=wide_dates)
        cum_market_0050 = None
        monthly_cost = pd.Series([0.001] * len(wide_dates), index=wide_dates)

    result = _R()

    # 沒傳 start/end → 不裁剪
    charts_full = build_charts(result)
    # 裁剪到 2022-2023
    charts_clipped = build_charts(result, start='2022-01-01', end='2023-12-31')

    # 驗證 HTML 中沒有 2020/2024 的 date 出現
    assert '2020-01-01' in charts_full['equity'] or '2020-01-02' in charts_full['equity']
    assert '2020-01-01' not in charts_clipped['equity']
    assert '2024-12-31' not in charts_clipped['equity']


def test_report_clips_selected_monthly_and_per_stock():
    """render_html() → selected_monthly 與 per-stock 表的期間都被裁剪到 cfg 範圍"""
    import pandas as pd
    from quant.report import render_html

    dates = pd.date_range('2020-01-01', '2024-12-31', freq='MS')  # 月初
    selected = {d.strftime('%Y-%m-%d'): ['2330'] for d in dates}

    class _R:
        kpis = {
            'trading_days': 100, 'total_return': 0.1,
            'pool_benchmark_return': 0.05, 'pool_excess_return': 0.05,
            'mdd': -0.1, 'sharpe': 0.5, 'rebalance_count': 10,
        }
        cum_strategy = pd.Series([1.0] * len(dates), index=dates)
        cum_benchmark = pd.Series([1.0] * len(dates), index=dates)
        cum_market_0050 = None
        selected_monthly = selected
        monthly_cost = pd.Series([0.001] * len(dates), index=dates)
        monthly_turnover = pd.Series([0.1] * len(dates), index=dates)
        include_dividends = False
        adjust_method = 'none'
        walk_forward_split_date = None
        # close 給 per-stock 用
        full_dates = pd.date_range('2020-01-01', '2024-12-31', freq='D')
        close = pd.DataFrame({'2330': [100.0] * len(full_dates)}, index=full_dates)

    result = _R()
    cfg = {
        'pool': ['2330'], 'top_n': 1,
        'start': '2022-01-01', 'end': '2023-12-31',
        'strategies': [{'name': 'value', 'enabled': True, 'weight': 1.0}],
    }

    html = render_html(result, cfg)
    # 應該看不到 2020 / 2024 月份
    assert '2020-' not in html, 'selected_monthly / per-stock 表不應含 2020 年月份'
    assert '2024-' not in html, 'selected_monthly / per-stock 表不應含 2024 年月份'
    # 應該看到 2022 / 2023 月份
    assert '2022-' in html or '2023-' in html