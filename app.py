"""
app.py — Flask 入口
- 5 個 API：
  GET  /                  首頁
  GET  /api/health        健康檢查
  GET  /api/profiles      列出 user_profile/*.csv
  GET  /api/profile/<n>   預覽單檔名單
  POST /api/analyze       主分析（3 模式 + N-Year 預估）
  POST /api/export        匯出 HTML / PDF
- 報表檔案透過 /data/reports/ 靜態路徑下載
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import (
    Flask, jsonify, render_template, request, send_from_directory, url_for,
)

# 確保根目錄在 sys.path（讓 from lib.xxx 有效）
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_config import (  # noqa: E402
    DATA_DIR, DEFAULT_N_YEARS, DEFAULT_PV, DEFAULT_START_DATE,
    LOGS_DIR, MAX_CONTENT_LENGTH, REPORTS_DIR, ROOT_DIR, STATIC_DIR,
    TEMPLATES_DIR, USER_PROFILE_DIR,
)
from lib.csv_loader import CSVLintError, list_profile_csvs, load_portfolio_csv  # noqa: E402
from lib.exporter import render_html_report, render_pdf_report  # noqa: E402
from lib.finmind import FinMindClient, FinMindError, load_finmind_token  # noqa: E402
from lib.forecast import ForecastError, build_forecast  # noqa: E402
from lib.portfolio import (  # noqa: E402
    BacktestError, build_benchmark, build_portfolio, compute_market_value,
    per_stock_history, prices_to_pivot,
)


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(STATIC_DIR),
        template_folder=str(TEMPLATES_DIR),
    )
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

    # ────────────── 頁面 ──────────────
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/data/reports/<path:filename>')
    def serve_report(filename):
        return send_from_directory(str(REPORTS_DIR), filename, as_attachment=False)

    # ────────────── 健康檢查 ──────────────
    @app.get('/api/health')
    def health():
        checks = {
            'finmind_token': bool(load_finmind_token()),
            'user_profile_dir': USER_PROFILE_DIR.is_dir(),
            'profile_csvs': list_profile_csvs(USER_PROFILE_DIR),
            'python_ok': True,
        }
        try:
            import pandas  # noqa: F401
            checks['pandas_ok'] = True
        except ImportError:
            checks['pandas_ok'] = False
        try:
            import reportlab  # noqa: F401
            checks['reportlab_ok'] = True
        except ImportError:
            checks['reportlab_ok'] = False
        all_ok = all(v for v in checks.values() if isinstance(v, bool))
        return jsonify({'ok': all_ok, 'checks': checks}), 200 if all_ok else 503

    # ────────────── 名單 ──────────────
    @app.get('/api/profiles')
    def profiles():
        return jsonify({
            'profiles': list_profile_csvs(USER_PROFILE_DIR),
            'dir': str(USER_PROFILE_DIR),
        })

    @app.get('/api/profile/<name>')
    def profile_preview(name: str):
        # 防止 path traversal
        if '/' in name or '\\' in name or '..' in name:
            return jsonify({'error': 'invalid name'}), 400
        path = USER_PROFILE_DIR / f'{name}.csv'
        if not path.is_file():
            return jsonify({'error': f'{name}.csv not found'}), 404
        try:
            holdings = load_portfolio_csv(path)
        except CSVLintError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify({
            'name': name,
            'count': len(holdings),
            'holdings': [{'ticker': h.ticker, 'shares': h.shares} for h in holdings],
        })

    # ────────────── 主分析 ──────────────
    @app.post('/api/analyze')
    def analyze():
        body = request.get_json(silent=True) or {}
        try:
            result = _run_analyze(body)
        except _BadInput as e:
            return jsonify({'error': str(e)}), 400
        except (CSVLintError, BacktestError, ForecastError, FinMindError) as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:  # noqa: BLE001
            return jsonify({'error': f'內部錯誤：{type(e).__name__}: {e}'}), 500
        return jsonify(result)

    # ────────────── 匯出 ──────────────
    @app.post('/api/export')
    def export():
        body = request.get_json(silent=True) or {}
        result = body.get('result')
        fmt = (body.get('format') or 'pdf').lower()
        profile_name = (body.get('profile_name') or '').strip()
        if not result or not isinstance(result, dict):
            return jsonify({'error': 'result 不可為空'}), 400
        if fmt not in ('html', 'pdf'):
            return jsonify({'error': "format 必須是 html 或 pdf"}), 400

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        uid = uuid.uuid4().hex[:8]
        if fmt == 'pdf':
            fname = f'portfolio_forecast_{ts}_{uid}.pdf'
            out = REPORTS_DIR / fname
            try:
                render_pdf_report(result, out, profile_name=profile_name)
            except Exception as e:  # noqa: BLE001
                return jsonify({'error': f'PDF 產生失敗：{e}'}), 500
        else:
            fname = f'portfolio_forecast_{ts}_{uid}.html'
            out = REPORTS_DIR / fname
            try:
                out.write_text(
                    render_html_report(result, profile_name=profile_name),
                    encoding='utf-8',
                )
            except Exception as e:  # noqa: BLE001
                return jsonify({'error': f'HTML 產生失敗：{e}'}), 500

        return jsonify({
            'file': fname,
            'url': url_for('serve_report', filename=fname),
            'format': fmt,
            'size': out.stat().st_size,
        })

    # ────────────── 錯誤 ──────────────
    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'not found'}), 404
        return jsonify({'error': 'not found'}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'error': str(e)}), 500

    return app


# ────────────── 核心邏輯 ──────────────
class _BadInput(ValueError):
    pass


def _parse_weights(raw, tickers: list[str]) -> dict[str, float] | None:
    """支援 '2330:0.3,2317:0.7' 字串 或 {ticker: weight} dict"""
    if raw is None or raw == '':
        return None
    if isinstance(raw, dict):
        return {str(k).strip(): float(v) for k, v in raw.items()}
    if isinstance(raw, str):
        out: dict[str, float] = {}
        for chunk in raw.split(','):
            chunk = chunk.strip()
            if not chunk or ':' not in chunk:
                continue
            k, v = chunk.split(':', 1)
            out[k.strip()] = float(v.strip())
        return out if out else None
    raise _BadInput('weights 格式錯誤（需 dict 或 "TICKER:weight,..." 字串）')


def _run_analyze(body: dict) -> dict:
    """主分析流程：
    1) 讀名單 → FinMind TaiwanStockInfo 預先驗證 stock_id 存在 → 過濾假代號
    2) 抓 first_trading_day + 標記歷史太短的股票
    3) 抓 FinMind TaiwanStockPrice（只抓驗證過的）
    4) 三模式回測
    5) 計算起始市值（最後收盤價 × 股數）
    6) N-Year 預估
    7) 組裝回傳（含 bias 警告）
    """
    # 1) 解析輸入
    profile = (body.get('profile') or '').strip()
    if not profile:
        raise _BadInput('profile 必填（從 /api/profiles 選一個）')
    if '/' in profile or '\\' in profile or '..' in profile:
        raise _BadInput('profile 名稱不合法')
    profile_path = USER_PROFILE_DIR / f'{profile}.csv'
    if not profile_path.is_file():
        raise _BadInput(f'{profile}.csv 不存在')

    holdings = load_portfolio_csv(profile_path)
    user_tickers = [h.ticker for h in holdings]
    shares_map = {h.ticker: h.shares for h in holdings}

    n = int(body.get('n', DEFAULT_N_YEARS))
    if n < 1 or n > 50:
        raise _BadInput('n 必須在 1~50 之間')
    user_pv = body.get('pv')  # None = 自動用實際市值
    start_date = (body.get('start_date') or DEFAULT_START_DATE).strip()
    end_date = (body.get('end_date') or datetime.now().strftime('%Y-%m-%d')).strip()
    weights = _parse_weights(body.get('weights'), user_tickers)

    # 1.5) 交易成本（選填，預設 0 = 不計）
    # Buy & hold 場景下，成本只作用在「初始買入」一次：
    #   effective_pv = pv / (1 + fee_buy + slippage)
    # 月/季 rebalancing 場景下則每次都抽。详細見 README。
    fee_buy = float(body.get('fee_buy', 0) or 0)
    fee_sell = float(body.get('fee_sell', 0) or 0)
    tax_sell = float(body.get('tax_sell', 0) or 0)
    slippage = float(body.get('slippage', 0) or 0)
    if any(x < 0 or x > 0.1 for x in (fee_buy, fee_sell, tax_sell, slippage)):
        raise _BadInput('fee/tax/slippage 應在 0~0.1（10%）之間')

    # 1.6) Benchmark（選填）
    benchmark_id = (body.get('benchmark') or '').strip() or None

    # 2) 預先驗證：TaiwanStockInfo 抓清單 → match user ticker → 過濾假代號
    client = FinMindClient()
    try:
        stock_list = client.get_stock_list()
    except FinMindError as e:
        raise _BadInput(f'FinMind TaiwanStockInfo 抓取失敗：{e}') from e

    matched: dict[str, dict] = {}        # stock_id → match 結果（含 stock_name）
    invalid_tickers: list[dict] = []     # [{user_input, reason}]
    for ut in user_tickers:
        m = client.match_ticker(ut)
        if m is None:
            invalid_tickers.append({
                'user_input': ut,
                'reason': f'在 TaiwanStockInfo 清單中查無此代號（可能是 typo 或已下市）',
            })
            continue
        sid = m['stock_id']
        if sid in matched:
            # 同一檔被多個 user ticker match 到 → 累加股數
            matched[sid]['matched_from'].append(ut)
            continue
        matched[sid] = {
            'stock_id': sid,
            'stock_name': m.get('stock_name', ''),
            'industry_category': m.get('industry_category', ''),
            'type': m.get('type', ''),
            'source': m.get('source', ''),
            'matched_from': [ut],
        }

    if not matched:
        raise _BadInput(
            '名單中所有 ticker 都不在 FinMind TaiwanStockInfo 清單內。'
            '請檢查代號是否正確（例如 50 → 0050、6208 → 006208）。'
        )

    # 3) 抓 first_trading_day + 標記歷史太短
    valid_stock_ids = list(matched.keys())
    first_trading_days: dict[str, str | None] = {}
    short_history: list[str] = []   # < N 年的 ticker
    today_ts = pd.Timestamp(end_date)
    n_years_ago = today_ts - pd.DateOffset(years=n)

    for sid in valid_stock_ids:
        try:
            ftd = client.get_first_trading_day(sid)
        except FinMindError:
            ftd = None
        first_trading_days[sid] = ftd
        if ftd is None:
            # 該股根本沒歷史股價
            invalid_tickers.append({
                'user_input': matched[sid]['matched_from'][0],
                'stock_id': sid,
                'reason': f'{sid}（{matched[sid].get("stock_name", "")}）查無任何歷史股價資料',
            })
            del matched[sid]
        else:
            ftd_ts = pd.Timestamp(ftd)
            if ftd_ts > n_years_ago:
                short_history.append(sid)

    if not matched:
        raise _BadInput('過濾掉無歷史資料的 ticker 後，沒有任何可用股票。請檢查名單。')

    # 4) 抓歷史價格（只抓驗證過 + 有 first_trading_day 的）
    final_stock_ids = list(matched.keys())
    rows_by_ticker: dict[str, list[dict]] = {}
    fetch_errors: dict[str, str] = {}
    for sid in final_stock_ids:
        try:
            # 起點用 first_trading_day 避免浪費 API 額度
            ftd = first_trading_days.get(sid, start_date)
            actual_start = max(ftd, start_date) if ftd else start_date
            rows_by_ticker[sid] = client.get_stock_price(sid, actual_start, end_date)
        except FinMindError as e:
            fetch_errors[sid] = str(e)
    # 過濾空 list
    for sid in list(rows_by_ticker.keys()):
        if not rows_by_ticker[sid]:
            del rows_by_ticker[sid]

    if not rows_by_ticker:
        raise FinMindError(f'驗證後的股票都抓不到歷史價格：{fetch_errors}')

    # 5) 轉 pivot
    prices = prices_to_pivot(rows_by_ticker, price_col='close')
    if prices.empty:
        raise BacktestError('抓回的價格資料為空')

    # 6) 起始市值（用最後一個共同交易日的收盤價 × 股數）
    # 累加同 stock_id 的股數
    combined_shares: dict[str, int] = {}
    for sid, info in matched.items():
        for ut in info['matched_from']:
            combined_shares[sid] = combined_shares.get(sid, 0) + shares_map[ut]

    mv = compute_market_value(prices, combined_shares)
    if user_pv is None:
        raw_pv = mv['total']
        pv_source = 'market_value'
    else:
        raw_pv = float(user_pv)
        pv_source = 'user_input'
        if raw_pv < 0:
            raise _BadInput('pv 不可為負')

    # 套用交易成本（Buy & hold：只在初始買入抽）
    initial_cost_rate = fee_buy + slippage
    if initial_cost_rate > 0 and pv_source == 'market_value':
        # 成本只在「使用者沒手動指定 pv」時套用（因為手動 pv 已含/不含成本由使用者決定）
        effective_pv = raw_pv / (1 + initial_cost_rate)
        cost_text = f'（已扣買入手續費 {fee_buy*100:.3f}% + 滑價 {slippage*100:.3f}%）'
    else:
        effective_pv = raw_pv
        cost_text = ''
    pv = effective_pv
    pv_raw = raw_pv
    pv_cost_text = cost_text

    # 7) 三模式
    common_res = build_portfolio(prices, mode='common', weights=weights)
    dynamic_res = build_portfolio(prices, mode='dynamic', weights=weights)
    full_res = build_portfolio(prices, mode='full', weights=weights)

    # 7.5) Benchmark
    benchmark = None
    if benchmark_id:
        try:
            bench_rows = client.get_stock_price(benchmark_id, start_date, end_date)
            bench_prices = prices_to_pivot({benchmark_id: bench_rows}, price_col='close')
            if not bench_prices.empty:
                # 裁到跟 dynamic 同期，公平對照
                bench_prices = bench_prices.loc[:dynamic_res.nav.index[-1]] if not dynamic_res.nav.empty else bench_prices
                benchmark = build_benchmark(bench_prices, ticker=benchmark_id)
        except FinMindError as e:
            benchmark = {'ticker': benchmark_id, 'error': str(e)}

    # 8) N-Year 預估：優先用 Common，不夠則退回 Dynamic / Full
    forecast_basis = 'common'
    forecast = None
    for basis, res in (('common', common_res), ('dynamic', dynamic_res), ('full', full_res)):
        try:
            forecast = build_forecast(res.nav, n=n, pv=pv)
            forecast_basis = basis
            break
        except ForecastError:
            continue
    if forecast is None:
        raise ForecastError(
            f'三個模式的歷史長度都無法建立 N={n} 年 rolling outcome。'
            f'請縮短 N 年數，或加入上市更久的股票。'
        )
    forecast['basis'] = forecast_basis

    # 9) 個股歷史長度（加強版）
    psh = per_stock_history(prices)

    # 10) 組裝回傳
    overview = {
        'stocks': len(matched),
        'min_years': min((v['years'] for v in psh.values()), default=0),
        'median_years': sorted([v['years'] for v in psh.values()])[len(psh) // 2] if psh else 0,
        'max_years': max((v['years'] for v in psh.values()), default=0),
    }

    return {
        'inputs': {
            'profile': profile,
            'user_tickers': user_tickers,
            'tickers': final_stock_ids,  # 驗證後的 stock_id 清單
            'shares': shares_map,
            'combined_shares': combined_shares,
            'n': n,
            'pv': pv,
            'pv_raw': pv_raw,
            'pv_source': pv_source,
            'pv_cost_text': pv_cost_text,
            'fees': {
                'fee_buy': fee_buy,
                'fee_sell': fee_sell,
                'tax_sell': tax_sell,
                'slippage': slippage,
            },
            'start_date': start_date,
            'end_date': end_date,
            'weights': weights,
            'invalid_tickers': invalid_tickers,
            'first_trading_days': first_trading_days,
            'short_history': short_history,
            'fetch_errors': fetch_errors,
            'ticker_match': {sid: {
                'stock_id': sid,
                'stock_name': info['stock_name'],
                'industry': info['industry_category'],
                'type': info['type'],
                'source': info['source'],
                'matched_from': info['matched_from'],
            } for sid, info in matched.items()},
        },
        'market_value': mv,
        'benchmark': benchmark,
        'common': _serialize_result(common_res),
        'dynamic': _serialize_result(dynamic_res),
        'full': _serialize_result(full_res),
        'forecast': forecast,
        'history': {
            'overview': overview,
            'per_stock': psh,
        },
        'nav_series': {
            'common': _downsample_nav(common_res.nav),
            'dynamic': _downsample_nav(dynamic_res.nav),
            'full': _downsample_nav(full_res.nav),
        },
    }


def _serialize_result(r) -> dict:
    """把 PortfolioResult 轉 JSON-safe dict"""
    return {
        'mode': r.mode,
        'metrics': r.metrics,
        'nav': _downsample_nav(r.nav),
        'pct_active': (
            [{'date': str(d.date()), 'n': int(v)} for d, v in r.pct_active.items()]
            if r.pct_active is not None else None
        ),
    }


def _downsample_nav(nav, max_points: int = 500) -> list[dict]:
    """NAV 太長時下採樣到 ~500 點（避免 JSON 太大）"""
    if nav is None or nav.empty:
        return []
    if len(nav) <= max_points:
        return [{'date': str(d.date()), 'nav': float(v)} for d, v in nav.items()]
    step = max(1, len(nav) // max_points)
    sampled = nav.iloc[::step]
    if sampled.index[-1] != nav.index[-1]:
        # 確保最後一點是真正的 end-of-data
        sampled = pd_concat_safe(sampled, nav.iloc[[-1]])
    return [{'date': str(d.date()), 'nav': float(v)} for d, v in sampled.items()]


def pd_concat_safe(*series) -> 'pd.Series':
    """小工具：concat 多個 Series 並去重（by index）"""
    import pandas as pd
    s = pd.concat(list(series))
    s = s[~s.index.duplicated(keep='last')].sort_index()
    return s


# ────────────── 啟動 ──────────────
app = create_app()


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    print(f'🚀 Portfolio Forecast 啟動中：http://{host}:{port}/')
    print(f'📁 根目錄：{ROOT_DIR}')
    app.run(host=host, port=port, debug=False, threaded=True)
