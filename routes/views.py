"""
頁面路由（單一頁面 + hash 路由）
- /            主框架
- /quant/output/<path>  量化報告檔（讓 iframe 讀得到）
- /health      簡單健全頁（與 API 不同）
"""
from flask import Blueprint, render_template, send_from_directory

from app_config import QUANT_OUTPUT_DIR

views_bp = Blueprint('views', __name__)


@views_bp.route('/')
def index():
    return render_template('base.html')


@views_bp.route('/quant/output/<path:filename>')
def quant_output(filename):
    """serve 量化報告檔案（report.html / backtest_results.json）"""
    return send_from_directory(str(QUANT_OUTPUT_DIR), filename)
