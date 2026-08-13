"""
多因子量化回測 - 設定檔
修改這裡的參數即可調整回測條件。
"""

import os
from pathlib import Path

# === 1. FinMind Token ===
# 透過環境變數 FINMIND_ENV_FILE 指向你的 .env 檔案。
# 設定方式：export FINMIND_ENV_FILE=/path/to/your/.env
# 注意：同 IP 使用多個 token 會導致兩個都被封鎖，請只留一個
ENV_FILE = Path(os.environ.get('FINMIND_ENV_FILE', '<unset: set FINMIND_ENV_FILE>'))


def load_finmind_token() -> str:
    """從 .env 讀取 FINMIND_TOKEN（只取第一個）。"""
    if not ENV_FILE.is_file():
        raise FileNotFoundError(f"找不到 .env：{ENV_FILE}")
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        if k.strip() == 'FINMIND_TOKEN':
            return v.strip()
    raise ValueError('.env 沒有 FINMIND_TOKEN')


# === 2. 回測區間 ===
START_DATE = '2023-01-01'
END_DATE = '2026-08-12'

# === 3. 股票池（可自行擴充，最多 ~30 檔會比較好管理） ===
# 範例：半導體 + 金融 + 電信 + 高股息 + ETF 龍頭
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

# === 7. 交易成本 ===
COMMISSION = 0.001425       # 手續費 0.1425%
TAX = 0.003                 # 證交稅 0.3%（賣出）

# === 8. 報表輸出 ===
OUTPUT_DIR = Path(__file__).parent / 'output'
OUTPUT_DIR.mkdir(exist_ok=True)
REPORT_FILE = OUTPUT_DIR / 'report.html'
RESULTS_JSON = OUTPUT_DIR / 'backtest_results.json'

# === 9. Buy & Hold 對照基準 ===
# 不指定 → 用股票池等權重
BENCHMARK_POOL = None   # 例如 ['0050'] 表用 0050 當對照；None = 股票池等權重