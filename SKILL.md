# FinMind Dashboard Skill

## 1. 專案說明

基於 FinMind API 建立的台股個股分析 + 策略回測儀表板。

### 對應 FinMind 原版
| FinMind 原版 | 本專案頁面 | 路徑 |
|--------------|-----------|------|
| `#/dashboards/taiwan-stock-analysis` | 個股分析 | `#/taiwan-stock-analysis` |
| `#/dashboards/back-testing`        | 回測     | `#/back-testing`        |

## 2. 架構

```
/finmind/
├── index.php                # 主框架（sidebar + content），hash 路由
├── .htaccess                # 禁止存取 data/ lib/ config.php
├── config.php               # 讀 token（兩段式 fallback）
├── api/                     # 後端 PHP proxy（保護 FinMind token）
│   ├── stock_list.php       # 個股清單 + 搜尋（含 24h 快取）
│   ├── stock_price.php      # 歷史股價
│   ├── stock_per.php        # PER / PBR / 殖利率
│   ├── stock_revenue.php    # 月營收 + YoY 計算
│   ├── stock_finance.php    # 三大財報
│   ├── stock_dividend.php   # 配息（TaiwanStockDividend，單一 dataset）
│   ├── institutional.php    # 三大法人買賣超
│   ├── margin.php           # 融資融券
│   └── backtest.php         # 策略回測引擎
├── pages/                   # 子頁面 fragment
│   ├── analysis.php
│   └── backtest.php
├── assets/
│   ├── css/style.css        # GitHub Dark 主題（沿用 stock/ 風格）
│   ├── js/
│   │   ├── app.js           # 路由 / sidebar / 共用
│   │   ├── api.js           # API client
│   │   ├── indicators.js    # MA / RSI / KD / MACD 計算
│   │   ├── analysis.js      # 個股分析頁邏輯
│   │   └── backtest.js      # 回測頁邏輯
│   └── lib/chart.umd.js     # Chart.js 4.4.1（本地，無 CDN 依賴）
├── lib/
│   └── finmind.php          # FinMind API client class
└── data/
    ├── finmind_token.txt    # 容器內 token（受 .htaccess 403 保護）
    ├── stock_list.json      # 個股清單快取（24h TTL）
    └── backtest_results.json # 回測歷史（最多 50 筆）
```

## 3. 設計風格

- GitHub Dark 主題（與 `/stock/` 一致）：
  - 背景 `#0d1117`、卡片 `#161b22`、內層 `#21262d`、邊框 `#30363d`
  - 漲綠跌紅：`#3fb950` / `#f85149`
  - 強調色藍 `#58a6ff`、紫 `#8957e5`、橘 `#d29922`
- Sidebar 固定 240px 左側
- 前端：純 HTML + vanilla JS + Chart.js（無前端框架）
- 後端：PHP 8.1（原生，無框架）

## 4. 安全性

1. **Token 雙層防護**：
   - 讀取順序：`finmind/data/finmind_token.txt` → `~/.env` → 報錯
   - `.htaccess` 設 403 禁止 web 直接讀 `/data/` `/lib/` `/config.php`
2. **XSS 防護**：所有前端輸出經 `esc()` HTML entity 轉義
3. **錯誤處理**：PHP API 用 try/catch + json_error()，前端 Promise.allSettled 個別容忍失敗
4. **參數過濾**：URLSearchParams 過濾 undefined / null，避免「undefined」字串傳到 FinMind

## 5. FinMind Dataset 名稱（踩坑紀錄）

| 想拿的資料 | 正確 dataset 名稱 |
|-----------|-----------------|
| 個股基本資料 | `TaiwanStockInfo` |
| 歷史股價 | `TaiwanStockPrice` |
| 本益比 / 淨值比 / 殖利率 | `TaiwanStockPER` |
| 月營收 | `TaiwanStockMonthRevenue` |
| 配息（**單一 dataset**） | `TaiwanStockDividend`（不是 `TaiwanStockCashDividend` / `TaiwanStockStockDividend`！） |
| 三大法人 | `TaiwanStockInstitutionalInvestorsBuySell` |
| 融資融券 | `TaiwanStockMarginPurchaseShortSale` |

`TaiwanStockDividend` 欄位包含 `CashEarningsDistribution`、`CashStatutorySurplus`、`StockEarningsDistribution`、`StockStatutorySurplus`，需後端彙總。

## 6. 快速參考

| 項目 | URL |
|------|-----|
| 主入口 | `http://localhost/finmind/` |
| 個股分析（帶個股） | `http://localhost/finmind/#/taiwan-stock-analysis?stock_id=2330` |
| 回測（帶個股） | `http://localhost/finmind/#/back-testing?stock_id=2330&autorun=1` |
| 個股清單 API | `http://localhost/finmind/api/stock_list.php?q=2330` |
| 個股股價 API | `http://localhost/finmind/api/stock_price.php?stock_id=2330&start_date=2025-01-01&end_date=2026-08-12` |
| 回測 API（POST） | `http://localhost/finmind/api/backtest.php` |

## 7. 回測策略說明

支援 4 種策略，可組合觸發：

| 策略 | 預設參數 | 觸發邏輯 |
|------|---------|---------|
| MA 交叉 | 5 / 20 | MA短 > MA長 為黃金交叉（買），MA短 < MA長 為死亡交叉（賣） |
| RSI 超買超賣 | 14 / 30 / 70 | RSI < 30 為超賣（買），RSI > 70 為超買（賣） |
| KD 隨機指標 | 9 / 3 / 3 / 20 / 80 | K < 20 且 K > D 為超賣（買），K > 80 且 K < D 為超買（賣） |
| MACD 翻正翻負 | 12 / 26 / 9 | OSC 由負轉正（買），由正轉負（賣） |

**觸發模式**：
- OR：任一啟用的策略觸發即動作
- AND：所有啟用的策略都觸發才動作

**回測規則**：每次觸發「全部現金買進」或「全部庫存賣出」，不考慮部位管理。

**交易頻率**：
- `frequency`: `"day"` （預設，每個交易日都評估）或 `"month"`（僅在指定日期評估）
- `month_day`: 1–31（僅 frequency=month 生效，找該月內第一個交易日 ≥ 此日期；若整月都沒有，該月略過）

### 比較：2330 台積電 MA(5,20) 策略、2024-01-01 ~ 2026-08-12

| 頻率 | 動作日 | 交易次數 | 總報酬 | Buy & Hold |
|------|--------|----------|--------|-----------|
| 每日 | 631 | 33 | +106.76% | +307.19% |
| 每月 5 號 | 32 | 1 | +124.62% | +307.19% |
| 每月 15 號 | 31 | 2 | +9.75% | +307.19% |
| 每月 28 號 | 28 | 1 | +108.18% | +307.19% |

> 不同月分選日只評估那些特定日期是否觸發訊號，錯過的日子純持倉。交易次數會比每日少很多，但進場點會更精準（也可能完全沒有觸發）。

## 8. Token 更新流程

如果 token 過期：

```bash
# 1. 更新 .env
TOKEN="新 token"
echo $TOKEN > "/mnt/d/docker-volumn/ubuntu-apache2/html/finmind/data/finmind_token.txt"

# 2. 清除個股清單快取（讓新 token 重新驗證）
rm "/mnt/d/docker-volumn/ubuntu-apache2/html/finmind/data/stock_list.json"
```

## 9. 已知限制

1. **無部位管理**：回測只支援全進全出，不支援分批、停損、停利
2. **個股清單快取 24h**：新增股票可能 24 小時後才會出現在搜尋
3. **無即時股價**：FinMind 個股股價有 1 天延遲（daily 收盤後才更新）
4. **回測無費用**：未考慮手續費、證交稅、滑價
