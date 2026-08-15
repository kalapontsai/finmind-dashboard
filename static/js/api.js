/**
 * FinMind API Client（前端呼叫 Flask 後端）
 */
const FinMindAPI = {
    base: '/api',

    async get(url, params = {}) {
        // 過濾掉 undefined / null，避免 URLSearchParams 把 undefined 轉成 "undefined" 字串
        const clean = Object.entries(params).filter(([_, v]) => v !== undefined && v !== null && v !== '');
        const qs = new URLSearchParams(clean).toString();
        const r = await fetch(`${this.base}/${url}${qs ? '?' + qs : ''}`);
        const j = await r.json();
        if (!r.ok || j.error) throw new Error(j.error || `HTTP ${r.status}`);
        return j;
    },

    async post(url, body) {
        const r = await fetch(`${this.base}/${url}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const j = await r.json();
        if (!r.ok || j.error) throw new Error(j.error || `HTTP ${r.status}`);
        return j;
    },

    stockList(q = '', limit = 50) {
        return this.get('stock_list', { q, limit });
    },

    stockPrice(stockId, startDate, endDate) {
        return this.get('stock_price', {
            stock_id: stockId,
            start_date: startDate,
            end_date: endDate,
        });
    },

    stockPer(stockId, startDate, endDate) {
        return this.get('stock_per', { stock_id: stockId, start_date: startDate, end_date: endDate });
    },

    stockRevenue(stockId, startDate, endDate) {
        return this.get('stock_revenue', { stock_id: stockId, start_date: startDate, end_date: endDate });
    },

    stockFinance(stockId, startDate, endDate) {
        return this.get('stock_finance', { stock_id: stockId, start_date: startDate, end_date: endDate });
    },

    stockDividend(stockId, startDate, endDate) {
        return this.get('stock_dividend', { stock_id: stockId, start_date: startDate, end_date: endDate });
    },

    institutional(stockId, startDate, endDate) {
        return this.get('institutional', { stock_id: stockId, start_date: startDate, end_date: endDate });
    },

    margin(stockId, startDate, endDate) {
        return this.get('margin', { stock_id: stockId, start_date: startDate, end_date: endDate });
    },

    backtest(params) {
        return this.post('backtest', params);
    },

    quantRun(params) {
        return this.post('quant_run', params || {});
    },

    quantStatus() {
        return this.get('quant_status');
    },

    /**
     * 查詢非同步 job 的進度（v1.4 P3-4 修補）
     * GET /api/quant_status?job_id=xxx
     * 回傳：{ job_id, status, progress_pct, stage, updated_at, result?, error? }
     */
    quantStatusById(jobId) {
        return this.get('quant_status', { job_id: jobId });
    },

    quantPool() {
        return this.get('quant_pool');
    },

    strategiesList() {
        return this.get('strategies');
    },

    strategiesSaveConfig(strategies) {
        return this.post('strategies/config', { strategies });
    },
};
