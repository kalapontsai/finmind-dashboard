"""
tests/test_exporter.py
- 測試 HTML exporter 對假資料的輸出（含⑦ 滾動分布 SVG）
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.exporter import render_html_report


# ────────── 假 analyze 結果 ──────────
def _fake_analyze() -> dict:
    return {
        'inputs': {
            'tickers': ['2330', '2317'],
            'shares': {'2330': 387, '2317': 5000},
            'weights': None,
        },
        'common': {
            'mode': 'common',
            'metrics': {
                'start': '2010-01-04',
                'end': '2024-12-31',
                'years': 15.0,
                'total_return': 1.234,
                'cagr': 0.056,
                'mdd': -0.345,
                'volatility': 0.18,
                'sharpe': 0.42,
            },
        },
        'dynamic': {
            'mode': 'dynamic',
            'metrics': {
                'start': '2005-01-03',
                'end': '2024-12-31',
                'years': 20.0,
                'total_return': 2.5,
                'cagr': 0.067,
                'mdd': -0.40,
                'volatility': 0.20,
                'sharpe': 0.45,
            },
        },
        'full': {
            'mode': 'full',
            'metrics': {
                'start': '2000-01-04',
                'end': '2024-12-31',
                'years': 25.0,
                'total_return': 4.5,
                'cagr': 0.073,
                'mdd': -0.45,
                'volatility': 0.22,
                'sharpe': 0.48,
            },
        },
        'forecast': {
            'n': 10,
            'pv': 10_000_000,
            'rolling_count': 12,
            'r_count': 12,
            'percentiles': {
                'Bear': 0.02, 'Conservative': 0.05, 'Base': 0.08,
                'Optimistic': 0.12, 'Bull': 0.18,
            },
            'scenarios': [
                {'scenario': 'Bear (P10)', 'label': 'Bear', 'quantile': 0.10,
                 'cagr': 0.02, 'fv': 12_189_944, 'multiplier': 1.22},
                {'scenario': 'Conservative (P25)', 'label': 'Conservative', 'quantile': 0.25,
                 'cagr': 0.05, 'fv': 16_288_946, 'multiplier': 1.63},
                {'scenario': 'Base (P50)', 'label': 'Base', 'quantile': 0.50,
                 'cagr': 0.08, 'fv': 21_589_249, 'multiplier': 2.16},
                {'scenario': 'Optimistic (P75)', 'label': 'Optimistic', 'quantile': 0.75,
                 'cagr': 0.12, 'fv': 31_058_348, 'multiplier': 3.11},
                {'scenario': 'Bull (P90)', 'label': 'Bull', 'quantile': 0.90,
                 'cagr': 0.18, 'fv': 52_338_957, 'multiplier': 5.23},
            ],
            'rolling': [
                {'start': '2000-01-04', 'end': '2010-01-04', 'years': 10.0, 'cagr': 0.05},
                {'start': '2001-01-04', 'end': '2011-01-04', 'years': 10.0, 'cagr': 0.04},
                {'start': '2002-01-04', 'end': '2012-01-04', 'years': 10.0, 'cagr': 0.03},
                {'start': '2003-01-04', 'end': '2013-01-04', 'years': 10.0, 'cagr': 0.06},
                {'start': '2004-01-04', 'end': '2014-01-04', 'years': 10.0, 'cagr': 0.07},
                {'start': '2005-01-04', 'end': '2015-01-04', 'years': 10.0, 'cagr': 0.10},
                {'start': '2006-01-04', 'end': '2016-01-04', 'years': 10.0, 'cagr': 0.08},
                {'start': '2007-01-04', 'end': '2017-01-04', 'years': 10.0, 'cagr': 0.12},
                {'start': '2008-01-04', 'end': '2018-01-04', 'years': 10.0, 'cagr': 0.09},
                {'start': '2009-01-04', 'end': '2019-01-04', 'years': 10.0, 'cagr': 0.06},
                {'start': '2010-01-04', 'end': '2020-01-04', 'years': 10.0, 'cagr': 0.11},
                {'start': '2011-01-04', 'end': '2021-01-04', 'years': 10.0, 'cagr': 0.15},
            ],
        },
        'history': {
            'overview': {
                # 驗收標準 #6 新欄位
                'start': '2000-01-04',
                'end': '2024-12-31',
                'rows': 6000,
                'first_close': 50.0,
                'last_close': 600.0,
                # 舊欄位（compatibility）
                'stocks': 2,
                'min_years': 14.5,
                'median_years': 17.2,
                'max_years': 20.0,
            },
            'per_stock': {
                '2330': {
                    'years': 20.0, 'start': '2000-01-04', 'end': '2024-12-31',
                    'rows': 6000, 'first_close': 50.0, 'last_close': 600.0,
                },
                '2317': {
                    'years': 14.5, 'start': '2005-01-03', 'end': '2024-12-31',
                    'rows': 5000, 'first_close': 30.0, 'last_close': 200.0,
                },
            },
            'all_per_stock': {'2330': 20.0, '2317': 14.5},
        },
    }


def test_html_renders_without_error():
    html = render_html_report(_fake_analyze(), profile_name='liyu_stock')
    assert '<html' in html.lower() or '<!doctype' in html.lower()
    assert 'liyu_stock' in html
    assert 'Base' in html
    assert '10,000,000' in html or '10000000' in html


def test_html_includes_rolling_chart_svg():
    """⑦ 滾動 N 年收益分布圖（純 SVG）必須內嵌在 Section 三"""
    html = render_html_report(_fake_analyze(), profile_name='liyu_stock')
    assert '<svg' in html, 'HTML 報告應含 <svg> 圖（⑦ 滾動分布）'
    assert 'Bear P10' in html, '應標示 Bear P10 分位線'
    assert 'Bull P90' in html, '應標示 Bull P90 分位線'
    assert '<polyline' in html, '應有滾動 CAGR 主折線'


def test_html_section_two_hoisted_dates_when_same():
    """當三模式的 start/end 都相同,起訖日應提高至上一階（不重複出現在每個模式）"""
    fake = _fake_analyze()
    # 讓三模式共用同一組日期
    common_dates = {'start': '2010-01-04', 'end': '2024-12-31'}
    for m in ('common', 'dynamic', 'full'):
        fake[m]['metrics'].update(common_dates)
    html = render_html_report(fake, profile_name='liyu_stock')
    # 上方應有「共用起訖日」區塊
    assert '三模式共用' in html, '起訖日應提高至上一階顯示(三模式共用標記)'
    # 每個模式的 KPI 不應再重複列「開始日期」「結束日期」(因已 hoist)
    # 計算「開始日期」字串在 KPI grid 區塊出現次數 — 應只出現 1 次(在共用區塊)
    kpi_section = html.split('三、')[0]  # Section 三 之前的內容
    start_label_count = kpi_section.count('開始日期')
    end_label_count = kpi_section.count('結束日期')
    assert start_label_count == 1, f'「開始日期」應只出現 1 次(共用),實際 {start_label_count}'
    assert end_label_count == 1, f'「結束日期」應只出現 1 次(共用),實際 {end_label_count}'


def test_html_section_two_fallback_when_dates_differ():
    """當三模式日期不同,起訖日退回各模式 KPI 內顯示(向後相容)"""
    fake = _fake_analyze()
    # 三模式日期刻意不同(沿用 _fake_analyze 的預設差異)
    html = render_html_report(fake, profile_name='liyu_stock')
    kpi_section = html.split('三、')[0]
    # 三模式日期不同 → 開始日期應出現 3 次(每模式一次)
    start_label_count = kpi_section.count('開始日期')
    assert start_label_count >= 3, (
        f'日期不同時應退回各模式顯示,預期「開始日期」≥3 次,實際 {start_label_count}'
    )
