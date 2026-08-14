"""
FinMind Dashboard 設定
- 讀 FinMind token（兩段式：data/finmind_token.txt → ~/.env）
- 定義路徑常數
- Flask 啟動設定
"""
import os
from pathlib import Path

# ────────────────────────── 路徑 ──────────────────────────
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / 'data'
QUANT_DIR = ROOT_DIR / 'quant'
STATIC_DIR = ROOT_DIR / 'static'
TEMPLATES_DIR = ROOT_DIR / 'templates'

# 確認必要目錄存在
for p in (DATA_DIR, QUANT_DIR, STATIC_DIR, TEMPLATES_DIR):
    p.mkdir(parents=True, exist_ok=True)

# 量化產出目錄
QUANT_OUTPUT_DIR = QUANT_DIR / 'output'
QUANT_CACHE_DIR = QUANT_DIR / 'cache'
QUANT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
QUANT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ────────────────────────── Token ──────────────────────────
FINMIND_API_BASE = 'https://api.finmindtrade.com/api/v4/data'
FINMIND_RATE_LIMIT_MS = 200  # 兩次呼叫至少間隔 200ms（避免 600/hr 額度爆）
STOCK_LIST_CACHE_TTL = 86400  # 24h
BACKTEST_RESULTS_MAX = 50     # 最多保留 50 筆回測歷史

STOCK_LIST_CACHE_FILE = DATA_DIR / 'stock_list.json'
BACKTEST_RESULTS_FILE = DATA_DIR / 'backtest_results.json'
FINMIND_TOKEN_FILE = DATA_DIR / 'finmind_token.txt'

# 量化回測
QUANT_RUN_TIMEOUT = 600          # 10 分鐘
QUANT_RUN_LOCK_FILE = QUANT_DIR / '.quant.lock'
QUANT_RUN_LOCK_STALE_MIN = 30    # 超過 30 分鐘判定為 stale


def _parse_env_file(path: Path) -> dict:
    """Parse .env 檔案，剝掉單/雙引號"""
    env = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        env[k.strip()] = v
    return env


def load_finmind_token() -> str:
    """
    兩段式讀取 FinMind token：
    1) data/finmind_token.txt（純 token 單行）
    2) ~/.env 的 FINMIND_TOKEN
    """
    # 1) 純 token 檔
    if FINMIND_TOKEN_FILE.is_file():
        try:
            tok = FINMIND_TOKEN_FILE.read_text(encoding='utf-8').strip()
            if tok:
                return tok
        except Exception:
            pass

    # 2) ~/.env 內 FINMIND_TOKEN
    env_path = Path.home() / '.env'
    env = _parse_env_file(env_path)
    tok = env.get('FINMIND_TOKEN', '').strip()
    return tok


FINMIND_TOKEN: str = load_finmind_token()


# ────────────────────────── Flask 設定 ──────────────────────────
class FlaskConfig:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'finmind-dashboard-' + os.environ.get('USER', 'dev'))

    # 快取 / 歷史（Flask 內取用）
    STOCK_LIST_CACHE_TTL = STOCK_LIST_CACHE_TTL
    BACKTEST_RESULTS_MAX = BACKTEST_RESULTS_MAX
