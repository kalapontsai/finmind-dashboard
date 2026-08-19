"""
tests/test_csv_loader.py
- 測試 csv_loader 對各種格式的 (Ticker, Shares) CSV 容錯
"""
import sys
from pathlib import Path

import pytest

# 確保 lib/ 在 path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.csv_loader import (
    CSVLintError, Holding, list_profile_csvs, load_portfolio_csv,
)


def test_simple_two_columns():
    """無 header，兩欄乾淨數字"""
    csv = "2330,387\n6208,3713\n"
    h = load_portfolio_csv(csv)
    assert h == [Holding('2330', 387), Holding('6208', 3713)]


def test_with_header_english():
    csv = "Ticker,Shares\n2330,387\n6208,3713\n"
    h = load_portfolio_csv(csv)
    assert h == [Holding('2330', 387), Holding('6208', 3713)]


def test_with_header_chinese():
    csv = '代號,股數\n2330,387\n6208,"3,713"\n'
    h = load_portfolio_csv(csv)
    assert h == [Holding('2330', 387), Holding('6208', 3713)]


def test_thousands_separator_quoted():
    """使用者範例：shares 帶千分位"""
    csv = '''50,"21,315"
6208,"3,713"
2330,387
'''
    h = load_portfolio_csv(csv)
    assert h == [Holding('50', 21315), Holding('6208', 3713), Holding('2330', 387)]


def test_real_liyu_stock_fixture():
    """用 user_profile/liyu_stock.csv 跑一次（31 筆）"""
    f = ROOT / 'user_profile' / 'liyu_stock.csv'
    if not f.is_file():
        pytest.skip(f'{f} not found')
    h = load_portfolio_csv(f)
    assert len(h) == 31
    # 檢查第一筆
    assert h[0].ticker == '50'
    assert h[0].shares == 21315


def test_duplicate_ticker_sums():
    csv = "Ticker,Shares\n2330,100\n2330,250\n"
    h = load_portfolio_csv(csv)
    assert h == [Holding('2330', 350)]


def test_empty_file():
    with pytest.raises(CSVLintError):
        load_portfolio_csv('')


def test_only_header():
    with pytest.raises(CSVLintError):
        load_portfolio_csv('Ticker,Shares\n')


def test_missing_ticker_column():
    """純數字當 header 無 ticker 別名 → 視為無 header，要求兩欄"""
    with pytest.raises(CSVLintError):
        load_portfolio_csv('Foo,Bar\n2330,100\n')


def test_blank_rows_skipped():
    csv = "Ticker,Shares\n\n2330,100\n\n"
    h = load_portfolio_csv(csv)
    assert h == [Holding('2330', 100)]


def test_list_profile_csvs():
    """讀 user_profile/ 應該找得到 liyu_stock.csv"""
    profiles = list_profile_csvs(ROOT / 'user_profile')
    assert 'liyu_stock' in profiles
