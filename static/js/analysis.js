/**
 * 個股分析頁
 * - 個股搜尋（autocomplete）
 * - 區間選擇
 * - 個股 header（最新價、漲跌）
 * - 主圖：收盤 + MA
 * - RSI / KD / MACD 副圖
 * - 基本面（PER / PBR / 殖利率）
 * - 月營收 YoY
 * - 三大法人
 * - 融資融券
 * - 配息歷史
 */

const AnalysisPage = {
    currentStock: null,
    charts: {},

    /**
     * 主渲染
     */
    render(container) {
        container.innerHTML = `
            <div class="card">
                <div class="form-row">
                    <div class="field search-box" style="flex:2;">
                        <label class="field-label">個股搜尋（代碼或名稱）</label>
                        <input type="text" class="input" id="stockSearch" placeholder="例如 2330 或 台積電" autocomplete="off">
                        <div class="search-results" id="searchResults" style="display:none;"></div>
                    </div>
                    <div class="field">
                        <label class="field-label">區間</label>
                        <select class="select" id="rangeSel">
                            <option value="1M">近 1 個月</option>
                            <option value="3M" selected>近 3 個月</option>
                            <option value="6M">近 6 個月</option>
                            <option value="1Y">近 1 年</option>
                            <option value="2Y">近 2 年</option>
                            <option value="YTD">今年以來</option>
                            <option value="custom">自訂</option>
                        </select>
                    </div>
                    <div class="field" id="customRangeWrap" style="display:none;">
                        <label class="field-label">起 / 迄</label>
                        <div style="display:flex; gap:6px;">
                            <input type="date" class="input" id="startDate">
                            <input type="date" class="input" id="endDate">
                        </div>
                    </div>
                    <div class="field" style="flex:0 0 auto;">
                        <button class="btn btn-blue" id="loadBtn" disabled>載入資料</button>
                    </div>
                </div>
            </div>

            <div id="stockInfo"></div>

            <div class="card" id="priceCard" style="display:none;">
                <div class="card-header">
                    <div class="card-title">股價走勢 + 移動平均線</div>
                </div>
                <div class="chart-box chart-box-lg"><canvas id="priceChart"></canvas></div>
            </div>

            <div class="grid-2" id="subCharts" style="display:none; gap:16px;">
                <div class="card">
                    <div class="card-header"><div class="card-title">RSI (14)</div></div>
                    <div class="chart-box chart-box-sm"><canvas id="rsiChart"></canvas></div>
                </div>
                <div class="card">
                    <div class="card-header"><div class="card-title">KD (9,3,3)</div></div>
                    <div class="chart-box chart-box-sm"><canvas id="kdChart"></canvas></div>
                </div>
            </div>

            <div class="card" id="macdCard" style="display:none;">
                <div class="card-header"><div class="card-title">MACD (12,26,9)</div></div>
                <div class="chart-box"><canvas id="macdChart"></canvas></div>
            </div>

            <div class="card" id="fundamentalsCard" style="display:none;">
                <div class="card-header"><div class="card-title">基本面（本益比 / 淨值比 / 殖利率）</div></div>
                <div class="stats-grid" id="fundamentalsGrid"></div>
                <div class="chart-box chart-box-sm"><canvas id="perChart"></canvas></div>
            </div>

            <div class="card" id="revenueCard" style="display:none;">
                <div class="card-header"><div class="card-title">月營收（YoY %）</div></div>
                <div class="chart-box"><canvas id="revenueChart"></canvas></div>
            </div>

            <div class="card" id="instCard" style="display:none;">
                <div class="card-header"><div class="card-title">三大法人買賣超</div></div>
                <div class="chart-box"><canvas id="instChart"></canvas></div>
            </div>

            <div class="grid-2" id="tablesRow" style="display:none; gap:16px;">
                <div class="card">
                    <div class="card-header"><div class="card-title">融資融券</div></div>
                    <div class="table-wrap" id="marginTable"></div>
                </div>
                <div class="card">
                    <div class="card-header"><div class="card-title">配息歷史</div></div>
                    <div class="table-wrap" id="dividendTable"></div>
                </div>
            </div>
        `;

        // 自訂區間切換
        document.getElementById('rangeSel').addEventListener('change', (e) => {
            document.getElementById('customRangeWrap').style.display = e.target.value === 'custom' ? 'flex' : 'none';
        });

        // 個股搜尋
        this.bindSearch();

        // 指標教學 ⓘ tooltip
        if (window.IndicatorTip) IndicatorTip.bindAll();

        // 載入按鈕
        document.getElementById('loadBtn').addEventListener('click', () => this.loadAll());

        // URL 帶 stock_id 自動載入
        const params = new URLSearchParams(location.hash.split('?')[1] || '');
        const sid = params.get('stock_id');
        if (sid) {
            document.getElementById('stockSearch').value = sid;
            this.currentStock = { stock_id: sid, stock_name: '' };
            document.getElementById('loadBtn').disabled = false;
            this.loadAll();
        }
    },

    /**
     * 個股搜尋 autocomplete
     */
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
                                document.getElementById('loadBtn').disabled = false;
                                this.loadAll();
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

        // 點外面關閉
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.search-box')) results.style.display = 'none';
        });
    },

    /**
     * 取得區間
     */
    getRange() {
        const sel = document.getElementById('rangeSel').value;
        const today = new Date();
        const end = today.toISOString().slice(0, 10);
        let start;
        if (sel === 'custom') {
            start = document.getElementById('startDate').value || end;
            const e = document.getElementById('endDate').value || end;
            return [start, e];
        }
        if (sel === 'YTD') {
            start = `${today.getFullYear()}-01-01`;
        } else {
            const days = { '1M': 30, '3M': 90, '6M': 180, '1Y': 365, '2Y': 730 }[sel];
            const d = new Date(today.getTime() - days * 86400000);
            start = d.toISOString().slice(0, 10);
        }
        return [start, end];
    },

    /**
     * 載入所有資料
     */
    async loadAll() {
        if (!this.currentStock) return;
        const [start, end] = this.getRange();
        const sid = this.currentStock.stock_id;

        const info = document.getElementById('stockInfo');
        App.showLoading(info, `載入 ${sid} ${this.currentStock.stock_name || ''} 資料...`);

        try {
            // 並行抓所有資料（價格 / PER / 營收 / 法人 / 融資 / 配息）
            const [priceData, perData, revenueData, instData, marginData, dividendData] = await Promise.allSettled([
                FinMindAPI.stockPrice(sid, start, end),
                FinMindAPI.stockPer(sid, start, end),
                FinMindAPI.stockRevenue(sid),
                FinMindAPI.institutional(sid, start, end),
                FinMindAPI.margin(sid, start, end),
                FinMindAPI.stockDividend(sid),
            ]);

            const price    = priceData.status    === 'fulfilled' ? priceData.value    : null;
            const per      = perData.status      === 'fulfilled' ? perData.value      : null;
            const revenue  = revenueData.status  === 'fulfilled' ? revenueData.value  : null;
            const inst     = instData.status     === 'fulfilled' ? instData.value     : null;
            const margin   = marginData.status   === 'fulfilled' ? marginData.value   : null;
            const dividend = dividendData.status === 'fulfilled' ? dividendData.value : null;

            if (!price || price.count === 0) {
                info.innerHTML = '';
                App.showError(info, `${sid} 在選定區間無價格資料`);
                this.hideAllCards();
                return;
            }

            this.renderStockHeader(info, price.prices);
            this.renderPriceChart(price.prices);
            this.renderSubCharts(price.prices);
            this.renderMACDChart(price.prices);

            if (per) this.renderFundamentals(per.rows);
            if (revenue) this.renderRevenueChart(revenue.rows);
            if (inst) this.renderInstChart(inst.rows);

            this.renderTables(margin ? margin.rows : [], dividend);

        } catch (err) {
            info.innerHTML = '';
            App.showError(info, err.message);
            this.hideAllCards();
        }
    },

    hideAllCards() {
        ['priceCard', 'subCharts', 'macdCard', 'fundamentalsCard', 'revenueCard', 'instCard', 'tablesRow']
            .forEach(id => document.getElementById(id).style.display = 'none');
    },

    renderStockHeader(container, prices) {
        const last = prices[prices.length - 1];
        const prev = prices[prices.length - 2] || last;
        const chg = last.close - prev.close;
        const chgPct = prev.close ? (chg / prev.close * 100) : 0;
        const dir = chg >= 0 ? 'up' : 'down';
        const arrow = chg >= 0 ? '▲' : '▼';

        container.innerHTML = `
            <div class="stock-header">
                <span class="stock-id">${last.stock_id}</span>
                <span class="stock-name">${this.esc(this.currentStock.stock_name || '')}</span>
                <span class="stock-price ${dir}">${Indicators.fmtNum(last.close)}</span>
                <span class="stock-change ${dir}">${arrow} ${chg >= 0 ? '+' : ''}${Indicators.fmtNum(chg)} (${chg >= 0 ? '+' : ''}${Indicators.fmtNum(chgPct)}%)</span>
                <button class="btn btn-ghost" id="watchBtn" style="margin-left:auto; font-size:14px; padding:4px 10px;">${(window.Watchlist && Watchlist.has(last.stock_id)) ? '⭐ 已觀察' : '☆ 加入觀察名單'}</button>
                <span style="color:var(--text-dim); font-size:12px;">${last.date}</span>
            </div>
        `;

        // 綁定觀察名單按鈕
        const wb = document.getElementById('watchBtn');
        if (wb && window.Watchlist) {
            wb.addEventListener('click', () => {
                Watchlist.toggle(last.stock_id, this.currentStock.stock_name || '');
                wb.textContent = Watchlist.has(last.stock_id) ? '⭐ 已觀察' : '☆ 加入觀察名單';
            });
        }
    },

    renderPriceChart(prices) {
        document.getElementById('priceCard').style.display = 'block';
        const labels = prices.map(p => p.date);
        const closes = prices.map(p => p.close);
        const ma5 = Indicators.sma(closes, 5);
        const ma20 = Indicators.sma(closes, 20);
        const ma60 = Indicators.sma(closes, 60);

        this.charts.price = new Chart(document.getElementById('priceChart'), {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: '收盤',
                        data: closes,
                        borderColor: '#58a6ff',
                        backgroundColor: 'rgba(88, 166, 255, 0.05)',
                        borderWidth: 1.5,
                        fill: true,
                        tension: 0.1,
                        pointRadius: 0,
                    },
                    {
                        label: 'MA5',
                        data: ma5,
                        borderColor: '#d29922',
                        borderWidth: 1.2,
                        fill: false,
                        pointRadius: 0,
                    },
                    {
                        label: 'MA20',
                        data: ma20,
                        borderColor: '#8957e5',
                        borderWidth: 1.2,
                        fill: false,
                        pointRadius: 0,
                    },
                    {
                        label: 'MA60',
                        data: ma60,
                        borderColor: '#3fb950',
                        borderWidth: 1.2,
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

    renderSubCharts(prices) {
        document.getElementById('subCharts').style.display = 'grid';
        const labels = prices.map(p => p.date);
        const closes = prices.map(p => p.close);
        const highs  = prices.map(p => p.max);
        const lows   = prices.map(p => p.min);

        // RSI
        const rsi = Indicators.rsi(closes, 14);
        this.charts.rsi = new Chart(document.getElementById('rsiChart'), {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'RSI',
                    data: rsi,
                    borderColor: '#58a6ff',
                    borderWidth: 1.5,
                    fill: false,
                    pointRadius: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: ChartDefaults.tooltip },
                scales: {
                    x: { grid: { color: ChartDefaults.grid }, ticks: { maxTicksLimit: 8 } },
                    y: { min: 0, max: 100, grid: { color: ChartDefaults.grid } },
                },
            },
        });

        // KD
        const { k, d } = Indicators.kd(highs, lows, closes, 9, 3, 3);
        this.charts.kd = new Chart(document.getElementById('kdChart'), {
            type: 'line',
            data: {
                labels,
                datasets: [
                    { label: 'K', data: k, borderColor: '#58a6ff', borderWidth: 1.2, fill: false, pointRadius: 0 },
                    { label: 'D', data: d, borderColor: '#d29922', borderWidth: 1.2, fill: false, pointRadius: 0 },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'top', labels: { boxWidth: 12 } }, tooltip: ChartDefaults.tooltip },
                scales: {
                    x: { grid: { color: ChartDefaults.grid }, ticks: { maxTicksLimit: 8 } },
                    y: { min: 0, max: 100, grid: { color: ChartDefaults.grid } },
                },
            },
        });
    },

    renderMACDChart(prices) {
        document.getElementById('macdCard').style.display = 'block';
        const labels = prices.map(p => p.date);
        const closes = prices.map(p => p.close);
        const { dif, macd, osc } = Indicators.macd(closes, 12, 26, 9);

        this.charts.macd = new Chart(document.getElementById('macdChart'), {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: 'OSC',
                        data: osc,
                        backgroundColor: osc.map(v => v >= 0 ? 'rgba(63, 185, 80, 0.6)' : 'rgba(248, 81, 73, 0.6)'),
                        borderWidth: 0,
                        type: 'bar',
                        order: 2,
                    },
                    {
                        label: 'DIF',
                        data: dif,
                        borderColor: '#58a6ff',
                        borderWidth: 1.2,
                        fill: false,
                        pointRadius: 0,
                        type: 'line',
                        order: 1,
                    },
                    {
                        label: 'MACD',
                        data: macd,
                        borderColor: '#d29922',
                        borderWidth: 1.2,
                        fill: false,
                        pointRadius: 0,
                        type: 'line',
                        order: 1,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'top', labels: { boxWidth: 12 } }, tooltip: ChartDefaults.tooltip },
                scales: {
                    x: { grid: { color: ChartDefaults.grid }, ticks: { maxTicksLimit: 10 } },
                    y: { grid: { color: ChartDefaults.grid } },
                },
            },
        });
    },

    renderFundamentals(rows) {
        if (!rows || rows.length === 0) return;
        document.getElementById('fundamentalsCard').style.display = 'block';
        const last = rows[rows.length - 1];

        const grid = document.getElementById('fundamentalsGrid');
        grid.innerHTML = `
            <div class="stat-box"><div class="stat-label">本益比 (PER)</div><div class="stat-value">${Indicators.fmtNum(last.PER)}</div></div>
            <div class="stat-box"><div class="stat-label">股價淨值比 (PBR)</div><div class="stat-value">${Indicators.fmtNum(last.PBR)}</div></div>
            <div class="stat-box"><div class="stat-label">現金殖利率</div><div class="stat-value">${Indicators.fmtNum(last.dividend_yield)}%</div></div>
            <div class="stat-box"><div class="stat-label">資料日期</div><div class="stat-value" style="font-size:14px;">${last.date}</div></div>
        `;

        const labels = rows.map(r => r.date);
        this.charts.per = new Chart(document.getElementById('perChart'), {
            type: 'line',
            data: {
                labels,
                datasets: [
                    { label: 'PER', data: rows.map(r => r.PER), borderColor: '#58a6ff', borderWidth: 1.5, fill: false, pointRadius: 0, yAxisID: 'y' },
                    { label: 'PBR', data: rows.map(r => r.PBR), borderColor: '#8957e5', borderWidth: 1.5, fill: false, pointRadius: 0, yAxisID: 'y' },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'top', labels: { boxWidth: 12 } }, tooltip: ChartDefaults.tooltip },
                scales: {
                    x: { grid: { color: ChartDefaults.grid }, ticks: { maxTicksLimit: 8 } },
                    y: { grid: { color: ChartDefaults.grid }, ticks: { callback: v => v.toLocaleString() } },
                },
            },
        });
    },

    renderRevenueChart(rows) {
        if (!rows || rows.length === 0) return;
        document.getElementById('revenueCard').style.display = 'block';
        const labels = rows.map(r => r.date);
        const yoy = rows.map(r => r.YoY);

        this.charts.revenue = new Chart(document.getElementById('revenueChart'), {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'YoY %',
                    data: yoy,
                    backgroundColor: yoy.map(v => v === null ? 'rgba(110, 118, 129, 0.3)' : (v >= 0 ? 'rgba(63, 185, 80, 0.6)' : 'rgba(248, 81, 73, 0.6)')),
                    borderColor: yoy.map(v => v === null ? '#6e7681' : (v >= 0 ? '#3fb950' : '#f85149')),
                    borderWidth: 1,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { ...ChartDefaults.tooltip, callbacks: { label: ctx => ctx.parsed.y === null ? '無前期資料' : `${ctx.parsed.y.toFixed(2)}%` } } },
                scales: {
                    x: { grid: { color: ChartDefaults.grid }, ticks: { maxTicksLimit: 10 } },
                    y: { grid: { color: ChartDefaults.grid }, ticks: { callback: v => v + '%' } },
                },
            },
        });
    },

    renderInstChart(rows) {
        if (!rows || rows.length === 0) return;
        document.getElementById('instCard').style.display = 'block';
        const labels = rows.map(r => r.date);

        this.charts.inst = new Chart(document.getElementById('instChart'), {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    { label: '外資',    data: rows.map(r => r.foreign),  backgroundColor: '#58a6ff', stack: 's' },
                    { label: '投信',    data: rows.map(r => r.trust),    backgroundColor: '#3fb950', stack: 's' },
                    { label: '自營商',  data: rows.map(r => r.dealer),   backgroundColor: '#d29922', stack: 's' },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'top', labels: { boxWidth: 12 } }, tooltip: ChartDefaults.tooltip },
                scales: {
                    x: { stacked: true, grid: { color: ChartDefaults.grid }, ticks: { maxTicksLimit: 10 } },
                    y: { stacked: true, grid: { color: ChartDefaults.grid }, ticks: { callback: v => v.toLocaleString() } },
                },
            },
        });
    },

    renderTables(marginRows, dividend) {
        document.getElementById('tablesRow').style.display = 'grid';

        // 融資融券
        const mt = document.getElementById('marginTable');
        if (!marginRows || marginRows.length === 0) {
            mt.innerHTML = '<div class="state-box" style="padding:20px;">無資料</div>';
        } else {
            const latest = marginRows.slice(-20).reverse();
            mt.innerHTML = `
                <table>
                    <thead>
                        <tr>
                            <th>日期</th>
                            <th class="num">融資買進</th>
                            <th class="num">融資賣出</th>
                            <th class="num">融資餘額</th>
                            <th class="num">融券餘額</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${latest.map(r => `
                            <tr>
                                <td>${r.date}</td>
                                <td class="num">${Indicators.fmtInt(r.MarginPurchaseBuy)}</td>
                                <td class="num">${Indicators.fmtInt(r.MarginPurchaseSell)}</td>
                                <td class="num">${Indicators.fmtInt(r.MarginPurchaseTodayBalance)}</td>
                                <td class="num">${Indicators.fmtInt(r.ShortSaleTodayBalance)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }

        // 配息（後端已依年份彙總）
        const dt = document.getElementById('dividendTable');
        if (!dividend || !dividend.rows || dividend.rows.length === 0) {
            dt.innerHTML = '<div class="state-box" style="padding:20px;">無資料</div>';
        } else {
            const rows = dividend.rows.slice(0, 8);
            dt.innerHTML = `
                <table>
                    <thead>
                        <tr>
                            <th>年度</th>
                            <th class="num">現金股利</th>
                            <th class="num">股票股利</th>
                            <th class="num">合計 / 股</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map(r => `
                            <tr>
                                <td>${r.year}</td>
                                <td class="num">${Indicators.fmtNum(r.cash_dividend, 2)}</td>
                                <td class="num">${Indicators.fmtNum(r.stock_dividend, 2)}</td>
                                <td class="num">${Indicators.fmtNum(r.cash_dividend + r.stock_dividend, 2)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }
    },

    esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    },
};
