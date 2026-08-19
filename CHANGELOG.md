# Changelog

## 2026-08-19 — v1.0 Portfolio Forecast 大翻修

### Changed (BREAKING)

- **架構從單檔翻成模組化**
  - `app.py` — Flask 入口（單一 process，5000 port）
  - `app_config.py` — 路徑 / 預設值
  - `lib/finmind.py` — FinMind API client（200ms rate-limit + 24h cache + ticker 自動補 0 試 variants）
  - `lib/csv_loader.py` — 用戶名單 CSV 解析（Ticker / 代號 / 股票代號 / Symbol 多別名 + 千分位）
  - `lib/portfolio.py` — 3 模式 (Common / Dynamic / Full) + 指標 + 個股歷史診斷
  - `lib/forecast.py` — N-Year rolling CAGR + P10..P90 + 終值
  - `lib/exporter.py` — HTML (Jinja2) + PDF (reportlab) 報告匯出
  - `templates/index.html` — 主頁（輸入 / 結果 / 三模式 tab / 圖表）
  - `templates/report.html` — 報告模板（Jinja2）
  - `static/css/style.css` + `static/js/portfolio.js` — 前端樣式 / 邏輯
  - `tests/` — 31 個 pytest 案例（4 個檔）

### Added

- **讀用戶名單 CSV**（不再是預先整理好的 Date+Ticker+Price CSV）
  - 範例：`user_profile/liyu_stock.csv`（31 筆，欄位 Ticker, Shares）
  - 自動認欄位別名：`代號 / 股票代號 / Ticker / Symbol`
  - 自動剝千分位逗號（`"21,315"` → `21315`）
  - 支援無 header（兩欄式）

- **FinMind 整合**
  - Token 兩段式：`config/finmind-api-key` → `~/.env` 的 `FINMIND_TOKEN`
  - 200ms thread-safe rate-limit
  - 24h 價格快取（`data/price_cache/<ticker>.json`）
  - 自動試 ticker variants：原文 / 補 0 到 4 碼 / 補 0 到 6 碼 / upper
  - 單股壞資料（return=inf）容錯：自動視為 NaN，不污染整個組合
  - 個股抓不到資料：跳過並記在 `inputs.fetch_errors`，不中斷整批

- **3 模式歷史回測**
  - **Common Period** — 共同期間，等權重（可自訂），公平比較
  - **Dynamic Entry** — 股票有資料才加入，權重每日重新正規化
  - **Full Available History** — 每支股票從自己最早資料開始算
  - 共同期間 + Dynamic / Full 都有「每日 active 股票數」診斷
  - 個股歷史長度摘要（最短 / 中位 / 最長 + per-stock 年數）

- **N-Year 終值情境估計**
  - 從 Portfolio NAV 建立所有 N-Year rolling periods
  - P10 / P25 / P50 / P75 / P90 對應 Bear / Conservative / Base / Optimistic / Bull
  - `FV = PV × (1+r)^N`
  - 自動選 baseline：Common → Dynamic → Full（取 rolling_count 最大的）
  - 在 response 中標記 `forecast.basis`（哪個模式算的）

- **HTML / PDF 匯出**
  - HTML：Jinja2 模板，self-contained，可瀏覽器開 / 列印
  - PDF：reportlab Platypus，含中文字型（STSong-Light）、表格、配色、Base 高亮
  - 透過 `/api/export` + `/data/reports/<filename>` 靜態下載

- **API（5 個端點）**
  - `GET  /` — 主頁
  - `GET  /api/health` — 健康檢查
  - `GET  /api/profiles` — 列出 `user_profile/*.csv`
  - `GET  /api/profile/<name>` — 預覽單檔名單
  - `POST /api/analyze` — 主分析（接收 profile / n / pv / weights）
  - `POST /api/export` — 匯出 HTML / PDF

- **研究紀律（繼承自舊版）**
  - 不把缺資料視為 0% 報酬（NaN 處理）
  - 不用短期 CAGR 外推完整歷史
  - 不直接平均個股 CAGR（從 Portfolio NAV 算）
  - Forecast 標示為「歷史 N-Year 持有期間曾經出現的結果分布」，不預測逐年路徑

### Improved

- **錯誤訊息人性化**：所有錯誤回傳明確中文訊息
- **Ticker 正規化**：自動補 0（解決 `50` vs `0050` vs `006208` 的常見 typo）
- **PDF 中文字型**：用 reportlab 內建 STSong-Light（無需裝額外字型）
- **前端互動**：tab 切換、loading status、即時錯誤提示、匯出按鈕

### Verified

- ✅ 31 個 pytest 全綠（csv_loader / portfolio / forecast / exporter）
- ✅ Flask 8 個 routes 全註冊
- ✅ 端對端：liyu_stock.csv 31 筆 → FinMind 抓價 → 三模式 + forecast → PDF/HTML 匯出
- ✅ Common period 6 個月（user 名單含 692 / 713 等新股票）
- ✅ Dynamic / Full 26.6 年（2000-01-04 → 2026-08-19），4143 個 N=10 rolling 樣本
- ✅ Forecast P10/P50/P90 = 0.10% / 2.68% / 5.99% CAGR（10 年情境）
- ✅ PDF 7.2KB，3 頁；HTML 7.2KB
- ✅ Health check：token / pandas / reportlab / profile_csvs 全綠

### Known Limits

- 共用 FinMind 600/hr 額度：31 檔首次抓約 6 秒（200ms rate-limit × 31）
- ETF（4 碼 0050 / 6 碼含字母 00980A）需確認 FinMind 是否有資料
- FinMind 對少數個股偶爾回傳壞資料（價格跳 100x），已自動視為 NaN 但可能影響該股貢獻
- 共同期間若 < N 年，自動退回 Dynamic / Full（response 有 `forecast.basis` 標記）
