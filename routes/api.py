"""
REST API 路由
- /api/stock_list          GET  個股清單 + 搜尋
- /api/stock_price         GET  歷史股價
- /api/stock_per           GET  PER / PBR / 殖利率
- /api/stock_revenue       GET  月營收（含 YoY）
- /api/stock_finance       GET  三大財報
- /api/stock_dividend      GET  配息（年份彙總）
- /api/institutional       GET  三大法人買賣超
- /api/margin              GET  融資融券
- /api/backtest            POST 策略回測
- /api/quant_run           POST 量化回測
- /api/quant_status        GET  量化狀態
- /api/quant_pool          GET  量化股票池
- /api/health              GET  健康檢查
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, jsonify, request

from app_config import (
    BACKTEST_RESULTS_FILE,
    FINMIND_TOKEN,
    QUANT_DIR,
    STOCK_LIST_CACHE_FILE,
)
from lib import finmind as fm
from lib.backtest import run_backtest, save_backtest_summary
from lib.finmind import FinMindClient, FinMindError
from lib.quant_runner import get_status, run_quant, run_quant_async
from lib.strategy_store import list_strategies
from lib.user_strategy_config import load as load_user_strategy_config, save as save_user_strategy_config

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ────────────────────────── 工具 ──────────────────────────
def _err(msg: str, code: int = 400, **extra):
    payload = {'error': msg}
    payload.update(extra)
    resp = jsonify(payload)
    resp.status_code = code
    return resp


def _require_token():
    if not FINMIND_TOKEN:
        return _err('FINMIND_TOKEN not configured', 500)
    return None


# ────────────────────────── 個股清單 / 搜尋 ──────────────────────────
@api_bp.get('/stock_list')
def stock_list():
    err = _require_token()
    if err:
        return err
    q = (request.args.get('q') or '').strip()
    limit = max(1, min(200, int(request.args.get('limit', 50))))

    try:
        client = FinMindClient()
        if q:
            results = client.search_stock(q, limit)
        else:
            results = client.get_stock_list()[:limit]
        return jsonify({'count': len(results), 'stocks': results})
    except FinMindError as e:
        return _err(str(e), 502)


# ────────────────────────── 個股股價 ──────────────────────────
@api_bp.get('/stock_price')
def stock_price():
    err = _require_token()
    if err:
        return err
    stock_id = (request.args.get('stock_id') or '').strip()
    start = (request.args.get('start_date') or '').strip()
    end = (request.args.get('end_date') or '').strip()
    if not stock_id:
        return _err('stock_id required')
    if not start:
        return _err('start_date required')
    if not end:
        return _err('end_date required')

    try:
        client = FinMindClient()
        rows = client.query('TaiwanStockPrice', {
            'data_id': stock_id,
            'start_date': start,
            'end_date': end,
        })
        return jsonify({'stock_id': stock_id, 'count': len(rows), 'prices': rows})
    except FinMindError as e:
        return _err(str(e), 502)


# ────────────────────────── PER / PBR / 殖利率 ──────────────────────────
@api_bp.get('/stock_per')
def stock_per():
    err = _require_token()
    if err:
        return err
    stock_id = (request.args.get('stock_id') or '').strip()
    if not stock_id:
        return _err('stock_id required')

    end = (request.args.get('end_date') or datetime.now().strftime('%Y-%m-%d'))
    start = (request.args.get('start_date') or
             (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'))
    try:
        client = FinMindClient()
        rows = client.query('TaiwanStockPER', {
            'data_id': stock_id,
            'start_date': start,
            'end_date': end,
        })
        return jsonify({'stock_id': stock_id, 'count': len(rows), 'rows': rows})
    except FinMindError as e:
        return _err(str(e), 502)


# ────────────────────────── 月營收 ──────────────────────────
@api_bp.get('/stock_revenue')
def stock_revenue():
    err = _require_token()
    if err:
        return err
    stock_id = (request.args.get('stock_id') or '').strip()
    if not stock_id:
        return _err('stock_id required')

    end = (request.args.get('end_date') or datetime.now().strftime('%Y-%m-%d'))
    start = (request.args.get('start_date') or
             (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d'))
    try:
        client = FinMindClient()
        rows = client.query('TaiwanStockMonthRevenue', {
            'data_id': stock_id,
            'start_date': start,
            'end_date': end,
        })

        # 加 YoY 計算
        by_month = {}
        for r in rows:
            key = r['date'][:7]
            by_month[key] = r
        month_keys = sorted(by_month.keys())
        enriched = []
        for i, key in enumerate(month_keys):
            cur = by_month[key]
            yoy = None
            if i >= 12:
                prev = by_month[month_keys[i - 12]]
                if prev.get('revenue', 0) > 0:
                    yoy = round((cur['revenue'] - prev['revenue']) / prev['revenue'] * 100, 2)
            enriched.append({
                'date': cur['date'],
                'revenue': cur['revenue'],
                'revenue_year': cur.get('revenue_year'),
                'revenue_month': cur.get('revenue_month'),
                'YoY': yoy,
            })

        return jsonify({'stock_id': stock_id, 'count': len(enriched), 'rows': enriched})
    except FinMindError as e:
        return _err(str(e), 502)


# ────────────────────────── 三大財報 ──────────────────────────
@api_bp.get('/stock_finance')
def stock_finance():
    err = _require_token()
    if err:
        return err
    stock_id = (request.args.get('stock_id') or '').strip()
    if not stock_id:
        return _err('stock_id required')

    end = (request.args.get('end_date') or datetime.now().strftime('%Y-%m-%d'))
    start = (request.args.get('start_date') or
             (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d'))
    try:
        client = FinMindClient()
        rows = client.query('TaiwanStockFinancialStatements', {
            'data_id': stock_id,
            'start_date': start,
            'end_date': end,
        })
        return jsonify({'stock_id': stock_id, 'count': len(rows), 'rows': rows})
    except FinMindError as e:
        return _err(str(e), 502)


# ────────────────────────── 配息 ──────────────────────────
@api_bp.get('/stock_dividend')
def stock_dividend():
    err = _require_token()
    if err:
        return err
    stock_id = (request.args.get('stock_id') or '').strip()
    if not stock_id:
        return _err('stock_id required')

    end = (request.args.get('end_date') or datetime.now().strftime('%Y-%m-%d'))
    start = (request.args.get('start_date') or
             (datetime.now() - timedelta(days=1825)).strftime('%Y-%m-%d'))
    try:
        client = FinMindClient()
        rows = client.query('TaiwanStockDividend', {
            'data_id': stock_id,
            'start_date': start,
            'end_date': end,
        })

        # 依年份彙總
        by_year = {}
        for r in rows:
            d = r.get('date', '')
            year = d[:4]
            if not year or year == '0000':
                continue
            if year not in by_year:
                by_year[year] = {
                    'year': year,
                    'cash_dividend': 0,
                    'stock_dividend': 0,
                    'events': [],
                }
            cash = (float(r.get('CashEarningsDistribution') or 0)
                    + float(r.get('CashStatutorySurplus') or 0))
            stock = (float(r.get('StockEarningsDistribution') or 0)
                     + float(r.get('StockStatutorySurplus') or 0))
            by_year[year]['cash_dividend'] += cash
            by_year[year]['stock_dividend'] += stock
            by_year[year]['events'].append({
                'date': d,
                'cash': cash,
                'stock': stock,
                'announce': r.get('AnnouncementDate', ''),
            })

        years = sorted(by_year.values(), key=lambda y: int(y['year']), reverse=True)
        return jsonify({'stock_id': stock_id, 'count': len(years), 'rows': years})
    except FinMindError as e:
        return _err(str(e), 502)


# ────────────────────────── 三大法人 ──────────────────────────
@api_bp.get('/institutional')
def institutional():
    err = _require_token()
    if err:
        return err
    stock_id = (request.args.get('stock_id') or '').strip()
    if not stock_id:
        return _err('stock_id required')

    end = (request.args.get('end_date') or datetime.now().strftime('%Y-%m-%d'))
    start = (request.args.get('start_date') or
             (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d'))
    try:
        client = FinMindClient()
        rows = client.query('TaiwanStockInstitutionalInvestorsBuySell', {
            'data_id': stock_id,
            'start_date': start,
            'end_date': end,
        })

        # 依日期彙總
        by_date = {}
        for r in rows:
            d = r['date']
            if d not in by_date:
                by_date[d] = {
                    'date': d,
                    'foreign': 0,
                    'trust': 0,
                    'dealer': 0,
                    'total': 0,
                    'foreign_buy': 0,
                    'foreign_sell': 0,
                }
            name = r.get('name', '')
            buy = int(r.get('buy') or 0)
            sell = int(r.get('sell') or 0)
            net = buy - sell
            if name == 'Foreign_Investor':
                by_date[d]['foreign'] += net
                by_date[d]['foreign_buy'] += buy
                by_date[d]['foreign_sell'] += sell
            elif name == 'Investment_Trust':
                by_date[d]['trust'] += net
            elif name == 'Dealer':
                by_date[d]['dealer'] += net
            by_date[d]['total'] += net

        result = sorted(by_date.values(), key=lambda x: x['date'])
        return jsonify({'stock_id': stock_id, 'count': len(result), 'rows': result})
    except FinMindError as e:
        return _err(str(e), 502)


# ────────────────────────── 融資融券 ──────────────────────────
@api_bp.get('/margin')
def margin():
    err = _require_token()
    if err:
        return err
    stock_id = (request.args.get('stock_id') or '').strip()
    if not stock_id:
        return _err('stock_id required')

    end = (request.args.get('end_date') or datetime.now().strftime('%Y-%m-%d'))
    start = (request.args.get('start_date') or
             (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d'))
    try:
        client = FinMindClient()
        rows = client.query('TaiwanStockMarginPurchaseShortSale', {
            'data_id': stock_id,
            'start_date': start,
            'end_date': end,
        })
        return jsonify({'stock_id': stock_id, 'count': len(rows), 'rows': rows})
    except FinMindError as e:
        return _err(str(e), 502)


# ────────────────────────── 策略回測 ──────────────────────────
@api_bp.post('/backtest')
def backtest():
    err = _require_token()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    stock_id = (body.get('stock_id') or '').strip()
    start = (body.get('start_date') or '').strip()
    end = (body.get('end_date') or '').strip()
    capital = float(body.get('capital', 1000000))
    strategies = body.get('strategies') or {}
    combine_mode = body.get('combine_mode', 'OR')
    frequency = body.get('frequency', 'day')
    month_day = int(body.get('month_day', 15))

    # 補預設值（避免 users 沒給 select 沒啟用策略的欄位）
    strategies.setdefault('ma', {'enabled': False, 'short': 5, 'long': 20})
    strategies.setdefault('rsi', {'enabled': False, 'period': 14, 'low': 30, 'high': 70})
    strategies.setdefault('kd', {'enabled': False, 'period': 9, 'k_smooth': 3, 'd_smooth': 3, 'low': 20, 'high': 80})
    strategies.setdefault('macd', {'enabled': False, 'fast': 12, 'slow': 26, 'signal': 9})

    if not stock_id or not start or not end:
        return _err('stock_id / start_date / end_date required')
    if capital < 1000:
        return _err('capital must be >= 1000')
    if not (strategies.get('ma', {}).get('enabled')
            or strategies.get('rsi', {}).get('enabled')
            or strategies.get('kd', {}).get('enabled')
            or strategies.get('macd', {}).get('enabled')):
        return _err('至少啟用一個策略')

    # 簡單日期格式檢查
    try:
        datetime.strptime(start, '%Y-%m-%d')
        datetime.strptime(end, '%Y-%m-%d')
    except ValueError:
        return _err('日期格式錯誤，需為 YYYY-MM-DD')

    try:
        client = FinMindClient()
        rows = client.query('TaiwanStockPrice', {
            'data_id': stock_id,
            'start_date': start,
            'end_date': end,
        })
    except FinMindError as e:
        return _err(str(e), 502)

    if not rows:
        return _err('該區間無價格資料', 404)

    try:
        result = run_backtest(
            rows=rows,
            capital=capital,
            strategies=strategies,
            combine_mode=combine_mode,
            frequency=frequency,
            month_day=month_day,
        )
        result['stock_id'] = stock_id
        try:
            save_backtest_summary(stock_id, result)
        except Exception:
            pass  # 寫歷史失敗不影響回傳
        return jsonify(result)
    except ValueError as e:
        return _err(str(e), 400)
    except Exception as e:
        return _err(f'回測失敗：{e}', 500)


# ────────────────────────── 量化回測（非同步，支援 polling）─────────────────────────
@api_bp.post('/quant_run')
def quant_run():
    """非同步版本：立即回 job_id，背景跑回測。
    Body（可選）:
        {
            'strategies': [{name, weight}, ...],
            'start': 'YYYY-MM-DD',
            'end': 'YYYY-MM-DD',
            'top_n': int,
            'fee_buy': float, 'fee_sell': float,
            'tax_sell': float, 'slippage': float,
        }
    """
    err = _require_token()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    # 過濾掉 None 值避免覆蓋 runner 預設
    kwargs = {k: v for k, v in body.items() if v is not None and k != 'strategies'}
    if 'strategies' in body and body['strategies']:
        kwargs['strategies'] = body['strategies']
    result = run_quant_async(**kwargs)
    return jsonify(result)


@api_bp.get('/quant_status')
def quant_status():
    """
    GET /api/quant_status           → 同步版最後狀態（向後相容）
    GET /api/quant_status?job_id=xxx → 非同步 job 進度
    """
    job_id = request.args.get('job_id') or None
    return jsonify(get_status(job_id=job_id))


@api_bp.get('/quant_pool')
def quant_pool():
    """回傳量化預設股票池（讀 quant/pool.json，沒有就用 26 檔預設）"""
    pool_file = QUANT_DIR / 'pool.json'
    if pool_file.is_file():
        try:
            data = json.loads(pool_file.read_text(encoding='utf-8'))
            if isinstance(data, list):
                stocks = [str(s).strip() for s in data if str(s).strip()]
                # 去重 + 排序
                stocks = sorted(set(stocks))
                return jsonify({'count': len(stocks), 'stocks': stocks})
        except Exception:
            pass

    # 26 檔預設池（從 quant/config.py STOCK_POOL 拆出來）
    default_pool = [
        '0056', '00878', '00919', '1301', '1303', '1326', '2303', '2317', '2330',
        '2357', '2379', '2382', '2412', '2454', '2603', '2609', '2881', '2882',
        '2884', '2885', '2886', '2887', '2891', '3008', '3034', '3711',
    ]
    return jsonify({'count': len(default_pool), 'stocks': default_pool})


# ────────────────────────── 量化策略（參數 + 使用者啟用/權重）─────────────────────────
@api_bp.get('/strategies')
def strategies_list():
    """
    GET /api/strategies
    回傳所有量化策略的：
      - meta：name / type / schema_version / updated_at
      - params：純因子參數（從 strategies/params/<name>.json 讀）
      - user_config：使用者在 UI 設的 enabled / weight（從 user_strategies.json 讀）
    """
    metas = list_strategies()  # [{name, type, schema_version, updated_at}]
    user_cfg = load_user_strategy_config()
    user_map = {s['name']: s for s in user_cfg.get('strategies', [])}

    items = []
    from lib.strategy_store import load as _store_load
    for meta in metas:
        name = meta['name']
        params: dict = {}
        try:
            full = _store_load(name)
            params = full.get('params', {}) or {}
        except FileNotFoundError:
            pass
        except Exception:
            pass

        u = user_map.get(name, {'enabled': True, 'weight': 0.0})
        items.append({
            'name': name,
            'type': meta.get('type', name),
            'schema_version': meta.get('schema_version', 1),
            'updated_at': meta.get('updated_at'),
            'params': params,
            'enabled': bool(u.get('enabled', True)),
            'weight': float(u.get('weight', 0)),
        })

    return jsonify({
        'count': len(items),
        'strategies': items,
        'user_updated_at': user_cfg.get('updated_at'),
    })


@api_bp.post('/strategies/config')
def strategies_config_save():
    """
    POST /api/strategies/config
    Body: { strategies: [{ name, enabled, weight }, ...] }
    儲存使用者的啟用與權重設定。
    """
    body = request.get_json(silent=True) or {}
    strategies = body.get('strategies')
    if not isinstance(strategies, list):
        return _err('strategies must be a list')

    try:
        saved = save_user_strategy_config(strategies)
    except Exception as e:
        return _err(f'儲存失敗：{e}', 500)

    return jsonify({
        'ok': True,
        'strategies': saved['strategies'],
        'updated_at': saved['updated_at'],
    })


# ────────────────────────── 健康檢查 ──────────────────────────
@api_bp.get('/health')
def health():
    checks = {
        'finmind_token': FINMIND_TOKEN != '',
        'stock_list_cache': STOCK_LIST_CACHE_FILE.is_file(),
        'python_ok': True,
        'pandas_ok': True,
        'quant_main': (QUANT_DIR / 'main.py').is_file(),
        'quant_report': (QUANT_DIR / 'output' / 'report.html').is_file(),
    }

    # 套件檢查
    try:
        import pandas  # noqa: F401
        checks['pandas_ok'] = True
    except ImportError:
        checks['pandas_ok'] = False
    try:
        import plotly  # noqa: F401
        checks['plotly_ok'] = True
    except ImportError:
        checks['plotly_ok'] = False
    try:
        from FinMind.data import DataLoader  # noqa: F401
        checks['finmind_pkg_ok'] = True
    except ImportError:
        checks['finmind_pkg_ok'] = False

    checks['python_version'] = sys.version.split()[0]
    all_ok = all(v for v in checks.values() if isinstance(v, bool))
    return jsonify({
        'ok': all_ok,
        'checks': checks,
    }), 200 if all_ok else 503
