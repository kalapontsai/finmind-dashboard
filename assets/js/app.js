/**
 * Sidebar / 路由 / 共用 UI
 */

const App = {
    pages: {
        'analysis':  { title: '個股分析', desc: '台股個股技術面 + 基本面 + 籌碼面整合分析', hash: 'taiwan-stock-analysis', render: (c) => AnalysisPage.render(c) },
        'backtest':  { title: '策略回測', desc: '依歷史股價回測 MA / RSI / KD / MACD 策略績效',     hash: 'back-testing',         render: (c) => BacktestPage.render(c) },
        'quant':     { title: '多因子回測', desc: 'Python 量化：價值 40% + 動能 30% + 品質 30%，月頻調倉',  hash: 'quant-backtest',     render: (c) => QuantPage.render(c) },
    },

    /**
     * 從 hash 解析頁面 key（支援 ?query 參數）
     */
    parseHash() {
        const raw = location.hash.replace(/^#\/?/, '');
        const hash = raw.split('?')[0];   // 去掉 ? 後的 query
        for (const [k, v] of Object.entries(this.pages)) {
            if (v.hash === hash) return k;
        }
        return 'analysis';
    },

    /**
     * 切換頁面
     */
    navigate(pageKey) {
        const page = this.pages[pageKey];
        if (!page) return;
        location.hash = page.hash;
    },

    /**
     * 初始化：綁 sidebar、hash 變動、頁面首次載入
     */
    init() {
        // Sidebar 點擊
        document.querySelectorAll('[data-nav]').forEach(el => {
            el.addEventListener('click', (e) => {
                e.preventDefault();
                this.navigate(el.dataset.nav);
                document.querySelector('.sidebar')?.classList.remove('open');
            });
        });

        // 手機版 menu toggle
        document.getElementById('menuToggle')?.addEventListener('click', () => {
            document.querySelector('.sidebar')?.classList.toggle('open');
        });

        // hash 變動
        window.addEventListener('hashchange', () => this.loadCurrent());

        // 首次載入
        this.loadCurrent();
    },

    /**
     * 載入當前頁面
     */
    loadCurrent() {
        const key = this.parseHash();
        const page = this.pages[key];

        // 更新 sidebar active
        document.querySelectorAll('[data-nav]').forEach(el => {
            el.classList.toggle('active', el.dataset.nav === key);
        });

        // 更新 title / desc
        document.getElementById('pageTitle').textContent = page.title;
        document.getElementById('pageDesc').textContent = page.desc;

        // 清空舊 charts
        if (window.Chart && Chart.helpers) {
            // Chart.js 4 — destroy by registry
            Chart.getChart('priceChart')?.destroy();
            Chart.getChart('rsiChart')?.destroy();
            Chart.getChart('kdChart')?.destroy();
            Chart.getChart('macdChart')?.destroy();
            Chart.getChart('revenueChart')?.destroy();
            Chart.getChart('instChart')?.destroy();
            Chart.getChart('equityChart')?.destroy();
        }

        // 渲染頁面
        const container = document.getElementById('pageContent');
        container.innerHTML = '';
        page.render(container);
    },

    /**
     * 共用 helper：顯示 loading / error / empty
     */
    showLoading(container, msg = '載入中...') {
        container.innerHTML = `<div class="state-box"><div class="spinner"></div><div>${msg}</div></div>`;
    },

    showError(container, msg) {
        container.innerHTML = `<div class="error-text">⚠️ ${msg}</div>`;
    },

    showEmpty(container, msg = '無資料') {
        container.innerHTML = `<div class="state-box">${msg}</div>`;
    },
};

// 啟動
document.addEventListener('DOMContentLoaded', () => App.init());
