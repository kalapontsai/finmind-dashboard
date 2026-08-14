/**
 * 策略回測頁
 * - 個股選擇 + 區間
 * - 策略設定（MA / RSI / KD / MACD，可勾選）
 * - AND / OR 觸發模式
 * - KPI + 累計淨值曲線 + 交易明細
 */

const BacktestPage = {
    currentStock: null,
    charts: {},

    DEFAULT_SETTINGS: {
        ma:   { enabled: true,  short: 5, long: 20 },
        rsi:  { enabled: false, period: 14, low: 30, high: 70 },
        kd:   { enabled: false, period: 9, k_smooth: 3, d_smooth: 3, low: 20, high: 80 },
        macd: { enabled: false, fast: 12, slow: 26, signal: 9 },
    },

    render(container) {
        const s = this.DEFAULT_SETTINGS;
        container.innerHTML = `
            <div class="card">
                <div class="form-row">
                    <div class="field search-box" style="flex:2;">
                        <label class="field-label">個股</label>
                        <input type="text" class="input" id="stockSearch" placeholder="例如 2330 或 台積電" autocomplete="off">
                        <div class="search-results" id="searchResults" style="display:none;"></div>
                    </div>
                    <div class="field">
                        <label class="field-label">起始日</label>
                        <input type="date" class="input" id="startDate" value="${this.defaultStart()}">
                    </div>
                    <div class="field">
                        <label class="field-label">結束日</label>
                        <input type="date" class="input" id="endDate" value="${this.todayStr()}">
                    </div>
                    <div class="field">
                        <label class="field-label">初始資金</label>
                        <input type="number" class="input" id="capital" value="1000000" min="10000" step="100000">
                    </div>
                    <div class="field">
                        <label class="field-label">交易頻率</label>
                        <select class="select" id="frequencySel">
                            <option value="day">每日</option>
                            <option value="month">每月指定日期</option>
                        </select>
                    </div>
                    <div class="field" id="monthDayField" style="display:none;">
                        <label class="field-label">每月幾號</label>
                        <input type="number" class="input" id="monthDay" value="15" min="1" max="31">
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header"><div class="card-title">策略設定</div></div>

                <div class="form-row" style="margin-bottom:12px;">
                    <label class="field-label">觸發模式</label>
                    <select class="select" id="combineMode" style="max-width:140px;">
                        <option value="OR">OR（任一觸發即動作）</option>
                        <option value="AND">AND（全部啟用策略都觸發才動作）</option>
                    </select>
                </div>

                <div class="strategy-group">
                    <div class="strategy-header">
                        <label class="checkbox">
                            <input type="checkbox" id="stratMa" ${s.ma.enabled ? 'checked' : ''}>
                            <span class="strategy-name">MA 移動平均交叉</span>
                        </label>
                    </div>
                    <div class="strategy-params">
                        <div class="field">
                            <label class="field-label">短期</label>
                            <input type="number" class="input" id="maShort" value="${s.ma.short}" min="2" max="100">
                        </div>
                        <div class="field">
                            <label class="field-label">長期</label>
                            <input type="number" class="input" id="maLong" value="${s.ma.long}" min="5" max="200">
                        </div>
                    </div>
                </div>

                <div class="strategy-group">
                    <div class="strategy-header">
                        <label class="checkbox">
                            <input type="checkbox" id="stratRsi" ${s.rsi.enabled ? 'checked' : ''}>
                            <span class="strategy-name">RSI 超買超賣</span>
                        </label>
                    </div>
                    <div class="strategy-params">
                        <div class="field">
                            <label class="field-label">週期</label>
                            <input type="number" class="input" id="rsiPeriod" value="${s.rsi.period}" min="5" max="50">
                        </div>
                        <div class="field">
                            <label class="field-label">超賣門檻</label>
                            <input type="number" class="input" id="rsiLow" value="${s.rsi.low}" min="5" max="50">
                        </div>
                        <div class="field">
                            <label class="field-label">超買門檻</label>
                            <input type="number" class="input" id="rsiHigh" value="${s.rsi.high}" min="50" max="95">
                        </div>
                    </div>
                </div>

                <div class="strategy-group">
                    <div class="strategy-header">
                        <label class="checkbox">
                            <input type="checkbox" id="stratKd" ${s.kd.enabled ? 'checked' : ''}>
                            <span class="strategy-name">KD 隨機指標</span>
                        </label>
                    </div>
                    <div class="strategy-params">
                        <div class="field">
                            <label class="field-label">週期</label>
                            <input type="number" class="input" id="kdPeriod" value="${s.kd.period}" min="3" max="50">
                        </div>
                        <div class="field">
                            <label class="field-label">K 平滑</label>
                            <input type="number" class="input" id="kdK" value="${s.kd.k_smooth}" min="1" max="10">
                        </div>
                        <div class="field">
                            <label class="field-label">D 平滑</label>
                            <input type="number" class="input" id="kdD" value="${s.kd.d_smooth}" min="1" max="10">
                        </div>
                        <div class="field">
                            <label class="field-label">超賣門檻</label>
                            <input type="number" class="input" id="kdLow" value="${s.kd.low}" min="5" max="50">
                        </div>
                        <div class="field">
                            <label class="field-label">超買門檻</label>
                            <input type="number" class="input" id="kdHigh" value="${s.kd.high}" min="50" max="95">
                        </div>
                    </div>
                </div>

                <div class="strategy-group">
                    <div class="strategy-header">
                        <label class="checkbox">
                            <input type="checkbox" id="stratMacd" ${s.macd.enabled ? 'checked' : ''}>
                            <span class="strategy-name">MACD 柱狀翻正/翻負</span>
                        </label>
                    </div>
                    <div class="strategy-params">
                        <div class="field">
                            <label class="field-label">Fast</label>
                            <input type="number" class="input" id="macdFast" value="${s.macd.fast}" min="2" max="50">
                        </div>
                        <div class="field">
                            <label class="field-label">Slow</label>
                            <input type="number" class="input" id="macdSlow" value="${s.macd.slow}" min="5" max="100">
                        </div>
                        <div class="field">
                            <label class="field-label">Signal</label>
                            <input type="number" class="input" id="macdSignal" value="${s.macd.signal}" min="2" max="50">
                        </div>
                    </div>
                </div>

                <button class="btn btn-blue" id="runBtn" disabled style="margin-top:10px;">執行回測</button>
            </div>

            <div id="result"></div>
        `;

        this.bindSearch();
        document.getElementById('runBtn').addEventListener('click', () => this.run());

        // 頻率切換：顯示/隱藏「每月幾號」
        const freqSel = document.getElementById('frequencySel');
        const monthDayField = document.getElementById('monthDayField');
        freqSel.addEventListener('change', () => {
            monthDayField.style.display = freqSel.value === 'month' ? 'flex' : 'none';
        });

        // URL 帶 stock_id 自動預填（可選 ?autorun=1 直接執行、?frequency=month&month_day=20 預先設定）
        const params = new URLSearchParams(location.hash.split('?')[1] || '');
        const sid = params.get('stock_id');
        if (sid) {
            document.getElementById('stockSearch').value = sid;
            this.currentStock = { stock_id: sid, stock_name: '' };
            document.getElementById('runBtn').disabled = false;
        }

        // 頻率 + 月份日（即使沒有 stock_id 也可以先設）
        const freq = params.get('frequency');
        if (freq === 'month' || freq === 'day') {
            document.getElementById('frequencySel').value = freq;
            document.getElementById('monthDayField').style.display = freq === 'month' ? 'flex' : 'none';
        }
        const md = params.get('month_day');
        if (md) document.getElementById('monthDay').value = md;

        if (sid && params.get('autorun')) {
            setTimeout(() => this.run(), 200);
        }
    },

    defaultStart() {
        const d = new Date(Date.now() - 365 * 86400000);
        return d.toISOString().slice(0, 10);
    },

    todayStr() {
        return new Date().toISOString().slice(0, 10);
    },

    bindSearch() {
        const input = document.getElementById('stockSearch');
        const results = document.getElementById('searchResults');
        let timer = null;

        input.addEventListener('input', () => {
            clearTimeout(timer);
            const q = input.value.trim();
            if (q === '') {
                results.style.display = 'none';
                return;
            }
            timer = setTimeout(async () => {
                try {
                    const data = await FinMindAPI.stockList(q, 30);
                    if (data.stocks.length === 0) {
                        results.innerHTML = '<div class="search-result-item" style="cursor:default; color:var(--text-dim);">無結果</div>';
                    } else {
                        results.innerHTML = data.stocks.map(s => `
                            <div class="search-result-item" data-id="${s.stock_id}" data-name="${this.esc(s.stock_name)}">
                                <div>
                                    <span class="search-result-id">${s.stock_id}</span>
                                    <span class="search-result-name">${this.esc(s.stock_name)}</span>
                                </div>
                                <span class="search-result-industry">${this.esc(s.industry || s.type)}</span>
                            </div>
                        `).join('');
                        results.querySelectorAll('.search-result-item[data-id]').forEach(item => {
                            item.addEventListener('click', () => {
                                this.currentStock = { stock_id: item.dataset.id, stock_name: item.dataset.name };
                                input.value = `${item.dataset.id} ${item.dataset.name}`;
                                results.style.display = 'none';
                                document.getElementById('runBtn').disabled = false;
                            });
                        });
                    }
                    results.style.display = 'block';
                } catch (err) {
                    results.innerHTML = `<div class="search-result-item" style="cursor:default; color:var(--red);">搜尋失敗：${this.esc(err.message)}</div>`;
                    results.style.display = 'block';
                }
            }, 300);
        });

        document.addEventListener('click', (e) => {
            if (!e.target.closest('.search-box')) results.style.display = 'none';
        });
    },

    collectSettings() {
        return {
            ma:   { enabled: document.getElementById('stratMa').checked,   short: parseInt(document.getElementById('maShort').value),  long: parseInt(document.getElementById('maLong').value) },
            rsi:  { enabled: document.getElementById('stratRsi').checked,  period: parseInt(document.getElementById('rsiPeriod').value), low: parseFloat(document.getElementById('rsiLow').value), high: parseFloat(document.getElementById('rsiHigh').value) },
            kd:   { enabled: document.getElementById('stratKd').checked,   period: parseInt(document.getElementById('kdPeriod').value), k_smooth: parseInt(document.getElementById('kdK').value), d_smooth: parseInt(document.getElementById('kdD').value), low: parseFloat(document.getElementById('kdLow').value), high: parseFloat(document.getElementById('kdHigh').value) },
            macd: { enabled: document.getElementById('stratMacd').checked, fast: parseInt(document.getElementById('macdFast').value), slow: parseInt(document.getElementById('macdSlow').value), signal: parseInt(document.getElementById('macdSignal').value) },
        };
    },

    async run() {
        if (!this.currentStock) return;

        const settings = this.collectSettings();
        if (!settings.ma.enabled && !settings.rsi.enabled && !settings.kd.enabled && !settings.macd.enabled) {
            alert('請至少啟用一個策略');
            return;
        }

        const result = document.getElementById('result');
        const runBtn = document.getElementById('runBtn');
        runBtn.disabled = true;
        runBtn.textContent = '回測中...';
        App.showLoading(result, '回測執行中（拉取歷史股價 + 計算指標）...');

        try {
            const data = await FinMindAPI.backtest({
                stock_id: this.currentStock.stock_id,
                start_date: document.getElementById('startDate').value,
                end_date:   document.getElementById('endDate').value,
                capital:    parseFloat(document.getElementById('capital').value),
                strategies: settings,
                combine_mode: document.getElementById('combineMode').value,
                frequency:  document.getElementById('frequencySel').value,
                month_day:  parseInt(document.getElementById('monthDay').value),
            });

            this.renderResult(result, data);
        } catch (err) {
            result.innerHTML = `<div class="error-text">⚠️ ${this.esc(err.message)}</div>`;
        } finally {
            runBtn.disabled = false;
            runBtn.textContent = '執行回測';
        }
    },

    renderResult(container, data) {
        const retClass = data.total_return >= 0 ? 'positive' : 'negative';
        const bhClass  = data.buy_hold_return >= 0 ? 'positive' : 'negative';
        const diff = data.total_return - data.buy_hold_return;

        const freqLabel = data.frequency === 'month'
            ? `每月 ${data.month_day} 號 (實際動作 ${data.action_days} 天)`
            : `每日 (全部 ${data.action_days} 個交易日)`;
        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <div class="card-title">回測結果</div>
                    <div style="color:var(--text-dim); font-size:12px;">
                        ${data.stock_id} | ${data.start_date} ~ ${data.end_date} (${data.trading_days} 交易日) | ${freqLabel}
                    </div>
                </div>

                <div class="kpi-grid">
                    <div class="kpi-card ${retClass}">
                        <div class="kpi-label">策略總報酬</div>
                        <div class="kpi-value">${data.total_return >= 0 ? '+' : ''}${data.total_return}%</div>
                    </div>
                    <div class="kpi-card neutral">
                        <div class="kpi-label">年化報酬</div>
                        <div class="kpi-value">${data.annual_return >= 0 ? '+' : ''}${data.annual_return}%</div>
                    </div>
                    <div class="kpi-card ${data.max_drawdown > 20 ? 'negative' : 'neutral'}">
                        <div class="kpi-label">最大回撤 (MDD)</div>
                        <div class="kpi-value">-${data.max_drawdown}%</div>
                    </div>
                    <div class="kpi-card neutral">
                        <div class="kpi-label">勝率</div>
                        <div class="kpi-value">${data.win_rate}%</div>
                    </div>
                    <div class="kpi-card neutral">
                        <div class="kpi-label">交易次數</div>
                        <div class="kpi-value">${data.trade_count}</div>
                    </div>
                    <div class="kpi-card ${bhClass}">
                        <div class="kpi-label">Buy & Hold 對照</div>
                        <div class="kpi-value">${data.buy_hold_return >= 0 ? '+' : ''}${data.buy_hold_return}%</div>
                    </div>
                    <div class="kpi-card ${diff >= 0 ? 'positive' : 'negative'}">
                        <div class="kpi-label">超額報酬 (vs 買進持有)</div>
                        <div class="kpi-value">${diff >= 0 ? '+' : ''}${diff.toFixed(2)}%</div>
                    </div>
                </div>

                <div class="chart-box chart-box-lg"><canvas id="equityChart"></canvas></div>
            </div>

            <div class="card">
                <div class="card-header"><div class="card-title">交易紀錄</div></div>
                <div class="table-wrap">
                    ${this.renderTradesTable(data.trades, data.dates)}
                </div>
            </div>
        `;

        // Equity curve
        this.charts.equity = new Chart(document.getElementById('equityChart'), {
            type: 'line',
            data: {
                labels: data.dates,
                datasets: [
                    {
                        label: `策略 (${data.total_return >= 0 ? '+' : ''}${data.total_return}%)`,
                        data: data.equity_curve,
                        borderColor: '#58a6ff',
                        backgroundColor: 'rgba(88, 166, 255, 0.1)',
                        borderWidth: 1.5,
                        fill: true,
                        pointRadius: 0,
                    },
                    {
                        label: `Buy & Hold (${data.buy_hold_return >= 0 ? '+' : ''}${data.buy_hold_return}%)`,
                        data: data.buy_hold_curve,
                        borderColor: '#8b949e',
                        borderWidth: 1.2,
                        borderDash: [4, 4],
                        fill: false,
                        pointRadius: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: { legend: { position: 'top', labels: { boxWidth: 12 } }, tooltip: ChartDefaults.tooltip },
                scales: {
                    x: { grid: { color: ChartDefaults.grid }, ticks: { maxTicksLimit: 10 } },
                    y: { grid: { color: ChartDefaults.grid }, ticks: { callback: v => v.toLocaleString() } },
                },
            },
        });
    },

    renderTradesTable(trades, dates) {
        if (!trades || trades.length === 0) {
            return '<div class="state-box" style="padding:20px;">區間內無觸發交易</div>';
        }
        return `
            <table>
                <thead>
                    <tr>
                        <th>日期</th>
                        <th>動作</th>
                        <th class="num">價格</th>
                        <th class="num">股數</th>
                        <th class="num">金額</th>
                        <th>備註</th>
                    </tr>
                </thead>
                <tbody>
                    ${trades.map(t => `
                        <tr>
                            <td>${t.date}</td>
                            <td class="${t.action === 'BUY' ? 'up' : 'down'}" style="font-weight:600;">${t.action === 'BUY' ? '買進' : '賣出'}</td>
                            <td class="num">${t.price.toFixed(2)}</td>
                            <td class="num">${Indicators.fmtInt(t.qty)}</td>
                            <td class="num">${Indicators.fmtInt(t.amount)}</td>
                            <td style="color:var(--text-muted);">${t.action === 'BUY' ? '全部現金買入' : '全部庫存賣出'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    },

    esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    },
};
