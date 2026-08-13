# FinMind 多因子量化回測 Skill

## 1. 用途

台股多因子量化回測工具，基於 FinMind Python 套件（`FinMind.data.DataLoader`）。

**3 因子**：
- 價值因子（40%）：`TaiwanStockPER` 的 PER（本益比），越低越好
- 動能因子（30%）：近 120 日股價漲幅，越高越好
- 品質因子（30%）：`TaiwanStockFinancialStatements` 的 ROE = `IncomeAfterTaxes / EquityAttributableToOwnersOfParent`

**交易規則**：
- 每月第一個交易日換倉
- 選出總分前 5 大，等權重 20%
- 含手續費 0.1425% + 證交稅 0.3%（賣出）

## 2. 專案結構

```
finmind-quant/
├── main.py            # 入口：跑回測 + 產 HTML 報表
├── config.py          # 所有可調參數（股票池、日期、權重、費用）
├── quant.py           # 核心邏輯（抓資料 / pivot / 因子 / 排名 / 回測 / KPI）
├── report.py          # HTML 報表生成（plotly 互動圖）
├── output/
│   ├── report.html    # 互動式報告（開啟瀏覽器即可看）
│   └── backtest_results.json
├── cache/             # API 回傳 parquet 快取（重跑時省 API 額度）
└── SKILL.md           # 本檔
```

## 3. 設定檔（`config.py`）

所有可調參數集中在 `config.py`：

```python
START_DATE = '2023-01-01'
END_DATE = '2026-08-12'

STOCK_POOL = [...]   # 股票代號清單（建議 20-30 檔）

WEIGHTS = {'value': 0.40, 'momentum': 0.30, 'quality': 0.30}
MOMENTUM_LOOKBACK = 120
TOP_N = 5
EQUAL_WEIGHT = 0.20
COMMISSION = 0.001425
TAX = 0.003
```

股票池擴充：直接加 stock_id 即可。**注意**：ETF（如 0056、00878）沒有 PER / 財報資料，會被跳過。

## 4. Token 管理

**單一檔案**：`<設定環境變數 FINMIND_ENV_FILE 指向的 .env>`：

```bash
FINMIND_TOKEN=eyJ...
```

⚠️ **不要**用多個 token 輪替 — FinMind 會偵測同 IP 多 token，把**所有** token 都封鎖。已驗證踩坑。

## 5. 執行

```bash
cd <your-project-root>/quant
python3 main.py              # 跑回測 + 產 HTML
python3 main.py --open       # 跑完自動開瀏覽器
```

第一次跑會從 FinMind API 抓資料（**每檔股票每個 dataset 各一次呼叫**，26 檔 × 3 個 dataset ≈ 78 次）。後續會用 `cache/*.parquet` 加速。

## 6. FinMind API Rate Limit

- Token 額度：**600 requests / 小時**（依註冊的 FinMind 帳號）
- 超出會收到 `402` 或 `ip banned`
- 超過額度後**等下個小時**自動恢復
- **同 IP 多 token 會導致多 token 都被封鎖**（已驗證）

緩解措施：
- `cache/*.parquet` 磁碟快取（重跑免費）
- `Time.sleep(0.3)` 每檔間隔，避免打爆
- 跳過無資料股票（ETF 無 PER / 財報）

## 7. 已知踩坑

1. **股票池重複**：config.py 的 STOCK_POOL 不能有重複代號，否則 pivot 失敗。
2. **ETF 無 PER / 財報**：`0056`、`00878`、`00919` 等 ETF 在 PER/PBR 與財報 dataset 沒資料，會被 `empty data` 跳過。
3. **close 0 值**：某些停牌股票在某日 `close=0`，會讓 `pct_change` 變 `inf`。已用 `replace(0, np.nan)` 處理。
4. **FinMind async 批次靜默吞 exception**：`use_async=True` 內部會把 402 exception 吃掉，但 `df` 仍是空。改用逐檔同步呼叫（`stock_id=` 而非 `stock_id_list=`）以讓 exception 正常傳遞。
5. **bench_pos.iloc[0]** 只設第一行 → 之後都是 0。要用 `DataFrame(..., index, columns)` 全填值。
6. **pct_change 的 FutureWarning**：新版本 pandas 要加 `fill_method=None`。
7. **月頻調倉的月初識別**：用 `resample('MS')` 會有 type mismatch。改用 `PeriodIndex.to_timestamp()` + 範圍比對。

## 8. 結果範例（2023-01-01 ~ 2026-08-12，26 檔股票池）

| KPI | 數值 |
|-----|------|
| 策略總報酬 | +1193.04% |
| B&H 對照 | +153.71% |
| 超額報酬 | +1039.34% |
| MDD | -58.17% |
| Sharpe | 1.52 |
| 換倉次數 | 44（每月一次） |

> ⚠️ 這是強趨勢市場 + 因子動能佔比的特性，**不代表未來**。回測只是過去，請自行承擔交易風險。

## 9. 快速參考

| 操作 | URL / 指令 |
|------|-----------|
| 跑回測 | `python3 main.py` |
| 跑回測 + 開瀏覽器 | `python3 main.py --open` |
| 看報告 | `output/report.html` |
| 看 JSON 結果 | `output/backtest_results.json` |
| 清快取 | `rm -rf cache/*.parquet` |
| 改股票池 | 編輯 `config.py` 的 `STOCK_POOL` |
| 改因子權重 | 編輯 `config.py` 的 `WEIGHTS` |
| 改換倉頻率 | 編輯 `build_position()` 的 `monthly_dates` 邏輯 |