# Changelog

## 2026-08-14 — v2.0.0 大翻修（PHP → Flask）

### Changed (BREAKING)

- **整個後端從 PHP + Apache 翻成 Python Flask 獨立運作**
  - 廢除：Apache 80 + Docker container + PHP API 11 個檔
  - 廢除：FastAPI 8765 子服務（量化改在 Flask 內 subprocess 跑）
  - 廢除：`$FINMIND_ENV_FILE` 環境變數（直接讀 `data/finmind_token.txt` 或 `~/.env`）
  - 廢除：`.htaccess`（改用 Flask 路由控制）
  - 新增：`app.py` 單一 Flask 入口（port 5000）
- **新版路徑**：
  - `/api/stock_list`（舊 `/finmind/api/stock_list.php`）
  - `/api/backtest`（舊 `/finmind/api/backtest.php`）
  - `/static/css/style.css`（舊 `/finmind/assets/css/style.css`）
  - `/quant/output/report.html`（舊 `/finmind/quant/output/report.html`）
- **位置**：從 `D:\docker-volumn\ubuntu-apache2\html\finmind\` 搬到 `D:\OneDrive - Sampo Corporation\3.Data\5.Python\finlab_tw_screener\`

### Added

- **觀察名單 Watchlist**（localStorage + 跨頁同步 + 移除按鈕）
- **指標教學 Tooltip**（11 個 card 自動綁定，hover 顯示說明）
- **健康檢查 `/api/health`**（token / 套件 / cache / 報告 — 200/503）
- **量化狀態 `/api/quant_status`**（KPI / 區間 / 最後更新 / 是否在跑）
- **量化股票池 `/api/quant_pool`**（26 檔預設，讀 `quant/pool.json` 可自訂）
- **app_config.py**（統一設定，token 兩段式讀取）
- **lib/finmind.py**（從 PHP 移植，帶 200ms thread-safe rate-limit）
- **lib/backtest.py**（從 PHP 移植，純 Python 指標計算）
- **lib/quant_runner.py**（subprocess + lock file 防並發）
- **scripts/start.bat / stop.bat / status.bat**（Windows 啟動 / 停止 / 狀態查詢）

### Improved

- **後端 `/api/backtest` 補預設值**：API 端自動補 ma / rsi / kd / macd 預設，避免 client 只給部分策略時 keyerror
- **前端 `static/js/api.js`**：`base` 從 `/finmind/api` 改成 `/api`，拿掉所有 `.php`
- **GitHub Dark 主題 + tooltip 樣式**：完整沿用並補上 `.tip-trigger` / `.tip-bubble` CSS

### Removed

- 舊 PHP 檔案（`index.php` / `config.php` / `api/*.php` / `pages/*.php` / `lib/finmind.php`）
- `.htaccess`（不再需要）
- `assets/` → 改名 `static/`
- `quant/server.py`（FastAPI 子服務，併入 `lib/quant_runner.py`）

### Verified

- ✅ 12 個 API 端點全綠（GET / POST）
- ✅ 個股清單 3134 檔（含 ETF）
- ✅ 2330 各 API 正常回傳
- ✅ Backtest MA(5,20) 2025-01-01 ~ 2026-08-13：策略 +91.01%，年化 49.44%，MDD -11.47%
- ✅ Quant 23 檔跑 90.7s 完整跑完，策略 +1193.04%，B&H +153.71%，Sharpe 1.52
- ✅ Quant report.html 158KB 正確產出
- ✅ Health：所有 token / 套件 / cache / report 檢查 OK

---

## 2026-08-14 — v1.2 Watchlist + Indicator tooltip

### Added

- **觀察名單 Watchlist**（localStorage `finmind.watchlist.v1`）
- **指標教學 ⓘ tooltip**（11 個 card 自動綁定）

## 2026-08-14 — v1.2 R1 成交量 bars + 程式碼清理

### Added

- `analysis.js` 獨立的成交量 chart（volumeChart）

### Fixed

- `quant.py` `MIN_LIQUIDITY_SHARES=0` 三元式改寫（可讀性）

## 2026-08-14 — v1.1 自我檢查 11 項修復

### Fixed

- backtest AND/OR 邏輯（移除 dead code）
- `report.py` 股票池大小（讀 `pool.load_pool()` 而非 `config.STOCK_POOL`）
- `quant.js` DEFAULT_POOL 同步（從 26 改為改從 `/api/quant_pool` 拉）
- `config.php` `.env` 引號處理（剝單/雙引號）
- `update_data.bat` Windows 相容性（呼叫 `wsl bash -c`）
- `quant_status.php` 顯示回測區間
- `lib/finmind.php` 搜尋排序（5-tier relevance）
- `pool_list` 空白處理
- backtest 輸入驗證（capital / 日期）
- `main.py` logging 顯示 INFO
- `api/quant_pool.php` API（新增）

### Added

- `api/health.php`（新增）
- `CHANGELOG.md`（本檔）

## 2026-08-13 — v1.0 初版

- Dashboard（PHP + vanilla JS + Chart.js）：個股搜尋、技術指標（MA / RSI / KD / MACD）、基本面（PER / PBR / 殖利率）、月營收 YoY、法人買賣超、融資融券、配息歷史、單股回測（4 種策略 + AND / OR + 頻率）
- Quant 模組（Python）：3 因子（價值 40% / 動能 30% / 品質 30%）月頻調倉、Top 5 等權重、手續費 + 證交稅、Plotly HTML 報告、0050 含息 benchmark
- 雙層 FinMind token（容器 `data/finmind_token.txt` + host `.env` 經 `FINMIND_ENV_FILE`）
- per-stock parquet 快取（`quant/cache/historical/{price,per,fin}/{stock_id}.parquet`）
- 部署驗證 `scripts/verify_deploy.sh`
