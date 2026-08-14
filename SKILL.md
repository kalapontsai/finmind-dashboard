# FinMind Dashboard Skill

## 1. 專案說明

基於 FinMind API 的台股個股分析 + 策略回測 + 多因子量化儀表板。

**v2.0 大翻修**：PHP + Apache → Python Flask 獨立運作。

### 對應 FinMind 原版
| FinMind 原版 | 本專案頁面 | 路徑 |
|--------------|-----------|------|
| `#/dashboards/taiwan-stock-analysis` | 個股分析 | `#/taiwan-stock-analysis` |
| `#/dashboards/back-testing`        | 回測     | `#/back-testing`        |
| （自製）                          | 量化     | `#/quant-backtest`      |
| （自製）                          | 觀察名單 | `#/watchlist`           |

## 2. 架構（v2.0 大翻修）

單一 Flask process 跑 5000 port（取代原本 PHP + Apache 80 + FastAPI 8765 三層）。

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (port 5000)                                         │
│  └─ http://localhost:5000/  (Jinja2 base.html + hash 路由)  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Flask app (app.py)                                          │
│  ├─ views_bp  ─→  /, /quant/output/<file>                  │
│  └─ api_bp    ─→  /api/{stock_*,institutional,margin,       │
│                     backtest,quant_*,health}                  │
│       │                                                       │
│       ├─ lib/finmind.py ────→ FinMind API v4 (200ms rate-limit) │
│       ├─ lib/backtest.py ──→ 純 Python 回測引擎              │
│       └─ lib/quant_runner.py ─→ subprocess 跑 quant/main.py│
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  quant/main.py — 多因子回測（pandas + FinMind）              │
│  ├─ 抓 3 dataset × N 檔（per-stock parquet 快取）            │
│  ├─ 算 3 因子（價值 40% / 動能 30% / 品質 30%）              │
│  ├─ 每月選 Top 5、等權重、手續費 + 證交稅                    │
│  └─ 寫 report.html + backtest_results.json                  │
└─────────────────────────────────────────────────────────────┘
```

## 3. 目錄結構

```
finmind-dashboard/
├── app.py                        # Flask 入口（port 5000）
├── app_config.py                 # 設定（token、路徑）
├── lib/
│   ├── finmind.py                # FinMind API client
│   ├── backtest.py               # 策略回測引擎
│   └── quant_runner.py           # 量化背景跑
├── routes/
│   ├── views.py                  # 頁面
│   └── api.py                    # 12 個 REST 端點
├── templates/base.html           # Jinja2 主框架
├── static/
│   ├── css/style.css             # GitHub Dark + tooltip
│   ├── js/{api,indicators,analysis,backtest,quant,watchlist,tooltip,app}.js
│   └── lib/chart.umd.js
├── quant/                        # 多因子（從 v1.x 搬過來）
│   ├── main.py / quant.py / report.py / config.py
│   ├── cache/                    # parquet（gitignore）
│   └── output/                   # 報告（gitignore）
├── data/
│   ├── finmind_token.txt         # gitignore
│   ├── stock_list.json           # 個股清單快取（gitignore）
│   └── backtest_results.json     # 回測歷史（gitignore）
├── scripts/
│   ├── start.bat / stop.bat / status.bat
├── .gitignore
├── README.md / SKILL.md / CHANGELOG.md / LICENSE
└── venv/                         # 開發用（gitignore）
```

## 4. 設計風格

- GitHub Dark 主題：
  - 背景 `#0d1117`、卡片 `#161b22`、內層 `#21262d`、邊框 `#30363d`
  - 漲綠跌紅：`#3fb950` / `#f85149`
  - 強調色藍 `#58a6ff`、紫 `#8957e5`、橘 `#d29922`
- Sidebar 固定 240px 左側
- 前端：純 HTML + vanilla JS + Chart.js（無前端框架）
- 後端：Flask 3 + Blueprint 架構

## 5. 安全性

1. **Token 雙層防護**：
   - 讀取順序：`data/finmind_token.txt` → `~/.env` 的 `FINMIND_TOKEN`
   - Token 走環境變數 / 檔案，不寫死進程式
   - `.gitignore` 排除敏感檔
2. **XSS 防護**：所有前端輸出經 `esc()` HTML entity 轉義
3. **錯誤處理**：API 用 try/except + `jsonify(error=...)`，前端 Promise.allSettled 容忍部分失敗
4. **參數過濾**：URLSearchParams 過濾 undefined / null；後端再 backup 過濾 `undefined` / `null` 字串
5. **CORS**：本地 port 5000（之後考慮加 flask-cors）

## 6. FinMind Dataset 名稱（踩坑紀錄）

| 想拿的資料 | 正確 dataset 名稱 |
|-----------|-----------------|
| 個股基本資料 | `TaiwanStockInfo` |
| 歷史股價 | `TaiwanStockPrice` |
| 本益比 / 淨值比 / 殖利率 | `TaiwanStockPER` |
| 月營收 | `TaiwanStockMonthRevenue` |
| **配息**（**單一 dataset**） | `TaiwanStockDividend`（不是 `TaiwanStockCashDividend` / `TaiwanStockStockDividend`！） |
| 三大法人 | `TaiwanStockInstitutionalInvestorsBuySell` |
| 融資融券 | `TaiwanStockMarginPurchaseShortSale` |
| 三大財報 | `TaiwanStockFinancialStatements` |

`TaiwanStockDividend` 欄位包含 `CashEarningsDistribution`、`CashStatutorySurplus`、`StockEarningsDistribution`、`StockStatutorySurplus`，需後端彙總。

## 7. 快速參考

| 項目 | URL |
|------|-----|
| 主入口 | `http://localhost:5000/` |
| 個股分析（帶個股） | `http://localhost:5000/#/taiwan-stock-analysis?stock_id=2330` |
| 回測（帶個股） | `http://localhost:5000/#/back-testing?stock_id=2330&autorun=1` |
| 觀察名單 | `http://localhost:5000/#/watchlist` |
| 量化報告 | `http://localhost:5000/quant/output/report.html` |
| 健康檢查 | `http://localhost:5000/api/health` |
| 個股清單 API | `http://localhost:5000/api/stock_list?q=2330` |
| 個股股價 API | `http://localhost:5000/api/stock_price?stock_id=2330&start_date=2025-01-01&end_date=2026-08-13` |
| 回測 API（POST） | `http://localhost:5000/api/backtest` |

## 8. 回測策略說明

支援 4 種策略，可組合觸發：

| 策略 | 預設參數 | 觸發邏輯 |
|------|---------|----------|
| MA 交叉 | 5 / 20 | MA短 > MA長 為黃金交叉（買），MA短 < MA長 為死亡交叉（賣） |
| RSI 超買超賣 | 14 / 30 / 70 | RSI < 30 為超賣（買），RSI > 70 為超買（賣） |
| KD 隨機指標 | 9 / 3 / 3 / 20 / 80 | K < 20 且 K > D 為超賣（買），K > 80 且 K < D 為超買（賣） |
| MACD 翻正翻負 | 12 / 26 / 9 | OSC 由負轉正（買），由正轉負（賣） |

**觸發模式**：
- OR：任一啟用策略觸發即動作
- AND：所有啟用策略都觸發才動作

**回測規則**：每次觸發「全部現金買進」或「全部庫存賣出」，不考慮部位管理。

**交易頻率**：
- `frequency`: `"day"`（預設，每個交易日都評估）或 `"month"`（僅在指定日期評估）
- `month_day`: 1–31（僅 frequency=month 生效）

## 9. Token 更新流程

```bash
# 1. 更新 token
echo "NEW_TOKEN" > data/finmind_token.txt
# 或：echo "FINMIND_TOKEN=NEW_TOKEN" >> ~/.env

# 2. 清除個股清單快取（讓新 token 立即驗證）
rm data/stock_list.json

# 3. 重啟 Flask
# Linux/Mac: Ctrl+C 砍掉 python app.py，再 python3 app.py
# Windows: 雙擊 scripts/stop.bat → start.bat
```

## 10. 已知限制

1. **無部位管理**：策略回測只支援全進全出
2. **個股清單快取 24h**：新增股票可能 24 小時後才會出現
3. **無即時股價**：FinMind 個股股價有 1 天延遲
4. **回測無費用**：Dashboard 端回測未考慮手續費 / 證交稅；量化有
5. **單 IP 單 token**：同 IP 使用多個 token 會被封鎖（已驗證）
6. **Flask dev server**：生產環境建議改用 gunicorn / uWSGI
7. **無 frontend build**：vanilla JS 改完直接刷新瀏覽器即可

## 11. 開發紀錄

- **2026-08-14 v2.0.0 大翻修**：PHP → Flask，獨立運作，5000 port
- **2026-08-14 v1.2 R3**：指標 tooltip（11 個 card）
- **2026-08-14 v1.2 R2**：Watchlist（localStorage）
- **2026-08-14 v1.2 R1**：成交量 bars + 程式碼清理
- **2026-08-14 v1.1**：自檢 11 項修復 + health / quant_pool API
- **2026-08-13 v1.0**：初版（PHP + Apache，含個股 + 回測 + 量化）
