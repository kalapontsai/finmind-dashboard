# 股票組合歷史回測 + 未來 N 年終值情境工具

## 1. 專案目的

本工具用於分析「一籃子股票」的歷史總報酬，並以歷史資料中的 **N-Year Rolling CAGR 分布**建立未來 N 年後的情境估計。

核心定位不是逐年預測股價，也不是聲稱可以精準預測未來，而是回答：

> 如果目前這一籃子股票在未來持有 N 年，歷史上相同長度的投資期間曾經出現什麼樣的報酬結果？

因此 Forecast 只輸出 **N 年後的終值情境**，不建立未來每一年的模擬路徑。

---

## 2. 分析架構

```text
CSV 股票價格資料
        │
        ▼
資料清理 / 日期排序 / 股票代號整理
        │
        ▼
三種歷史回測模式
 ┌──────────────┬────────────────┬──────────────────┐
 │ Common       │ Dynamic Entry  │ Full Available   │
 │ Period       │                │ History          │
 └──────────────┴────────────────┴──────────────────┘
        │
        ▼
Portfolio Daily Return
        │
        ▼
Portfolio NAV
        │
        ├── Total Return
        ├── CAGR
        ├── MDD
        ├── Volatility
        └── Sharpe
        │
        ▼
Historical N-Year Rolling CAGR
        │
        ▼
P10 / P25 / P50 / P75 / P90
        │
        ▼
Future N-Year Terminal Value
```

---

## 3. 三種歷史回測模式

### 3.1 Common Period

找出所有股票共同具有有效價格資料的期間，只在共同期間內進行組合回測。

用途：

- 公平比較不同股票
- 避免某些股票因歷史資料較短而取得額外時間優勢
- 最適合做「一籃子股票歷史績效」的主要比較

公式：

\[
R_{p,t}=\sum_i w_iR_{i,t}
\]

\[
NAV_t=NAV_{t-1}(1+R_{p,t})
\]

預設使用等權重；如果指定權重，則對有效股票權重重新標準化。

---

### 3.2 Dynamic Entry

每一支股票從其第一個有效價格開始加入組合。

某一天只有部分股票有報酬資料時，只對當天可觀測股票重新正規化權重。

用途：

- 模擬股票逐步進入資料集合的情境
- 分析不同股票歷史長度對組合績效的影響

注意：這是一種研究定義，不代表真實交易一定會採用完全相同的進場規則。

---

### 3.3 Full Available History

利用每支股票可取得的歷史資料；當某股票尚無有效資料時，不使用該股票的報酬，並將當日有效股票權重重新正規化。

用途：

- 個股歷史資料診斷
- 觀察整個股票池在「各自可觀測期間」下的表現

不應直接把這個結果解讀成嚴格的 Point-in-Time 歷史投資策略。

---

## 4. 股票歷史長度問題

本工具假設：

> 股票池中的股票本身都屬於研究對象；問題只有歷史資料長短不同。

因此：

- 尚未出現資料的日期不是 0% 報酬
- 不會將不存在的歷史資料填成 0%
- 不會把短期報酬強制外推成完整歷史
- 不會因為歷史短就自動刪除股票

報表會顯示：

- 股票數
- 最短歷史年數
- 中位數歷史年數
- 最長歷史年數

---

## 5. 未來 N 年 Forecast

### 5.1 基本概念

使用歷史 Portfolio NAV 建立所有可取得的 N-Year rolling periods。

例如：

```text
N = 10

2010 → 2020
2011 → 2021
2012 → 2022
2013 → 2023
...
```

每一段計算：

\[
CAGR_N=
\left(\frac{NAV_{end}}{NAV_{start}}\right)^{1/years}-1
\]

再將全部歷史 N-Year CAGR 排序，取得：

- P10：Bear
- P25：Conservative
- P50：Base
- P75：Optimistic
- P90：Bull

---

### 5.2 N 年後終值

使用：

\[
FV_N=PV(1+r_N)^N
\]

其中：

- \(PV\)：目前資產
- \(r_N\)：歷史 N-Year CAGR 對應分位數
- \(N\)：使用者指定的未來年數

例如目前資產為 10,000,000，N=10：

```text
P10 CAGR → Bear
P25 CAGR → Conservative
P50 CAGR → Base
P75 CAGR → Optimistic
P90 CAGR → Bull
```

---

## 6. 為什麼不直接使用個股 CAGR 平均？

不採用：

\[
Portfolio\ CAGR=
\frac{CAGR_1+CAGR_2+\cdots+CAGR_n}{n}
\]

原因是 CAGR 不是可以直接做算術平均後代表組合 CAGR 的每日報酬量。

本工具先：

```text
個股價格
→ 個股報酬
→ Portfolio Daily Return
→ Portfolio NAV
→ Portfolio CAGR
```

再從 Portfolio NAV 建立 N-Year rolling outcome。

這樣比較符合「一籃子股票總報酬」的定義。

---

## 7. CSV 格式

最少需要三個欄位：

```csv
Date,Ticker,Adj_Close
2020-01-02,2330,332.5
2020-01-02,2317,78.2
2020-01-02,2454,334.0
```

支援欄位名稱：

### 日期

- Date
- Datetime
- Time

### 股票代號

- Ticker
- Symbol
- Code
- Stock

### 價格

- Adj_Close
- Adjusted_Close
- Close
- Price

正式回測建議優先使用 **Adjusted Close / Total Return Price**，以避免除權息與股票分割造成錯誤。

---

## 8. 權重

若未輸入權重：

```text
等權重
```

例如 4 支股票：

```text
25%
25%
25%
25%
```

也可以指定：

```text
2330:0.25,2317:0.25,2454:0.25,2881:0.25
```

指定權重不一定要總和為 1，程式會標準化。

---

## 9. 安裝

需要 Python 3.10+。

```bash
pip install -r requirements.txt
```

啟動：

```bash
python app.py
```

瀏覽器：

```text
http://127.0.0.1:5000
```

---

## 10. API

### POST `/api/analyze`

輸入：

- `file`: CSV
- `mode`: common / dynamic / full
- `n`: 未來 N 年
- `initial_value`: 目前資產
- `weights`: 選填

輸出 JSON：

```text
metrics
forecast
rolling_count
history
nav
rolling
```

---

## 11. 目前版本的研究限制

本版本是「歷史回測 + 終點情境估計」核心版本，以下功能尚未納入：

- 手續費
- 稅費
- 滑價
- 股利現金流的獨立拆解
- Point-in-Time 股票池
- 下市股票資料
- ETF 成分股歷史還原
- 股票分割與除權息資料品質驗證
- 交易再平衡成本
- 多幣別
- 無風險利率的動態設定
- Bootstrap / Monte Carlo
- 信賴區間與樣本不確定性校正

因此輸出的未來 N 年結果應視為：

> **歷史情境參考，而非精準的未來價格預測。**

---

## 12. 建議的研究解讀方式

如果：

```text
P10 = 3%
P50 = 10%
P90 = 18%
```

不要解讀成：

> 未來一定介於 3%～18%。

正確解讀應為：

> 在目前歷史樣本中，具有相同 N 年長度的 rolling periods，其 CAGR 分布約落在這個範圍。

這個差異非常重要。

---

## 13. 建議的正式驗證流程

建議至少比較：

1. Common Period
2. Dynamic Entry
3. Full Available History

並比較：

- CAGR
- Total Return
- MDD
- Sharpe
- N-Year rolling CAGR distribution
- P10 / P25 / P50 / P75 / P90

如果不同方法得到的結論一致，結果可信度相對較高。

---

## 14. 專案定位

本工具應定位為：

**Portfolio Historical Backtest + Historical N-Year Outcome Scenario Tool**

而不是：

**Stock Price Prediction Engine**

核心目標是：

> 用歷史資料回答「這個投資組合在相同投資期間曾經發生什麼」，再將結果轉換成 N 年後的情境終值。
