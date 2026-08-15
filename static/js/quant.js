/**
 * 多因子量化回測頁
 * - 策略啟用 checkbox + 當前參數 hover tooltip + weight 輸入
 * - 「重新跑回測」按鈕（呼叫 Flask API，帶啟用策略）
 * - 顯示最新 HTML 報告（iframe）
 * - 顯示上次執行時間狀態
 */


// ===== debounce（v1.4 P3-4） =====
function debounce(fn, ms) {
  let t;
  return function (...args) {
    clearTimeout(t);
    t = setTimeout(() => fn.apply(this, args), ms);
  };
}

const STRATEGY_LABELS = {
    value:    { name: '價值', icon: '💎', desc: 'PER rank_pct（PER 越低 → 排名越高）' },
    momentum: { name: '動能', icon: '🚀', desc: 'N 日 close.pct_change rank_pct' },
    quality:  { name: '品質', icon: '🌟', desc: '由財務報表長表計 ROE（淨利 / 歸屬母公司權益） rank_pct' },
};

const QuantPage = {
    state: { strategies: [], saving: false },

    async render(container) {
        const cacheBust = Date.now();

        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <div class="card-title">策略選擇與權重</div>
                    <div style="display:flex; gap:8px; align-items:center;">
                        <button class="btn btn-ghost" id="normalizeBtn" title="將啟用策略的權重自動歸一到總和=1.0">∑ 歸一</button>
                        <span id="weightSum" style="color:var(--text-muted); font-size:12px;">總和：—</span>
                    </div>
                </div>
                <div id="strategyList" style="display:flex; flex-direction:column; gap:8px; padding:4px 0;">
                    <div style="color:var(--text-muted); font-size:12px;">載入中…</div>
                </div>
                <div id="strategyMsg" style="font-size:12px; color:var(--text-muted); min-height:18px; margin-top:4px;"></div>
            </div>

            <div class="card">
                <div class="card-header">
                    <div class="card-title">回測參數</div>
                </div>
                <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:12px; padding:4px 0;">
                    <div>
                        <label style="font-size:12px; color:var(--text-muted);">起始日</label>
                        <input type="date" id="startDate" value="2023-01-01" style="width:100%; padding:6px 8px; background:var(--bg-soft); border:1px solid var(--border); color:var(--text); border-radius:6px;">
                    </div>
                    <div>
                        <label style="font-size:12px; color:var(--text-muted);">結束日</label>
                        <input type="date" id="endDate" style="width:100%; padding:6px 8px; background:var(--bg-soft); border:1px solid var(--border); color:var(--text); border-radius:6px;">
                    </div>
                    <div>
                        <label style="font-size:12px; color:var(--text-muted);">換倉頻率</label>
                        <select id="rebalanceFreq" style="width:100%; padding:6px 8px; background:var(--bg-soft); border:1px solid var(--border); color:var(--text); border-radius:6px;">
                            <option value="monthly" selected>每月</option>
                            <option value="quarterly">每季</option>
                            <option value="daily">每日</option>
                        </select>
                    </div>
                    <div>
                        <label style="font-size:12px; color:var(--text-muted);">Top N</label>
                        <input type="number" id="topN" min="1" max="20" step="1" value="5" style="width:100%; padding:6px 8px; background:var(--bg-soft); border:1px solid var(--border); color:var(--text); border-radius:6px;">
                    </div>
                    <div>
                        <label style="font-size:12px; color:var(--text-muted);">買入手續費 (%)</label>
                        <input type="number" id="feeBuy" min="0" step="0.01" value="0.1425" style="width:100%; padding:6px 8px; background:var(--bg-soft); border:1px solid var(--border); color:var(--text); border-radius:6px;">
                    </div>
                    <div>
                        <label style="font-size:12px; color:var(--text-muted);">賣出手續費 (%)</label>
                        <input type="number" id="feeSell" min="0" step="0.01" value="0.1425" style="width:100%; padding:6px 8px; background:var(--bg-soft); border:1px solid var(--border); color:var(--text); border-radius:6px;">
                    </div>
                    <div>
                        <label style="font-size:12px; color:var(--text-muted);">賣出證交稅 (%)</label>
                        <input type="number" id="taxSell" min="0" step="0.01" value="0.3" style="width:100%; padding:6px 8px; background:var(--bg-soft); border:1px solid var(--border); color:var(--text); border-radius:6px;">
                    </div>
                    <div>
                        <label style="font-size:12px; color:var(--text-muted);">滑價 (%)</label>
                        <input type="number" id="slippage" min="0" step="0.01" value="0.1" style="width:100%; padding:6px 8px; background:var(--bg-soft); border:1px solid var(--border); color:var(--text); border-radius:6px;">
                    </div>
                    <div>
                        <label style="font-size:12px; color:var(--text-muted);" title="20 日均量最低門檻（張）；0 = 不過濾">最低 20 日均量 (張)</label>
                        <input type="number" id="minLiquidity" min="0" step="100" value="0" style="width:100%; padding:6px 8px; background:var(--bg-soft); border:1px solid var(--border); color:var(--text); border-radius:6px;">
                    </div>
                    <div style="display:flex; align-items:flex-end; gap:12px;">
                        <label style="display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text-muted); cursor:pointer;">
                            <input type="checkbox" id="walkForwardCb"> 🔬 Walk-forward
                        </label>
                        <div style="flex:1;">
                            <label style="font-size:12px; color:var(--text-muted);" title="訓練期佔比；驗證期 = 1 - train_pct">訓練期佔比</label>
                            <input type="number" id="trainPct" min="0.5" max="0.95" step="0.05" value="0.7" disabled
                                style="width:100%; padding:6px 8px; background:var(--bg-soft); border:1px solid var(--border); color:var(--text); border-radius:6px;">
                        </div>
                    </div>
                </div>
                <div id="paramsMsg" style="font-size:12px; color:var(--text-muted); min-height:18px; margin-top:4px;"></div>
            </div>

            <div class="card">
                <div class="card-header">
                    <div class="card-title">回測狀態</div>
                    <div style="display:flex; gap:8px; align-items:center;">
                        <button class="btn btn-orange" id="runBtn">🔄 重新跑回測</button>
                        <button class="btn btn-ghost" id="reloadBtn">↻ 重新載入報告</button>
                    </div>
                </div>
                <div id="statusBox" style="display:flex; gap:24px; flex-wrap:wrap; padding:8px 0;">
                    <div><span style="color:var(--text-muted); font-size:12px;">最新報告（時間序）</span><br><code id="archiveName" style="font-size:13px;">/quant/output/report.html</code></div>
                    <div><span style="color:var(--text-muted); font-size:12px;">最後更新</span><br><span id="lastUpdate" style="font-size:13px;">載入中...</span></div>
                    <div><span style="color:var(--text-muted); font-size:12px;">實際區間</span><br><span id="rangeInfo" style="font-size:13px;">—</span></div>
                    <div><span style="color:var(--text-muted); font-size:12px;">實際 Top N</span><br><span id="topNInfo" style="font-size:13px;">—</span></div>
                    <div><span style="color:var(--text-muted); font-size:12px;">實際股票池</span><br><span id="poolInfo" style="font-size:13px;">—</span></div>
                </div>
                <div id="runMsg" style="margin-top:8px;"></div>
            </div>

            <div class="card">
                <div class="card-header">
                    <div class="card-title">回測報告</div>
                    <div style="display:flex; gap:8px;">
                        <a id="openLatest" href="/quant/output/report.html" target="_blank" class="btn btn-ghost" style="padding:4px 10px; font-size:12px;">在新分頁開啟 latest ↗</a>
                    </div>
                </div>
                <iframe id="reportFrame" src="/quant/output/report.html?bust=${cacheBust}"
                    style="width:100%; height:2400px; border:1px solid var(--border); border-radius:8px; background:#0d1117;"
                    loading="lazy"></iframe>
                <div id="recentReports" style="margin-top:8px; font-size:11px; color:var(--text-muted);"></div>
            </div>
        `;

        document.getElementById('runBtn').addEventListener('click', () => this.run());
        document.getElementById('reloadBtn').addEventListener('click', () => this.reloadReport());
        document.getElementById('normalizeBtn').addEventListener('click', () => this.normalizeWeights());
        // v1.4 walk-forward 切換：勾選啟用時才開啟 train_pct 輸入
        const walkForwardCb = document.getElementById('walkForwardCb');
        const trainPctEl = document.getElementById('trainPct');
        if (walkForwardCb && trainPctEl) {
            walkForwardCb.addEventListener('change', debounce(() => {
                trainPctEl.disabled = !walkForwardCb.checked;
            }, 250));
        }

        await this.loadStrategies();
        await this.checkStatus();
    },

    // ────────────────────────── 策略載入與渲染 ──────────────────────────

    async loadStrategies() {
        try {
            const data = await FinMindAPI.strategiesList();
            this.state.strategies = data.strategies || [];
            this.renderStrategyList();
            this.updateWeightSum();
        } catch (e) {
            document.getElementById('strategyList').innerHTML =
                `<div class="error-text">❌ 載入失敗：${this.esc(e.message)}</div>`;
        }
    },

    renderStrategyList() {
        const list = document.getElementById('strategyList');
        if (!this.state.strategies.length) {
            list.innerHTML = '<div style="color:var(--text-muted); font-size:12px;">沒有可用的策略。</div>';
            return;
        }

        list.innerHTML = this.state.strategies.map(s => this._strategyRowHtml(s)).join('');

        // 綁定事件
        for (const s of this.state.strategies) {
            const cb = document.getElementById(`strat-cb-${s.name}`);
            const wt = document.getElementById(`strat-w-${s.name}`);
            if (cb) {
                cb.addEventListener('change', debounce(() => {
                    s.enabled = cb.checked;
                    if (wt) wt.disabled = !cb.checked;
                    this.updateWeightSum();
                    this.saveConfig();
                }, 250));
            }
            if (wt) {
                wt.addEventListener('input', debounce(() => {
                    const v = parseFloat(wt.value);
                    s.weight = isNaN(v) ? 0 : Math.max(0, Math.min(1, v));
                    this.updateWeightSum();
                }, 250));
                wt.addEventListener('change', debounce(() => {
                    this.saveConfig();
                }, 250));
            }
        }
    },

    _strategyRowHtml(s) {
        const meta = STRATEGY_LABELS[s.name] || { name: s.name, icon: '◆', desc: s.type || s.name };
        const params = s.params || {};
        const paramsTooltip = Object.entries(params)
            .map(([k, v]) => `${k} = ${v}`)
            .join('\n') || '（無參數）';
        const enabled = !!s.enabled;
        const weight = (typeof s.weight === 'number') ? s.weight : 0;

        return `
            <div class="strat-row" data-name="${this.esc(s.name)}"
                 style="display:flex; align-items:center; gap:12px; padding:10px 12px;
                        border:1px solid var(--border); border-radius:8px; background:var(--bg-soft);">
                <label style="display:flex; align-items:center; gap:8px; cursor:pointer; flex:1;">
                    <input type="checkbox" id="strat-cb-${this.esc(s.name)}" ${enabled ? 'checked' : ''}>
                    <span style="font-size:18px;">${meta.icon}</span>
                    <span>
                        <span style="font-weight:600;">${this.esc(meta.name)}</span>
                        <span style="color:var(--text-muted); font-size:12px; margin-left:8px;">${this.esc(meta.desc)}</span>
                    </span>
                    <span class="info-tip" data-tip="${this.esc(paramsTooltip)}"
                          style="margin-left:8px; color:var(--text-muted); cursor:help; border-bottom:1px dotted var(--text-muted); font-size:11px;"
                          title="${this.esc(paramsTooltip)}">
                        ⚙ 當前參數
                    </span>
                </label>
                <div style="display:flex; align-items:center; gap:6px;">
                    <label style="color:var(--text-muted); font-size:12px;">權重</label>
                    <input type="number" id="strat-w-${this.esc(s.name)}" min="0" max="1" step="0.05"
                           value="${weight}" ${enabled ? '' : 'disabled'}
                           style="width:80px;">
                </div>
            </div>
        `;
    },

    updateWeightSum() {
        const sum = this.state.strategies
            .filter(s => s.enabled)
            .reduce((acc, s) => acc + (Number(s.weight) || 0), 0);
        const el = document.getElementById('weightSum');
        if (!el) return;
        const warn = Math.abs(sum - 1) > 0.01;
        el.textContent = `總和：${sum.toFixed(2)}${warn ? '（建議 = 1.00，請按「歸一」）' : ''}`;
        el.style.color = warn ? 'var(--orange)' : 'var(--text-muted)';
    },

    normalizeWeights() {
        const enabled = this.state.strategies.filter(s => s.enabled);
        if (enabled.length === 0) return;
        const sum = enabled.reduce((acc, s) => acc + (Number(s.weight) || 0), 0);
        if (sum <= 0) {
            // 全部 0 → 平均分配
            const each = +(1 / enabled.length).toFixed(2);
            let assigned = 0;
            enabled.forEach((s, i) => {
                if (i === enabled.length - 1) {
                    s.weight = +(1 - assigned).toFixed(2);
                } else {
                    s.weight = each;
                    assigned += each;
                }
            });
        } else {
            enabled.forEach(s => {
                s.weight = +(s.weight / sum).toFixed(2);
            });
        }
        this.renderStrategyList();
        this.updateWeightSum();
        this.saveConfig();
    },

    async saveConfig() {
        if (this.state.saving) return;
        this.state.saving = true;
        const msg = document.getElementById('strategyMsg');
        if (msg) msg.textContent = '儲存中…';

        try {
            const payload = this.state.strategies.map(s => ({
                name: s.name,
                enabled: !!s.enabled,
                weight: Number(s.weight) || 0,
            }));
            await FinMindAPI.strategiesSaveConfig(payload);
            if (msg) {
                msg.textContent = `已儲存 ${new Date().toLocaleTimeString()}`;
                msg.style.color = 'var(--green)';
                setTimeout(() => { if (msg.textContent.startsWith('已儲存')) msg.textContent = ''; }, 2000);
            }
        } catch (e) {
            if (msg) {
                msg.textContent = `儲存失敗：${e.message}`;
                msg.style.color = 'var(--red)';
            }
        } finally {
            this.state.saving = false;
        }
    },

    // ────────────────────────── 狀態 / 跑回測 ──────────────────────────

    async checkStatus() {
        try {
            const data = await FinMindAPI.quantStatus();
            document.getElementById('lastUpdate').textContent = data.last_update || '無';

            const rangeEl = document.getElementById('rangeInfo');
            if (data.range_start && data.range_end) {
                rangeEl.textContent = `${data.range_start} ~ ${data.range_end}`;
            } else {
                rangeEl.textContent = '—';
            }

            // v1.4 P3-5：顯示實際跑的參數 + 時間序檔名
            const cfg = data.cfg || {};
            const topNEl = document.getElementById('topNInfo');
            const poolEl = document.getElementById('poolInfo');
            topNEl.textContent = cfg.top_n != null ? `${cfg.top_n} 檔` : '—';
            const poolSize = Array.isArray(cfg.pool) ? cfg.pool.length : (cfg.pool == null ? 'auto' : '—');
            poolEl.textContent = `${poolSize} 檔`;

            // 時間序檔名
            const archiveEl = document.getElementById('archiveName');
            const openLatest = document.getElementById('openLatest');
            if (data.archive_html) {
                archiveEl.textContent = `report.html (= ${data.archive_html})`;
                openLatest.href = `/quant/output/${data.archive_html}`;
            } else {
                archiveEl.textContent = '/quant/output/report.html';
                openLatest.href = '/quant/output/report.html';
            }

            // 最近 10 份報告列表
            const recentEl = document.getElementById('recentReports');
            if (Array.isArray(data.recent_reports) && data.recent_reports.length > 0) {
                recentEl.innerHTML = '歷史報告：' + data.recent_reports.map(r =>
                    `<a href="/quant/output/${r.name}" target="_blank" style="color:var(--text-muted); margin-right:12px; text-decoration:none;">${r.name}</a>`
                ).join('');
            } else {
                recentEl.innerHTML = '';
            }
        } catch (e) {
            document.getElementById('lastUpdate').textContent = '查詢失敗';
        }
    },

    reloadReport() {
        const iframe = document.getElementById('reportFrame');
        iframe.src = `/quant/output/report.html?bust=${Date.now()}`;
        this.checkStatus();
    },

    async run() {
        const btn = document.getElementById('runBtn');
        const msg = document.getElementById('runMsg');
        btn.disabled = true;
        btn.textContent = '⏳ 執行中...';
        msg.innerHTML = '<div class="state-box"><div class="spinner"></div><div>正在呼叫回測引擎（首次可能需 1-3 分鐘）</div></div>';

        try {
            // 帶目前啟用的策略與權重
            const enabled = this.state.strategies.filter(s => s.enabled).map(s => ({
                name: s.name,
                weight: s.weight,
            }));

            if (enabled.length === 0) {
                msg.innerHTML = `<div class="error-text">❌ 請至少啟用一個策略</div>`;
                btn.disabled = false;
                btn.textContent = '🔄 重新跑回測';
                return;
            }

            // 收集回測參數（轉百分比 → 小數：0.1425% → 0.001425）
            const pct = (v) => (parseFloat(v) || 0) / 100;
            const startDate = document.getElementById('startDate').value;
            const endDate = document.getElementById('endDate').value || new Date().toISOString().slice(0, 10);
            const topN = parseInt(document.getElementById('topN').value, 10) || 5;
            const rebalanceFreq = document.getElementById('rebalanceFreq').value || 'monthly';

            const params = {
                strategies: enabled,
                start: startDate,
                end: endDate,
                top_n: topN,
                rebalance_freq: rebalanceFreq,
                fee_buy: pct(document.getElementById('feeBuy').value),
                fee_sell: pct(document.getElementById('feeSell').value),
                tax_sell: pct(document.getElementById('taxSell').value),
                slippage: pct(document.getElementById('slippage').value),
                min_liquidity_shares: parseInt(document.getElementById('minLiquidity').value, 10) || 0,
            };
            // v1.4 walk-forward
            const walkForwardCb = document.getElementById('walkForwardCb');
            if (walkForwardCb && walkForwardCb.checked) {
                params.walk_forward = true;
                const trainPctEl = document.getElementById('trainPct');
                params.train_pct = parseFloat(trainPctEl.value) || 0.7;
            }

            const data = await FinMindAPI.quantRun(params);

            // ── v1.4 P3-4 修補：async job_id 分支 ──
            // 舊 bug：data.ok=true 就呼叫 pct(k.total_return)，但 run_quant_async 不回 kpis
            //         → (undefined).toFixed(2) → 「Cannot read properties of undefined (reading 'toFixed')」
            // 新行為：若 data.job_id 存在 → 改走 polling；完成後從 sync get_status() 拿 kpis
            if (data.ok && data.job_id) {
                await this._pollJob(data.job_id, msg);
                return;  // _pollJob 會處理 btn.disabled / reloadReport
            }

            if (data.ok) {
                // 同步 fallback（向後相容：若 backend 改回同步版）
                const k = data.kpis || {};
                const pctFmt = v => (v == null || isNaN(v)) ? '—' : `${(+v).toFixed(2)}%`;
                const sharpeFmt = v => (v == null || isNaN(v)) ? '—' : `${(+v).toFixed(2)}`;
                msg.innerHTML = `
                    <div class="kpi" style="background:rgba(63, 185, 80, 0.1); padding:12px; border-radius:8px; border-left:4px solid var(--green);">
                        <div class="label" style="color:var(--green); font-size:12px;">✅ 執行成功</div>
                        <div style="font-size:13px; margin-top:4px;">總報酬: <strong>${pctFmt(k.total_return)}</strong> &nbsp;|&nbsp; B&amp;H: ${pctFmt(k.pool_benchmark_return)} &nbsp;|&nbsp; Sharpe: ${sharpeFmt(k.sharpe)}</div>
                        <div style="font-size:11px; color:var(--text-muted); margin-top:4px;">耗時 ${data.elapsed_sec ?? '?'}s</div>
                    </div>
                `;
                this.reloadReport();
            } else {
                msg.innerHTML = `
                    <div class="error-text">
                        ❌ 執行失敗：${this.esc(data.error || '未知錯誤')}<br>
                        ${data.hint ? `<small style="color:var(--text-muted);">${this.esc(data.hint)}</small>` : ''}
                    </div>
                `;
            }
        } catch (e) {
            msg.innerHTML = `<div class="error-text">❌ 請求失敗：${this.esc(e.message)}</div>`;
        } finally {
            btn.disabled = false;
            btn.textContent = '🔄 重新跑回測';
        }
    },

    /**
     * v1.4 P3-4：輪詢 async job 直到 done / error
     * - 每 2 秒查一次 /api/quant_status?job_id=xxx
     * - 顯示進度（progress_pct / stage）
     * - 完成後從 sync get_status() 拿 kpis（讀 backtest_results.json）
     * - 完成 / 失敗都還原按鈕
     */
    async _pollJob(jobId, msg) {
        const btn = document.getElementById('runBtn');
        const POLL_INTERVAL_MS = 2000;
        const MAX_POLLS = 600;  // 最多 20 分鐘（1200s）
        const startedAt = Date.now();

        for (let i = 0; i < MAX_POLLS; i++) {
            await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));

            let status;
            try {
                status = await FinMindAPI.quantStatusById(jobId);
            } catch (e) {
                console.warn('poll status failed:', e);
                continue;  // 網路抖動不要直接放棄
            }

            const elapsed = Math.round((Date.now() - startedAt) / 1000);
            const pct = status.progress_pct ?? 0;
            const stage = status.stage ?? status.status ?? '執行中';

            msg.innerHTML = `
                <div class="state-box" style="flex-direction:column; align-items:stretch; gap:6px;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <div class="spinner"></div>
                        <div>${this.esc(stage)}（${pct}%）</div>
                    </div>
                    <div style="background:var(--bg-soft); border-radius:4px; height:6px; overflow:hidden;">
                        <div style="width:${pct}%; height:100%; background:var(--green); transition:width 0.3s;"></div>
                    </div>
                    <div style="font-size:11px; color:var(--text-muted);">已等待 ${elapsed}s · job_id: <code>${this.esc(jobId)}</code></div>
                </div>
            `;

            if (status.status === 'done') {
                await this._renderJobDone(msg);
                return;
            }
            if (status.status === 'error') {
                msg.innerHTML = `<div class="error-text">❌ 回測失敗：${this.esc(status.error || '未知錯誤')}</div>`;
                btn.disabled = false;
                btn.textContent = '🔄 重新跑回測';
                return;
            }
        }

        // timeout
        msg.innerHTML = `<div class="error-text">❌ 回測逾時（${MAX_POLLS * POLL_INTERVAL_MS / 1000}s 無進度）。請到 <code>quant/progress/</code> 查看 job <code>${this.esc(jobId)}</code> 狀態。</div>`;
        btn.disabled = false;
        btn.textContent = '🔄 重新跑回測';
    },

    /**
     * job done 後：抓 sync get_status()（讀 backtest_results.json 的 KPI）
     * 顯示 KPI + reload iframe
     */
    async _renderJobDone(msg) {
        const btn = document.getElementById('runBtn');
        let kpis = {};
        let lastUpdate = '';
        try {
            const sync = await FinMindAPI.quantStatus();
            kpis = sync.kpis || {};
            lastUpdate = sync.last_update || '';
        } catch (e) {
            console.warn('get sync status failed:', e);
        }

        const pctFmt = v => (v == null || isNaN(v)) ? '—' : `${(+v).toFixed(2)}%`;
        const numFmt = v => (v == null || isNaN(v)) ? '—' : `${(+v).toFixed(2)}`;

        msg.innerHTML = `
            <div class="kpi" style="background:rgba(63, 185, 80, 0.1); padding:12px; border-radius:8px; border-left:4px solid var(--green);">
                <div class="label" style="color:var(--green); font-size:12px;">✅ 執行成功</div>
                <div style="font-size:13px; margin-top:4px;">
                    總報酬: <strong>${pctFmt(kpis.total_return)}</strong>
                    &nbsp;|&nbsp; B&amp;H: ${pctFmt(kpis.pool_benchmark_return)}
                    &nbsp;|&nbsp; Sharpe: ${numFmt(kpis.sharpe)}
                    ${kpis.market_alpha != null ? `&nbsp;|&nbsp; α(vs 0050): ${pctFmt(kpis.market_alpha)}` : ''}
                </div>
                <div style="font-size:11px; color:var(--text-muted); margin-top:4px;">${lastUpdate ? `報告時間 ${lastUpdate}` : ''}</div>
            </div>
        `;
        this.reloadReport();
        btn.disabled = false;
        btn.textContent = '🔄 重新跑回測';
    },

    esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    },
};
