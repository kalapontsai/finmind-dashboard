"""
FinMind Dashboard — Flask 入口
- 單一 process 跑 Flask（5000 port）
- 個股分析 / 單股回測 / 多因子量化
- 取代舊版 PHP + Apache 架構
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 確保根目錄在 sys.path（讓 from app_config / from lib.xxx 有效）
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from flask import Flask, jsonify  # noqa: E402

from app_config import FlaskConfig, ROOT_DIR, STATIC_DIR, TEMPLATES_DIR  # noqa: E402
from routes.api import api_bp  # noqa: E402
from routes.views import views_bp  # noqa: E402


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(STATIC_DIR),
        template_folder=str(TEMPLATES_DIR),
    )
    app.config.from_object(FlaskConfig)

    # 註冊 blueprints
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)

    # 全域錯誤處理
    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({'error': 'not found'}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'error': str(e)}), 500

    return app


# ────────────────────────── 啟動 ──────────────────────────
app = create_app()


if __name__ == '__main__':
    # 0.0.0.0: 讓外部（手機、其他裝置）也可連
    # debug=False：避免 quant 子進程跑兩次
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    print(f'🚀 FinMind Dashboard 啟動中：http://{host}:{port}/')
    print(f'📁 根目錄：{ROOT_DIR}')
    app.run(host=host, port=port, debug=False, threaded=True)
