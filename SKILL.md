# SKILL.md
# 股票組合歷史回測 + 未來 N 年終值情境分析 Skill

## 1. Skill 名稱

`stock_portfolio_backtest_forecast`

---

## 2. 目的

建立一個可重複執行的股票組合分析流程：

1. 讀取大量股票歷史價格資料。
2. 處理不同股票歷史資料長度。
3. 建立 Portfolio NAV。
4. 計算歷史總報酬與風險指標。
5. 建立 N-Year Rolling CAGR Distribution。
6. 只推估未來 N 年「終點」結果。
7. 不模擬未來每一年的價格路徑。
8. 將結果輸出到 HTML 前端或 JSON API。

---

## 3. 核心研究原則

### 3.1 不把缺少歷史資料視為 0% 報酬

若某股票在某日期沒有資料：

```text
NaN / Not Observable
```

不可直接轉換為：

```text
0%
```

否則會把「沒有資料」錯誤解讀為「價格沒有變動」。

---

### 3.2 不用短期 CAGR 強制外推完整歷史

例如：

```text
股票 A：15 年資料
股票 B：3 年資料
```

不能因為 B 只有 3 年，就將 3 年 CAGR 假設成 15 年歷史 CAGR。

應保留實際觀測期間。

---

### 3.3 不直接平均個股 CAGR

禁止：

```text
portfolio_cagr = mean(stock_cagr)
```

Portfolio CAGR 必須由 Portfolio NAV 計算。

---

### 3.4 Forecast 不是價格預測

Forecast 的定義：

> 根據歷史上相同長度的 N-Year rolling CAGR distribution，建立 N 年後終值情境。

不可將結果描述為：

> 「未來一定報酬 X%。」

---

# 4. Input Specification

## 4.1 Required CSV

```csv
Date,Ticker,Adj_Close
```

支援：

### Date

```text
Date
Datetime
Time
```

### Ticker

```text
Ticker
Symbol
Code
Stock
```

### Price

```text
Adj_Close
Adjusted_Close
Close
Price
```

---

## 4.2 Data normalization

必須：

1. 日期轉 datetime。
2. 價格轉 numeric。
3. 股票代號轉 string。
4. 移除日期、Ticker、Price 缺失資料。
5. 按 Date、Ticker 排序。
6. 同一 Date + Ticker 重複資料只保留最後一筆。

---

# 5. Portfolio Construction

## 5.1 Equal Weight

沒有指定權重時：

\[
w_i=\frac{1}{N}
\]

---

## 5.2 Custom Weight

輸入：

```text
2330:0.25,2317:0.25,2454:0.25,2881:0.25
```

先建立權重向量，再 normalize：

\[
w_i'=\frac{w_i}{\sum w_i}
\]

---

# 6. Historical Modes

## 6.1 Common Period

目的：

> 公平比較所有股票共同存在的歷史期間。

流程：

```text
price matrix
→ 每支股票找第一個有效日期
→ 取所有股票 first_valid date 的最大值
→ 從此日期開始
→ 刪除仍不完整的股票
→ 建立 Portfolio
```

Portfolio return：

\[
R_{p,t}=\sum_i w_iR_{i,t}
\]

---

## 6.2 Dynamic Entry

目的：

> 股票有歷史資料後才加入 Portfolio。

每一日：

```text
valid stocks = 當日具有有效 return 的股票
```

重新正規化：

\[
w_{i,t}'=
\frac{w_i}{\sum_{j\in V_t}w_j}
\]

Portfolio return：

\[
R_{p,t}=\sum_{i\in V_t}w_{i,t}'R_{i,t}
\]

---

## 6.3 Full Available History

目的：

> 使用各股票實際可觀測歷史。

同樣只對當日有效股票進行權重正規化。

注意：

此模式不是嚴格的 Point-in-Time 股票池回測。

---

# 7. Portfolio NAV

初始：

\[
NAV_0=1
\]

每日：

\[
NAV_t=NAV_{t-1}(1+R_{p,t})
\]

---

# 8. Historical Metrics

## 8.1 Total Return

\[
TotalReturn=\frac{NAV_T}{NAV_0}-1
\]

若 NAV 初始設定為 1：

\[
TotalReturn=NAV_T-1
\]

---

## 8.2 CAGR

\[
CAGR=
\left(\frac{NAV_T}{NAV_0}\right)^{1/Y}-1
\]

其中：

\[
Y=\frac{days}{365.25}
\]

---

## 8.3 Maximum Drawdown

Running peak：

\[
Peak_t=\max(NAV_0,\ldots,NAV_t)
\]

Drawdown：

\[
DD_t=\frac{NAV_t}{Peak_t}-1
\]

Maximum Drawdown：

\[
MDD=\min(DD_t)
\]

---

## 8.4 Volatility

以日報酬：

\[
\sigma_{annual}=\sigma_{daily}\sqrt{252}
\]

---

## 8.5 Sharpe

目前版本預設無風險利率為 0：

\[
Sharpe=
\frac{\bar R_{daily}}{\sigma_{daily}}\sqrt{252}
\]

正式版本如加入無風險利率，必須明確標示計算方式。

---

# 9. Future N-Year Outcome Forecast

## 9.1 Input

```text
N = 1, 2, 3, ..., 50
PV = current portfolio value
```

---

## 9.2 Rolling N-Year Period

從 Portfolio NAV 建立歷史 rolling periods。

例如：

```text
N = 10

2010 → 2020
2011 → 2021
2012 → 2022
...
```

不要求建立未來逐年資料。

---

## 9.3 Rolling CAGR

每個 period：

\[
CAGR_N=
\left(\frac{NAV_{end}}{NAV_{start}}\right)^{1/Y}-1
\]

其中：

\[
Y=\frac{days}{365.25}
\]

若實際期間太短，避免誤認為完整 N 年。

目前實作允許的判定：

\[
Y\ge0.95N
\]

正式版本可以將 tolerance 變成 config。

---

# 10. Scenario Percentiles

對所有 Rolling N-Year CAGR：

```text
P10
P25
P50
P75
P90
```

映射：

| Percentile | Scenario |
|---:|---|
| P10 | Bear |
| P25 | Conservative |
| P50 | Base |
| P75 | Optimistic |
| P90 | Bull |

---

# 11. Future Terminal Value

\[
FV_N=PV(1+r_N)^N
\]

其中：

- PV = current portfolio value
- rN = selected historical rolling CAGR percentile
- N = forecast years

---

# 12. Forecast Interpretation

必須使用以下語意：

> 歷史 N-Year Outcome Scenario

而不是：

> Guaranteed Future Return

或：

> Accurate Stock Price Prediction

結果只能表示：

> 歷史樣本中，相同持有期間曾經出現的結果分布。

---

# 13. Short History Handling

## 個股歷史摘要

必須提供：

```text
stock_count
min_history_years
median_history_years
max_history_years
```

---

## 不足歷史

若：

```text
available_history < N
```

則該股票不應被硬補成 N 年資料。

Common Period 模式可能直接無法產生 N-Year rolling outcome。

這時應回傳明確錯誤：

```text
歷史資料不足以建立 N 年 rolling outcome
```

---

# 14. Frontend Requirements

HTML 前端至少提供：

### Input

- CSV Upload
- Mode Selection
- N Years
- Initial Portfolio Value
- Optional Weights

### Output

#### Historical KPI

- Total Return
- CAGR
- MDD
- Volatility
- Sharpe

#### Charts

1. Portfolio NAV
2. Rolling N-Year CAGR

#### Forecast Table

- Scenario
- Historical N-Year CAGR
- Current Value
- Future Value
- Multiple

#### History Diagnostics

- Stock count
- Minimum history
- Median history
- Maximum history

---

# 15. Flask API

Endpoint：

```http
POST /api/analyze
```

Form parameters：

```text
file
mode
n
initial_value
weights
```

Response 必須至少包含：

```json
{
  "mode": "common",
  "n": 10,
  "initial_value": 10000000,
  "metrics": {},
  "forecast": [],
  "rolling_count": 0,
  "history": {},
  "nav": [],
  "rolling": []
}
```

錯誤：

```json
{
  "error": "error message"
}
```

HTTP status：

```text
400
```

---

# 16. Quality Checks

程式開發完成後至少驗證：

### Data

- CSV 可讀
- Date 可解析
- Price 為 numeric
- Ticker 不為空
- 沒有重複 Date/Ticker

### Portfolio

- 權重總和 normalize 後為 1
- NAV 不應因正常正報酬變成負值
- Daily Return 計算正確

### Forecast

- N > 0
- rolling samples > 0
- P10 <= P25 <= P50 <= P75 <= P90
- Future Value 與 CAGR 公式一致

---

# 17. Research Validation

至少進行三種模式比較：

```text
Common Period
Dynamic Entry
Full Available History
```

比較：

```text
CAGR
Total Return
MDD
Sharpe
N-Year Rolling Distribution
P10/P25/P50/P75/P90
```

如果結論差異很大，必須在報告中標示：

> 結果對歷史期間定義敏感。

---

# 18. Survivorship Bias

如果股票池是「2026 年市值 Top 100」，回測 2016～2025：

這本身可能存在：

> Survivorship Bias

原因：

2026 年仍存活且市值最大的公司，被拿回過去測試。

本 Skill 不自動消除 Survivorship Bias。

正式 Point-in-Time Backtest 必須使用每個歷史日期當時可取得的股票池。

因此報告必須清楚標示：

```text
Universe Definition Date
Backtest Period
Survivorship Bias Risk
```

---

# 19. Look-Ahead Bias

任何股票排名、權重或選股條件，都不可使用回測當時尚未知道的未來資訊。

例如：

```text
2026 Top 100
```

不能直接宣稱：

```text
2016 年投資人當時就知道這 100 支股票
```

因此：

> Fixed 2026 Universe 回測

與：

> Point-in-Time Strategy Backtest

必須分開。

---

# 20. Recommended Extensions

後續版本可加入：

1. Point-in-Time Universe
2. Survivorship Bias correction
3. Delisted stocks
4. Corporate actions validation
5. Dividend / Total Return Index
6. Transaction costs
7. Taxes
8. Slippage
9. Rebalancing frequency
10. Benchmark comparison
11. Bootstrap confidence interval
12. Monte Carlo
13. Excel export
14. HTML report export
15. PDF report
16. Multi-portfolio comparison
17. Batch processing
18. Parameter sensitivity analysis

---

# 21. Development Rule

任何新增功能都必須維持以下原則：

```text
歷史資料
    ↓
可驗證的 Portfolio Return
    ↓
NAV
    ↓
Historical Metrics
    ↓
Historical N-Year Distribution
    ↓
Terminal Scenario
```

不要將：

```text
歷史 CAGR
```

直接解讀成：

```text
未來 CAGR
```

也不要把：

```text
Forecast Scenario
```

包裝成：

```text
Price Prediction
```

---

# 22. Final Output Definition

本 Skill 最終應產生：

### Historical

```text
Portfolio Total Return
Portfolio CAGR
MDD
Volatility
Sharpe
```

### Future N-Year

```text
Bear P10
Conservative P25
Base P50
Optimistic P75
Bull P90
```

### Terminal Value

```text
FV = PV × (1+r)^N
```

核心原則：

> **只預測 N 年後的終點，不預測中間每一年。**
