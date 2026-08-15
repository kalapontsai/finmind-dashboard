"""
多因子量化回測 - 設定檔
修改這裡的參數即可調整回測條件。
"""

import os
import sys
from pathlib import Path

# === 1. FinMind Token ===
# 從根目錄的 app_config.py 載入（單一來源）
# 設定 application 的 token 來源：data/finmind_token.txt 或 ~/.env
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app_config import FINMIND_TOKEN  # noqa: E402


def load_finmind_token() -> str:
    """從 app_config 讀取 FINMIND_TOKEN（與 Flask 共用同一份）。"""
    if not FINMIND_TOKEN:
        raise ValueError(
            'FINMIND_TOKEN 未設定。請在 data/finmind_token.txt 或 ~/.env 設定。'
        )
    return FINMIND_TOKEN


# === 2. 回測區間 ===
START_DATE = '2023-01-01'
END_DATE = '2026-08-12'

# === 3. 股票池（v1.4 P3-6：DEPRECATED，請改用 quant/pool.json） ===
# 來源改為 `quant/pool.txt`（手動編輯）→ `quant/pool.json`（lib/pool_loader.py sync）。
# 讀取順序見 lib/pool_loader.load_pool()。這個變數只保留為 report.py 的最後 fallback。
STOCK_POOL = [
    # 半導體
    '2330',  # 台積電
    '2317',  # 鴻海
    '2454',  # 聯發科
    '2303',  # 聯電
    '3711',  # 日月光投控
    '2379',  # 瑞昱
    '3034',  # 聯詠
    # 電子組裝 / 品牌
    '2382',  # 廣達
    '3008',  # 大立光
    '2357',  # 華碩
    # 金融
    '2881',  # 富邦金
    '2882',  # 國泰金
    '2884',  # 玉山金
    '2885',  # 元大金
    '2891',  # 中信金
    '2886',  # 兆豐金
    '2887',  # 台新金
    # 電信 / 公用
    '2412',  # 中華電
    # 傳產 / 塑化
    '1301',  # 台塑
    '1303',  # 南亞
    '1326',  # 台化
    # 高股息 ETF
    '0056',  # 元大高股息
    '00878', # 國泰永續高股息
    '00919', # 群益台灣精選高股息
    # 航運
    '2603',  # 長榮
    '2609',  # 陽明
]

# === 4. 因子權重（總和 = 1.0） ===
WEIGHTS = {
    'value':    0.40,   # 價值：PER（低 = 好）
    'momentum': 0.30,   # 動能：120 日漲幅（高 = 好）
    'quality':  0.30,   # 品質：ROE（高 = 好）
}

# === 5. 因子參數 ===
MOMENTUM_LOOKBACK = 120   # 動能回看天數

# === 6. 選股 / 持倉 ===
TOP_N = 5                  # 每月選出前 N 大總分
EQUAL_WEIGHT = 0.20        # 每檔權重（1 / TOP_N）
MIN_LIQUIDITY_SHARES = 0   # 流動性最低門檻（20 日均量，0 = 不過濾）

# === 7. 交易成本（已移至 lib/cost.py；這裡保留供 report.py 向後相容）===
COMMISSION = 0.001425       # 買入手續費 0.1425%（僅供顯示用，實際計算見 lib/cost.py）
TAX = 0.003                 # 賣出證交稅 0.3%（僅供顯示用）
SLIPPAGE = 0.001            # 滑價 0.1%（僅供顯示用）

# === 8. 市場基準 ===
# 雙基準 B&H：股票池等權重（pool） + 市場 ETF（market）
MARKET_BENCHMARK = '0050'   # None = 不顯示市場基準

# === 9. 報表輸出 ===
OUTPUT_DIR = Path(__file__).parent / 'output'
OUTPUT_DIR.mkdir(exist_ok=True)
REPORT_FILE = OUTPUT_DIR / 'report.html'
RESULTS_JSON = OUTPUT_DIR / 'backtest_results.json'

# === 10. Buy & Hold 對照基準（已整合進 MARKET_BENCHMARK）===
# 不指定 → 用股票池等權重
BENCHMARK_POOL = None   # 例如 ['0050'] 表用 0050 當對照；None = 股票池等權重（僅向後相容）