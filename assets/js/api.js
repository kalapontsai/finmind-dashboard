/**
 * FinMind API Client（前端呼叫我們自己的 PHP 後端）
 */
const FinMindAPI = {
    base: '/finmind/api',

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
        return this.get('stock_list.php', { q, limit });
    },

    stockPrice(stockId, startDate, endDate) {
        return this.get('stock_price.php', {
            stock_id: stockId,
            start_date: startDate,
            end_date: endDate,
        });
    },

    stockPer(stockId, startDate, endDate) {
        return this.get('stock_per.php', { stock_id: stockId, start_date: startDate, end_date: endDate });
    },

    stockRevenue(stockId, startDate, endDate) {
        return this.get('stock_revenue.php', { stock_id: stockId, start_date: startDate, end_date: endDate });
    },

    stockFinance(stockId, startDate, endDate) {
        return this.get('stock_finance.php', { stock_id: stockId, start_date: startDate, end_date: endDate });
    },

    stockDividend(stockId, startDate, endDate) {
        return this.get('stock_dividend.php', { stock_id: stockId, start_date: startDate, end_date: endDate });
    },

    institutional(stockId, startDate, endDate) {
        return this.get('institutional.php', { stock_id: stockId, start_date: startDate, end_date: endDate });
    },

    margin(stockId, startDate, endDate) {
        return this.get('margin.php', { stock_id: stockId, start_date: startDate, end_date: endDate });
    },

    backtest(params) {
        return this.post('backtest.php', params);
    },
};
