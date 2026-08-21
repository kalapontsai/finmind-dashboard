"""
tests/test_exporter.py
- 測試 HTML / PDF exporter 對假資料的輸出
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.exporter import render_html_report, render_pdf_report


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


def test_pdf_writes_file(tmp_path):
    out = tmp_path / 'report.pdf'
    p = render_pdf_report(_fake_analyze(), out, profile_name='liyu_stock')
    assert p == out
    assert p.is_file()
    assert p.stat().st_size > 1000  # PDF 至少要 1KB
    # PDF 開頭應該是 %PDF
    with open(p, 'rb') as f:
        head = f.read(8)
    assert head.startswith(b'%PDF-')
