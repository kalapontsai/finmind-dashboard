# FinMind Dashboard v2.0

台股個股分析 + 策略回測 + 多因子量化儀表板，基於 [FinMind](https://finmindtrade.com/) API。

**v2.0 大翻修**：從 PHP + Apache 架構 → Python Flask 獨立運作，單一 process 整合所有功能。

---

## 特色

### Dashboard（個股 / 策略）
- **個股分析**：K 線 + MA / RSI / KD / MACD 副圖、PER / PBR / 殖利率、月營收 YoY、三大法人、融資融券、配息歷史
- **策略回測**：MA / RSI / KD / MACD 任選組合、AND / OR 觸發模式、每日 / 每月指定日頻率
- **指標教學**：每張 card 標題旁 ⓘ tooltip，hover 顯示簡短說明
- **觀察名單**：localStorage 自選股追蹤、加入 / 移除按鈕、跨頁面同步

### 量化（多因子）
- 3 因子綜合評分：**價值 40% / 動能 30% / 品質 30%**
- 每月第一個交易日換倉，選出總分前 5 檔等權重
- 0050 含息 benchmark 對照
- 手續費 0.1425% + 證交稅 0.3% 計入
- Plotly 互動式 HTML 報告

### 視覺
- GitHub Dark 主題（`#0d1117` / `#161b22` / 卡片 `#21262d`）
- 純 vanilla JS + Chart.js（無前端框架）
- Sidebar 240px 固定左側

---

## 啟動

### 1. 安裝

```bash
# 系統需求：Python 3.10+
pip install Flask pandas numpy plotly pyarrow requests FinMind
```

### 2. 設定 FinMind Token

兩種方式（擇一）：

```bash
# 方式 A：放在 data/finmind_token.txt（容器 / 部署用）
echo "YOUR_TOKEN" > data/finmind_token.txt

# 方式 B：放在 ~/.env
echo "FINMIND_TOKEN=YOUR_TOKEN" >> ~/.env
```

### 3. 啟動

```bash
python3 app.py
# → http://localhost:5000/
```

或 Windows 雙擊 `scripts/start.bat`。

### 4. 健康檢查

```bash
curl http://localhost:5000/api/health
# → {"ok": true, "checks": {...}}
```

---

## 與舊版（v1.x）差別

| 項目 | 舊版（PHP + Apache） | 新版（Flask） |
|------|---------------------|--------------|
| 框架 | 原生 PHP + Apache 80 | Flask 5000（單一 process） |
| 部署 | 容器 + Apache 模組 | 任意 Python 環境 |
| 量化 | FastAPI 8765 子服務 + @reboot cron | Flask 內 subprocess 跑 |
| Token 雙層 | container 檔 + `$FINMIND_ENV_FILE` env | `data/finmind_token.txt` + `~/.env` |
| 安全 | `.htaccess` 403 | Flask 路由控制 |
| 啟動 | 容器自動 + 外部 cron | `python3 app.py` 前景 |
| 觀察名單 | ❌ | ✅（localStorage） |
| 指標 tooltip | ❌ | ✅（11 個 card） |
| 健康檢查 | ❌ | ✅（`/api/health`） |

---

## 目錄結構

```
finmind-dashboard/
├── app.py                        # Flask 入口（單一 process）
├── app_config.py                 # 設定（token / 路徑 / FlaskConfig）
│
├── lib/                          # 共用模組
│   ├── finmind.py                # FinMind API client（requests + 200ms rate-limit）
│   ├── backtest.py               # 策略回測引擎（MA / RSI / KD / MACD + AND/OR）
│   └── quant_runner.py           # 量化背景跑（subprocess + lock file）
│
├── routes/                       # Flask blueprints
│   ├── views.py                  # 頁面（/、/quant/output/）
│   └── api.py                    # REST API（12 個端點）
│
├── templates/                    # Jinja2
│   └── base.html                 # 主框架（sidebar + content + hash 路由）
│
├── static/                       # 靜態資源
│   ├── css/style.css             # GitHub Dark（+ tooltip 樣式）
│   ├── js/                       # 前端（api / indicators / analysis / backtest / quant / watchlist / tooltip / app）
│   └── lib/chart.umd.js          # Chart.js 4.4.1（本地）
│
├── quant/                        # 多因子量化（從舊版搬進來）
│   ├── main.py                   # 入口
│   ├── quant.py / report.py / config.py
│   ├── SKILL.md
│   ├── cache/                    # parquet 快取（gitignore）
│   └── output/                   # report.html + backtest_results.json（gitignore）
│
├── data/                         # 應用資料
│   ├── finmind_token.txt         # gitignore（容器 / 部署 token）
│   ├── stock_list.json           # gitignore（24h 個股清單快取）
│   └── backtest_results.json     # gitignore（回測歷史）
│
├── scripts/                      # Windows 啟動腳本
│   ├── start.bat                 # 啟動 Flask（CRLF）
│   ├── stop.bat                  # 砍 python app.py
│   └── status.bat                # 查狀態
│
├── .gitignore
├── README.md                     # 本檔
├── SKILL.md                      # 工程筆記
├── CHANGELOG.md                  # 版本歷史
└── LICENSE                       # MIT
```

---

## API 端點

### 個股分析
| Method | URL | 說明 |
|--------|-----|------|
| GET | `/api/stock_list?q=2330` | 個股清單 + 搜尋（5-tier relevance） |
| GET | `/api/stock_price?stock_id=2330&start_date=...&end_date=...` | 歷史股價 |
| GET | `/api/stock_per?stock_id=2330` | PER / PBR / 殖利率 |
| GET | `/api/stock_revenue?stock_id=2330` | 月營收（含 YoY 計算） |
| GET | `/api/stock_finance?stock_id=2330` | 三大財報 |
| GET | `/api/stock_dividend?stock_id=2330` | 配息（年份彙總） |
| GET | `/api/institutional?stock_id=2330` | 三大法人買賣超 |
| GET | `/api/margin?stock_id=2330` | 融資融券 |

### 策略 / 量化
| Method | URL | 說明 |
|--------|-----|------|
| POST | `/api/backtest` | 策略回測（MA / RSI / KD / MACD + AND/OR + 頻率） |
| POST | `/api/quant_run` | 觸發多因子量化回測（背景跑 1-3 分鐘） |
| GET | `/api/quant_status` | 量化狀態（KPI / 區間 / 最後更新） |
| GET | `/api/quant_pool` | 預設股票池（26 檔） |

### 系統
| Method | URL | 說明 |
|--------|-----|------|
| GET | `/api/health` | 健康檢查（token / 套件 / cache） |
| GET | `/quant/output/report.html` | 量化報告（Flask serve） |
| GET | `/` | 主頁面（hash 路由 SPA） |

---

## 快速參考

| 項目 | URL |
|------|-----|
| 主入口 | `http://localhost:5000/` |
| 個股分析（帶個股） | `http://localhost:5000/#/taiwan-stock-analysis?stock_id=2330` |
| 回測（帶個股） | `http://localhost:5000/#/back-testing?stock_id=2330&autorun=1` |
| 觀察名單 | `http://localhost:5000/#/watchlist` |
| 量化報告 | `http://localhost:5000/quant/output/report.html` |
| 健康檢查 | `http://localhost:5000/api/health` |

---

## 已知限制

1. **回測無部位管理**：每次觸發「全部現金買入」或「全部庫存賣出」，不支援分批、停損、停利
2. **個股清單快取 24h**：新增股票可能 24 小時後才會出現
3. **無即時股價**：FinMind 個股股價有 1 天延遲
4. **回測無費用**：策略回測未考慮手續費 / 證交稅（量化有）
5. **單 IP 單 token**：同 IP 使用多個 token 會被封鎖（已驗證）

---

## 授權

MIT — 詳見 [LICENSE](LICENSE) 檔。
