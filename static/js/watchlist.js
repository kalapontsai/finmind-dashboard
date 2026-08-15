/**
 * 觀察名單 Watchlist
 * - 用 localStorage 持久化（key: finmind.watchlist.v1）作為「已加自選」子集
 * - 主清單來自 `quant/pool.json`（由 `quant/pool.txt` 同步而來）透過 /api/quant_pool
 * - 結構：[{ stock_id, stock_name, added_at }]
 * - 提供：add / remove / has / list / subscribe / getPricesBatch
 *
 * 設計：
 * - 主清單 = pool.json（100 檔池）；localStorage = ★ 加星號子集
 * - 加入 / 刪除 → 發 'change' 事件
 * - UI 元素按鈕 star toggle，由個股頁 / 觀察名單頁綁定
 */

const Watchlist = {
    STORAGE_KEY: 'finmind.watchlist.v1',
    MAX_ITEMS: 500,  // v1.4 P3-6：拉高上限（原 50 會吃掉 pool 後半）

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
 *
 * v1.4 P3-4 修補：主清單改讀 `quant/pool.json`（透過 /api/quant_pool），
 *   localStorage 只保留「已加自選」子集。避免「觀察名單空白」問題。
 *
 * - 顯示規則：
 *   1. 從 /api/quant_pool 拿 pool.json 主清單（100 檔）
 *   2. localStorage 是「★ 加自選」標記（不影響主清單顯示）
 *   3. 每行有 ☆/★ toggle；點 ★ 取消自選、☆ 加入自選
 *   4. 不批次抓價（100 檔一次拉會太慢且 hit rate limit）；點列進入個股分析
 * - 右上按鈕：
 *   - 「📥 全部加入自選」：把 pool.json 全部加進 localStorage（★）
 *   - 「清空自選」：清掉 localStorage 的 ★（pool 主清單仍顯示）
 */
const WatchlistPage = {
    state: { pool: [], loading: false },

    async render(container) {
        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <div class="card-title">觀察名單</div>
                    <div style="display:flex; gap:8px;">
                        <button class="btn btn-ghost" id="refreshBtn">↻ 重新整理</button>
                        <button class="btn btn-ghost" id="bulkAddBtn" title="把 pool.json 全部加進自選（localStorage）">📥 全部加入自選</button>
                        <button class="btn btn-ghost" id="clearBtn" style="color:var(--orange);">清空自選</button>
                    </div>
                </div>
                <div style="color:var(--text-muted); font-size:12px; margin-bottom:8px;" id="wlHeader">
                    主清單：<code>quant/pool.json</code>（由 <code>quant/pool.txt</code> 同步）· 載入中…
                </div>
                <div id="wlList"></div>
            </div>
        `;

        document.getElementById('refreshBtn').addEventListener('click', () => this.refresh());
        document.getElementById('clearBtn').addEventListener('click', () => {
            if (confirm('確定清空所有「自選」（localStorage）？pool 主清單仍會顯示。')) {
                Watchlist.clear();
                this.refresh();
            }
        });
        document.getElementById('bulkAddBtn').addEventListener('click', () => this.bulkAddAll());

        // 同步跨頁：Watchlist 變更時自動重新整理
        Watchlist.onChange(() => {
            if (this.state.loading) return;
            this.refresh();
        });

        await this.refresh();
    },

    async refresh() {
        const box = document.getElementById('wlList');
        const header = document.getElementById('wlHeader');
        if (!box) return;

        // 1. 拿 pool.json 主清單（透過 /api/quant_pool）
        this.state.loading = true;
        let poolStocks = [];
        try {
            const data = await FinMindAPI.quantPool();
            poolStocks = (data && data.stocks) ? data.stocks : [];
        } catch (e) {
            box.innerHTML = `<div class="error-text">❌ pool 載入失敗：${this.esc(e.message)}</div>`;
            this.state.loading = false;
            return;
        }
        this.state.pool = poolStocks;

        if (poolStocks.length === 0) {
            box.innerHTML = `
                <div style="padding:40px; text-align:center; color:var(--text-muted);">
                    <div style="font-size:32px; margin-bottom:8px;">⚠</div>
                    <div>pool.json 是空的</div>
                    <div style="font-size:12px; margin-top:8px;">請檢查 <code>quant/pool.txt</code>，或執行 <code>python3 -c "from lib.pool_loader import sync_pool_json; sync_pool_json()"</code></div>
                </div>
            `;
            if (header) header.innerHTML = '主清單：<code>quant/pool.json</code> · <strong>0 檔</strong>';
            this.state.loading = false;
            return;
        }

        // 2. 拿 localStorage 「已加自選」Set
        const starred = new Set(Watchlist.list().map(x => x.stock_id));

        if (header) {
            header.innerHTML = `主清單：<code>quant/pool.json</code> · <strong>${poolStocks.length} 檔</strong> · ★已加自選 <strong>${starred.size}</strong> 檔（點 ☆/★ 切換）`;
        }

        // 3. 渲染表格（不抓價；100 檔一次拉會 hit rate limit）
        box.innerHTML = `
            <table class="table" style="width:100%;">
                <thead>
                    <tr>
                        <th style="width:60px;">★</th>
                        <th style="width:100px;">代碼</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${poolStocks.map(sid => {
                        const isStarred = starred.has(sid);
                        return `
                            <tr data-sid="${sid}" style="cursor:pointer;">
                                <td style="text-align:center; font-size:18px;">${isStarred ? '★' : '☆'}</td>
                                <td><strong>${sid}</strong></td>
                                <td>
                                    <button class="btn btn-ghost" data-toggle="${sid}" style="font-size:12px;">
                                        ${isStarred ? '取消自選' : '加入自選'}
                                    </button>
                                    <button class="btn btn-ghost" data-open="${sid}" style="font-size:12px;">檢視個股 ↗</button>
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;

        // 4. 綁定事件
        box.querySelectorAll('[data-toggle]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const sid = btn.dataset.toggle;
                if (Watchlist.has(sid)) Watchlist.remove(sid);
                else Watchlist.add(sid, '');  // 名稱由個股頁補
                // Watchlist.onChange 會自動 refresh
            });
        });
        box.querySelectorAll('[data-open]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                window.location.hash = `#/taiwan-stock-analysis?stock=${btn.dataset.open}`;
            });
        });
        box.querySelectorAll('tr[data-sid]').forEach(tr => {
            tr.addEventListener('click', () => {
                window.location.hash = `#/taiwan-stock-analysis?stock=${tr.dataset.sid}`;
            });
        });

        this.state.loading = false;
    },

    /**
     * 「📥 全部加入自選」：把 pool.json 全部加進 localStorage（去重）
     */
    bulkAddAll() {
        const items = Watchlist.list();
        const have = new Set(items.map(x => x.stock_id));
        const missing = this.state.pool.filter(sid => !have.has(sid));
        if (missing.length === 0) {
            alert('pool 全部都已在自選');
            return;
        }
        const updated = items.concat(
            missing.map(sid => ({
                stock_id: sid,
                stock_name: '',
                added_at: new Date().toISOString(),
            }))
        );
        // 受 MAX_ITEMS 限制
        Watchlist.save(updated);
    },

    esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    },
};