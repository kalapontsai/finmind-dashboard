# FinMind Dashboard

台股個股分析 + 策略回測儀表板，資料源為 [FinMind](https://finmindtrade.com/) API。

包含兩個子系統：

1. **Dashboard**（PHP + JS）— 個股分析、技術指標、單股策略回測、視覺化圖表
2. **量化回測**（Python）— 多因子（價值/動能/品質）量化選股回測，附 0050 含息 benchmark

---

## 功能

### Dashboard

- 個股清單搜尋（24h 快取）
- 個股分析：K 線 + MA / RSI / KD / MACD、PER / PBR / 殖利率、月營收、三大財報、配息、法人買賣超、融資融券
- 策略回測：MA / RSI / KD / MACD 任選組合（AND / OR 觸發）
- 回測結果本地保存（最多 50 筆）
- 主題：GitHub Dark
- 純前端：HTML + vanilla JS + Chart.js（無框架）

### 量化回測

- 3 因子綜合評分：價值 40% / 動能 30% / 品質 30%
- 每月第一個交易日換倉，選出總分前 N 大
- 含手續費 0.1425% + 證交稅 0.3%
- 互動式 HTML 報表（plotly）
- 0050 含息 benchmark 對照

---

## 部署

需要：

- PHP 8.1+
- Python 3.10+（量化回測）
- Apache / Nginx（PHP）
- 對外網路的 FinMind API token（[免費註冊](https://finmindtrade.com/)）

### 1. Apache 設定

把整個目錄放到 web root（例如 `<DOCUMENT_ROOT>/finmind/`），`.htaccess` 內含禁止讀取 `data/` `lib/` `config.php` 的規則，無需額外設定。

### 2. FinMind Token

提供兩段式讀取：

1. `<DOCUMENT_ROOT>/finmind/data/finmind_token.txt`（受 `.htaccess` 403 保護，容器內首選）
2. 環境變數 `FINMIND_ENV_FILE` 指向的 `.env` 檔案（內含 `FINMIND_TOKEN=...`，WSL/host 部署用）

> ⚠️ **同 IP 多 token 會被 FinMind 偵測並封鎖**，請只保留一個 token。已驗證踩坑。

設定範例：

```bash
# 你自己的 .env 範例（一行一個）
FINMIND_TOKEN=eyJhbGciOi...
```

```bash
# 然後告訴應用程式去哪找這個檔
export FINMIND_ENV_FILE=/path/to/your/.env
```

PHP 端自動讀取；Python 端須在執行前 export。

### 3. Python 依賴（量化回測）

```bash
cd quant
python3 -m venv .venv
source .venv/bin/activate
pip install FinMind pandas numpy plotly pyarrow
```

### 4. 啟動

- Dashboard：開啟 `<DEPLOY_URL>/finmind/` 即可
- 量化回測：

```bash
cd <your-project-root>/quant
python3 main.py              # 跑回測 + 產 HTML
python3 main.py --open       # 跑完自動開瀏覽器
```

> 第一次跑會向 FinMind 抓資料（每檔約 3 次呼叫）。之後會用 `cache/*.parquet` 加速。
> 若遇 `402` 或 `ip banned`，請等下個小時額度自動恢復。

---

## 目錄結構

```
finmind-dashboard/
├── README.md                      # 本檔
├── LICENSE                        # MIT License
├── .gitignore
├── .htaccess                      # 保護 data/ lib/ config.php
├── SKILL.md                       # Dashboard 工程筆記
├── index.php                      # Dashboard 入口（hash 路由）
├── config.php                     # 兩段式讀 token
│
├── api/                           # 後端 PHP proxy
│   ├── stock_list.php
│   ├── stock_price.php
│   ├── stock_per.php
│   ├── stock_revenue.php
│   ├── stock_finance.php
│   ├── stock_dividend.php
│   ├── institutional.php
│   ├── margin.php
│   ├── backtest.php
│   ├── quant_run.php
│   └── quant_status.php
│
├── pages/                         # hash 路由 fragment
│   ├── analysis.php
│   └── backtest.php
│
├── assets/
│   ├── css/style.css              # GitHub Dark
│   ├── js/
│   │   ├── app.js                 # 路由 / sidebar
│   │   ├── api.js                 # API client
│   │   ├── indicators.js          # 技術指標計算
│   │   ├── analysis.js            # 個股分析
│   │   ├── backtest.js
│   │   └── quant.js
│   └── lib/chart.umd.js           # Chart.js 4.4.1（本地）
│
├── lib/
│   └── finmind.php                # FinMind API client class
│
├── quant/                         # 多因子量化回測
│   ├── SKILL.md
│   ├── main.py                    # 入口
│   ├── config.py
│   ├── quant.py                   # 核心邏輯
│   ├── report.py                  # HTML 報表
│   ├── cache/                     # parquet 快取（gitignore）
│   └── output/                    # 報表輸出（gitignore）
│
└── data/
    ├── .gitkeep
    ├── finmind_token.txt          # gitignore（容器內 token）
    ├── stock_list.json            # gitignore（24h 快取）
    └── backtest_results.json      # gitignore（回測輸出）
```

---

## 安全設計

1. **Token 雙層防護**
   - 讀取順序：`finmind/data/finmind_token.txt` → 環境變數 `FINMIND_ENV_FILE` 指向的 `.env`
   - `.htaccess` 設 403 禁止 web 直接讀 `/data/` `/lib/` `/config.php`
2. **XSS 防護**：所有前端輸出經 `esc()` HTML entity 轉義
3. **錯誤處理**：PHP API 用 try/catch + `json_error()`，前端用 `Promise.allSettled` 容忍部分失敗
4. **參數過濾**：URLSearchParams 過濾 undefined / null，避免 `"undefined"` 字串傳到 FinMind

---

## FinMind Dataset 名稱速查

| 想拿的資料 | 正確 dataset |
|-----------|------------|
| 個股基本資料 | `TaiwanStockInfo` |
| 歷史股價 | `TaiwanStockPrice` |
| 本益比 / 淨值比 / 殖利率 | `TaiwanStockPER` |
| 月營收 | `TaiwanStockMonthRevenue` |
| 三大財報 | `TaiwanStockFinancialStatements` |
| **配息** | `TaiwanStockDividend`（**單一** dataset，欄位含 `CashEarningsDistribution` 等，需後端彙總） |
| 三大法人 | `TaiwanStockInstitutionalInvestorsBuySell` |
| 融資融券 | `TaiwanStockMarginPurchaseShortSale` |

---

## 已知限制

1. **回測無部位管理**：每次觸發「全部現金買進」或「全部庫存賣出」，不支援分批、停損、停利
2. **個股清單快取 24h**：新增股票可能 24 小時後才會出現在搜尋
3. **無即時股價**：FinMind 個股股價有 1 天延遲（daily 收盤後才更新）
4. **回測無費用**：Dashboard 端回測未考慮手續費 / 證交稅；量化回測有
5. **單 IP 單 token**：同 IP 使用多個 token 會被封鎖，已驗證

---

## 授權

MIT License — 詳見 [LICENSE](LICENSE) 檔。
