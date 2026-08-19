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
from lib.portfolio import BacktestError, build_portfolio, prices_to_pivot  # noqa: E402


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
    """主分析流程：讀名單 → 抓價 → 三模式 → N-Year 預估 → 壓回 JSON"""
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
    tickers = [h.ticker for h in holdings]
    shares_map = {h.ticker: h.shares for h in holdings}

    n = int(body.get('n', DEFAULT_N_YEARS))
    if n < 1 or n > 50:
        raise _BadInput('n 必須在 1~50 之間')
    pv = float(body.get('pv', DEFAULT_PV))
    if pv < 0:
        raise _BadInput('pv 不可為負')
    start_date = (body.get('start_date') or DEFAULT_START_DATE).strip()
    end_date = (body.get('end_date') or datetime.now().strftime('%Y-%m-%d')).strip()
    weights = _parse_weights(body.get('weights'), tickers)

    # 2) 抓歷史價格
    client = FinMindClient()
    rows_by_ticker: dict[str, list[dict]] = {}
    errors: dict[str, str] = {}
    for sid in tickers:
        try:
            rows_by_ticker[sid] = client.get_stock_price(sid, start_date, end_date)
        except FinMindError as e:
            errors[sid] = str(e)
    if not rows_by_ticker:
        raise FinMindError(f'所有股票都抓不到歷史價格：{errors}')
    if errors:
        # 部分失敗不中斷，把成功的繼續算
        for sid in list(rows_by_ticker.keys()):
            if not rows_by_ticker[sid]:
                rows_by_ticker.pop(sid, None)

    # 3) 轉 pivot
    prices = prices_to_pivot(rows_by_ticker, price_col='close')
    if prices.empty:
        raise BacktestError('抓回的價格資料為空')

    # 4) 三模式
    common_res = build_portfolio(prices, mode='common', weights=weights)
    dynamic_res = build_portfolio(prices, mode='dynamic', weights=weights)
    full_res = build_portfolio(prices, mode='full', weights=weights)

    # 5) N-Year 預估：優先用 Common，不夠則退回 Dynamic / Full（取 rolling_count 最大的）
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

    # 6) 組裝回傳
    return {
        'inputs': {
            'profile': profile,
            'tickers': tickers,
            'shares': shares_map,
            'n': n,
            'pv': pv,
            'start_date': start_date,
            'end_date': end_date,
            'weights': weights,
            'fetch_errors': errors,
        },
        'common': _serialize_result(common_res),
        'dynamic': _serialize_result(dynamic_res),
        'full': _serialize_result(full_res),
        'forecast': forecast,
        'history': {
            'overview': {
                'stocks': dynamic_res.history_diag['stocks'],
                'min_years': dynamic_res.history_diag['min_years'],
                'median_years': dynamic_res.history_diag['median_years'],
                'max_years': dynamic_res.history_diag['max_years'],
            },
            'all_per_stock': dynamic_res.history_diag['per_stock'],
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
