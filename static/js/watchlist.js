/**
 * 觀察名單 Watchlist
 * - 用 localStorage 持久化（key: finmind.watchlist.v1）
 * - 結構：[{ stock_id, stock_name, added_at }]
 * - 提供：add / remove / has / list / subscribe / getPricesBatch
 *
 * 設計：
 * - 加入 / 刪除 → 發 'change' 事件
 * - UI 元素按鈕 star toggle，由個股頁綁定
 * - 觀察名單頁（sidebar menu 為 #/watchlist）→ 列出所有 + 最新收盤
 */

const Watchlist = {
    STORAGE_KEY: 'finmind.watchlist.v1',
    MAX_ITEMS: 50,

    /**
     * 取得 / 設定清單
     */
    list() {
        try {
            const raw = localStorage.getItem(this.STORAGE_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch (e) {
            console.warn('Watchlist.list parse failed:', e);
            return [];
        }
    },

    save(items) {
        // 限制最多 N 個（防狂加）
        const trimmed = items.slice(0, this.MAX_ITEMS);
        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(trimmed));
        this.dispatchChange();
    },

    has(stockId) {
        return this.list().some(it => it.stock_id === stockId);
    },

    add(stockId, stockName = '') {
        const items = this.list();
        if (items.some(it => it.stock_id === stockId)) return;  // 去重
        items.unshift({
            stock_id: stockId,
            stock_name: stockName,
            added_at: new Date().toISOString(),
        });
        this.save(items);
    },

    remove(stockId) {
        const items = this.list().filter(it => it.stock_id !== stockId);
        this.save(items);
    },

    toggle(stockId, stockName = '') {
        if (this.has(stockId)) this.remove(stockId);
        else this.add(stockId, stockName);
    },

    clear() {
        localStorage.removeItem(this.STORAGE_KEY);
        this.dispatchChange();
    },

    // 事件訂閱（給 UI 同步狀態）
    _listeners: [],
    onChange(fn) { this._listeners.push(fn); },
    dispatchChange() {
        this._listeners.forEach(fn => {
            try { fn(); } catch (e) { console.warn('Watchlist listener err:', e); }
        });
    },

    /**
     * 批次抓最新價（給觀察名單頁用）
     */
    async getLatestPrices() {
        const items = this.list();
        if (items.length === 0) return [];

        const end = new Date().toISOString().slice(0, 10);
        const start = (() => {
            const d = new Date();
            d.setDate(d.getDate() - 30);
            return d.toISOString().slice(0, 10);
        })();

        const tasks = items.map(async it => {
            try {
                const data = await FinMindAPI.stockPrice(it.stock_id, start, end);
                if (!data || data.length === 0) return null;
                const last = data[data.length - 1];
                const prev = data.length > 1 ? data[data.length - 2] : null;
                const close = +last.close;
                const prevClose = prev ? +prev.close : close;
                const chg = close - prevClose;
                const chgPct = prevClose ? (chg / prevClose * 100) : 0;
                return {
                    ...it,
                    date: last.date,
                    close,
                    change: chg,
                    change_pct: chgPct,
                };
            } catch (e) {
                console.warn(`Watchlist.getLatestPrices ${it.stock_id} failed:`, e);
                return { ...it, error: true };
            }
        });

        return Promise.all(tasks);
    },
};

/**
 * 觀察名單頁
 */
const WatchlistPage = {
    state: { items: [], loading: false },

    async render(container) {
        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <div class="card-title">我的觀察名單</div>
                    <div style="display:flex; gap:8px;">
                        <button class="btn btn-ghost" id="refreshBtn">↻ 重新整理</button>
                        <button class="btn btn-ghost" id="clearBtn" style="color:var(--orange);">清空</button>
                    </div>
                </div>
                <div style="color:var(--text-muted); font-size:12px; margin-bottom:8px;">
                    在個股分析頁加入觀察名單（localStorage 儲存，最多 ${Watchlist.MAX_ITEMS} 檔）
                </div>
                <div id="wlList"></div>
            </div>
        `;

        document.getElementById('refreshBtn').addEventListener('click', () => this.refresh(container));
        document.getElementById('clearBtn').addEventListener('click', () => {
            if (confirm('確定清空所有觀察名單？')) {
                Watchlist.clear();
                this.refresh(container);
            }
        });

        // 同步跨頁：Watchlist 變更時自動重新整理
        Watchlist.onChange(() => {
            if (this.state.loading) return;
            this.refresh(container);
        });

        await this.refresh(container);
    },

    async refresh(container) {
        const box = document.getElementById('wlList');
        if (!box) return;

        const items = Watchlist.list();
        if (items.length === 0) {
            box.innerHTML = `
                <div style="padding:40px; text-align:center; color:var(--text-muted);">
                    <div style="font-size:32px; margin-bottom:8px;">☆</div>
                    <div>尚未加入任何股票</div>
                    <div style="font-size:12px; margin-top:8px;">前往「個股分析」頁，找支股票點「☆ 加入觀察名單」</div>
                </div>
            `;
            return;
        }

        this.state.loading = true;
        box.innerHTML = `
            <div class="state-box">
                <div class="spinner"></div>
                <div>載入 ${items.length} 檔最新價...</div>
            </div>
        `;

        const prices = await Watchlist.getLatestPrices();

        this.state.loading = false;
        const newBox = document.getElementById('wlList');
        if (!newBox) return;

        newBox.innerHTML = `
            <table class="table" style="width:100%;">
                <thead>
                    <tr>
                        <th style="width:80px;">代碼</th>
                        <th>名稱</th>
                        <th style="text-align:right;">最新價</th>
                        <th style="text-align:right;">漲跌</th>
                        <th style="text-align:right;">漲跌 %</th>
                        <th style="text-align:right;">日期</th>
                        <th style="width:100px;"></th>
                    </tr>
                </thead>
                <tbody>
                    ${prices.map(p => {
                        if (!p) return '';
                        if (p.error) {
                            return `
                                <tr>
                                    <td><strong>${p.stock_id}</strong></td>
                                    <td colspan="5" style="color:var(--orange);">載入失敗</td>
                                    <td><button class="btn btn-ghost" data-remove="${p.stock_id}" style="font-size:12px;">移除</button></td>
                                </tr>
                            `;
                        }
                        const dir = p.change >= 0 ? 'up' : 'down';
                        const arrow = p.change >= 0 ? '▲' : '▼';
                        const sign = p.change >= 0 ? '+' : '';
                        return `
                            <tr data-sid="${p.stock_id}" style="cursor:pointer;">
                                <td><strong>${p.stock_id}</strong></td>
                                <td>${this.esc(p.stock_name || '')}</td>
                                <td style="text-align:right;">${p.close.toFixed(2)}</td>
                                <td style="text-align:right; color:var(--${dir});">${arrow} ${sign}${Math.abs(p.change).toFixed(2)}</td>
                                <td style="text-align:right; color:var(--${dir});">${sign}${p.change_pct.toFixed(2)}%</td>
                                <td style="text-align:right; color:var(--text-muted); font-size:12px;">${p.date}</td>
                                <td><button class="btn btn-ghost" data-remove="${p.stock_id}" style="font-size:12px;">移除</button></td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;

        // 綁定事件
        newBox.querySelectorAll('[data-remove]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                Watchlist.remove(btn.dataset.remove);
                // Watchlist.onChange 會自動 refresh
            });
        });

        newBox.querySelectorAll('tr[data-sid]').forEach(tr => {
            tr.addEventListener('click', () => {
                window.location.hash = `#/taiwan-stock-analysis?stock=${tr.dataset.sid}`;
            });
        });
    },

    esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    },
};