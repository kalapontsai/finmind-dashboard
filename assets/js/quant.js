/**
 * 多因子量化回測頁
 * - 顯示最新 HTML 報告（iframe）
 * - 「重新跑回測」按鈕（呼叫 PHP API）
 * - 顯示上次執行時間、token 狀態等狀態
 */

const QuantPage = {
    state: null,

    async render(container) {
        // 用 cache-bust 避免 iframe 拿快取
        const cacheBust = Date.now();

        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <div class="card-title">回測狀態</div>
                    <div style="display:flex; gap:8px; align-items:center;">
                        <button class="btn btn-orange" id="runBtn">🔄 重新跑回測</button>
                        <button class="btn btn-ghost" id="reloadBtn">↻ 重新載入報告</button>
                    </div>
                </div>
                <div id="statusBox" style="display:flex; gap:24px; flex-wrap:wrap; padding:8px 0;">
                    <div><span style="color:var(--text-muted); font-size:12px;">報告位置</span><br><code style="font-size:13px;">/finmind/quant/output/report.html</code></div>
                    <div><span style="color:var(--text-muted); font-size:12px;">最後更新</span><br><span id="lastUpdate" style="font-size:13px;">載入中...</span></div>
                    <div><span style="color:var(--text-muted); font-size:12px;">容器 Python</span><br><span id="pyAvail" style="font-size:13px;">檢查中...</span></div>
                </div>
                <div id="runMsg" style="margin-top:8px;"></div>
            </div>

            <div class="card">
                <div class="card-header">
                    <div class="card-title">回測報告</div>
                    <a href="/finmind/quant/output/report.html" target="_blank" class="btn btn-ghost" style="padding:4px 10px; font-size:12px;">在新分頁開啟 ↗</a>
                </div>
                <iframe id="reportFrame" src="/finmind/quant/output/report.html?bust=${cacheBust}"
                    style="width:100%; height:2400px; border:1px solid var(--border); border-radius:8px; background:#0d1117;"
                    loading="lazy"></iframe>
            </div>
        `;

        document.getElementById('runBtn').addEventListener('click', () => this.run());
        document.getElementById('reloadBtn').addEventListener('click', () => this.reloadReport());

        await this.checkStatus();
    },

    async checkStatus() {
        // 1. 報告檔案資訊
        try {
            const res = await fetch('/finmind/api/quant_status.php', { cache: 'no-store' });
            const data = await res.json();
            document.getElementById('lastUpdate').textContent = data.last_update || '無';
            document.getElementById('pyAvail').textContent = data.python_available
                ? '✅ 可用（直接執行）'
                : '❌ 不可用（需 WSL 手動跑）';
            document.getElementById('pyAvail').style.color = data.python_available
                ? 'var(--green)' : 'var(--orange)';
        } catch (e) {
            document.getElementById('lastUpdate').textContent = '查詢失敗';
        }
    },

    reloadReport() {
        const iframe = document.getElementById('reportFrame');
        iframe.src = `/finmind/quant/output/report.html?bust=${Date.now()}`;
        this.checkStatus();
    },

    async run() {
        const btn = document.getElementById('runBtn');
        const msg = document.getElementById('runMsg');
        btn.disabled = true;
        btn.textContent = '⏳ 執行中...';
        msg.innerHTML = '<div class="state-box"><div class="spinner"></div><div>正在呼叫回測引擎（首次可能需 1-3 分鐘）</div></div>';

        try {
            const res = await fetch('/finmind/api/quant_run.php', { method: 'POST' });
            const data = await res.json();

            if (data.ok) {
                msg.innerHTML = `
                    <div class="kpi" style="background:rgba(63, 185, 80, 0.1); padding:12px; border-radius:8px; border-left:4px solid var(--green);">
                        <div class="label" style="color:var(--green); font-size:12px;">✅ 執行成功</div>
                        <div style="font-size:13px; margin-top:4px;">總報酬: <strong>${data.kpis.total_return}</strong> &nbsp;|&nbsp; B&amp;H: ${data.kpis.benchmark_return} &nbsp;|&nbsp; Sharpe: ${data.kpis.sharpe}</div>
                        <div style="font-size:11px; color:var(--text-muted); margin-top:4px;">耗時 ${data.elapsed_sec}s</div>
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

    esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    },
};