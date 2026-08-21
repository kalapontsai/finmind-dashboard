/* Portfolio Forecast — 前端邏輯 */
(function () {
  'use strict';

  // ────────── 工具 ──────────
  const $ = (id) => document.getElementById(id);
  const fmtPct = (x) => {
    if (x == null || (typeof x === 'number' && isNaN(x))) return '—';
    return (x * 100).toFixed(2) + '%';
  };
  const fmtMoney = (x) => {
    if (x == null || (typeof x === 'number' && isNaN(x))) return '—';
    return Number(x).toLocaleString('zh-TW', { maximumFractionDigits: 0 });
  };
  const fmtFloat = (x, d = 3) => {
    if (x == null || (typeof x === 'number' && isNaN(x))) return '—';
    return Number(x).toFixed(d);
  };

  // ────────── State ──────────
  let lastResult = null;
  let navChart = null;
  let rollChart = null;
  let currentMode = 'common';

  // ────────── 啟動：載入 profiles ──────────
  async function loadProfiles() {
    try {
      const r = await fetch('/api/profiles');
      const d = await r.json();
      const sel = $('profileSel');
      sel.innerHTML = '';
      const profiles = d.profiles || [];
      if (profiles.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '（user_profile/ 沒有 CSV）';
        sel.appendChild(opt);
        sel.disabled = true;
        $('btnRun').disabled = true;
        return;
      }
      profiles.forEach((p) => {
        const opt = document.createElement('option');
        opt.value = p;
        opt.textContent = p + '.csv';
        sel.appendChild(opt);
      });
      // 預設選 liyu_stock
      if (profiles.includes('liyu_stock')) sel.value = 'liyu_stock';
      // 動態載入預覽
      sel.addEventListener('change', () => previewProfile(sel.value));
      previewProfile(sel.value);
    } catch (e) {
      $('err').textContent = '載入名單失敗：' + e.message;
      $('err').classList.add('show');
    }
  }

  async function previewProfile(name) {
    if (!name) {
      $('profileMeta').textContent = '';
      return;
    }
    try {
      const r = await fetch('/api/profile/' + encodeURIComponent(name));
      const d = await r.json();
      if (!r.ok) {
        $('profileMeta').textContent = '⚠️ ' + (d.error || '讀不到');
        return;
      }
      $('profileMeta').textContent = `共 ${d.count} 檔股票`;
    } catch (e) {
      $('profileMeta').textContent = '⚠️ ' + e.message;
    }
  }

  // ────────── 上傳 CSV 名單 ──────────
  async function uploadProfile(file) {
    const fd = new FormData();
    fd.append('file', file);
    const btn = $('btnUploadProfile');
    btn.disabled = true;
    btn.textContent = '⏳ 上傳中…';
    try {
      const r = await fetch('/api/upload_profile', { method: 'POST', body: fd });
      const d = await r.json();
      if (!r.ok) {
        showErr('上傳失敗：' + (d.error || 'unknown'));
        return;
      }
      clearErr();
      await loadProfiles();
      const sel = $('profileSel');
      sel.value = d.name;
      if (sel.value === d.name) {
        // 手動觸發 change 讓 preview 跑一次
        sel.dispatchEvent(new Event('change'));
      }
    } catch (e) {
      showErr('上傳失敗：' + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = '📁 上傳 CSV';
    }
  }

  function bindUpload() {
    const btn = $('btnUploadProfile');
    const input = $('fileUploadProfile');
    btn.addEventListener('click', () => input.click());
    input.addEventListener('change', () => {
      if (input.files.length === 0) return;
      const f = input.files[0];
      if (!f.name.toLowerCase().endsWith('.csv')) {
        showErr('只接受 .csv 檔案');
        input.value = '';
        return;
      }
      uploadProfile(f);
      // 清空 value 才能重複上傳同檔
      input.value = '';
    });
  }

  // ────────── 錯誤顯示 ──────────
  function showErr(msg) {
    const e = $('err');
    e.textContent = msg;
    e.classList.add('show');
  }
  function clearErr() {
    const e = $('err');
    e.textContent = '';
    e.classList.remove('show');
  }

  // ────────── 主分析 ──────────
  async function runAnalyze(e) {
    e.preventDefault();
    clearErr();
    $('out').hidden = true;
    $('btnRun').disabled = true;
    $('btnExportPdf').disabled = true;
    $('btnExportHtml').disabled = true;
    $('status').textContent = '分析中（首次抓 FinMind 需 30~60 秒）...';

    const f = e.target;
    const body = {
      profile: f.profile.value,
      n: parseInt(f.n.value, 10),
      pv: f.pv.value ? parseFloat(f.pv.value) : null,
      weights: f.weights.value.trim() || null,
      benchmark: f.benchmark.value.trim() || null,
      fee_buy: parseFloat(f.fee_buy.value || 0) / 100,
      tax_sell: parseFloat(f.tax_sell.value || 0) / 100,
      slippage: parseFloat(f.slippage.value || 0) / 100,
    };

    try {
      const r = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) {
        showErr(d.error || '分析失敗');
        $('status').textContent = '';
        return;
      }
      lastResult = d;
      renderAll(d);
      $('btnExportPdf').disabled = false;
      $('btnExportHtml').disabled = false;
      $('status').textContent = '✓ 完成';
    } catch (e) {
      showErr('網路錯誤：' + e.message);
    } finally {
      $('btnRun').disabled = false;
    }
  }

  // ────────── 渲染：Ticker 驗證結果 ──────────
  function renderTickerMatch(d) {
    const wrap = $('tickerMatch');
    const ins = d.inputs;
    const tm = ins.ticker_match || {};
    const invalid = ins.invalid_tickers || [];
    const short = new Set(ins.short_history || []);

    const matchedRows = Object.values(tm)
      .sort((a, b) => a.stock_id.localeCompare(b.stock_id))
      .map((m) => {
        const isShort = short.has(m.stock_id);
        const tag = m.source === 'exact' ? '' : '<small class="hint">(原 ' + m.matched_from[0] + ')</small>';
        const shortWarn = isShort ? ' <b style="color:#b42318">⚠️ 歷史 < ' + (ins.n || 10) + ' 年</b>' : '';
        return `<tr>
          <td>${m.stock_id}${tag}</td>
          <td>${m.stock_name || '—'}</td>
          <td>${m.industry || '—'}</td>
          <td>${m.type || '—'}</td>
          <td>${m.matched_from.join(', ')}</td>
          <td>${shortWarn}</td>
        </tr>`;
      })
      .join('');

    let invalidHtml = '';
    if (invalid.length > 0) {
      invalidHtml = `<div class="err show" style="margin-top:12px">
        <b>⚠️ 以下代號在 FinMind TaiwanStockInfo 查無資料，會被略過：</b>
        <ul>${invalid.map(x => `<li>${x.user_input}${x.stock_id ? ' → ' + x.stock_id : ''}：${x.reason}</li>`).join('')}</ul>
      </div>`;
    }

    wrap.innerHTML = `
      <table>
        <thead><tr>
          <th>stock_id</th><th>名稱</th><th>產業</th><th>市場</th>
          <th>使用者原始輸入</th><th>備註</th>
        </tr></thead>
        <tbody>${matchedRows || '<tr><td colspan="6" class="hint">無有效 ticker</td></tr>'}</tbody>
      </table>
      ${invalidHtml}
    `;
  }

  // ────────── 渲染：組合起始市值 ──────────
  function renderMarketValue(d) {
    const wrap = $('mv');
    const ins = d.inputs;
    const mv = d.market_value || {};
    const per = mv.per_stock || [];
    const missing = mv.missing || [];

    const rows = per
      .sort((a, b) => b.value - a.value)
      .map((s) => {
        const pct = mv.total > 0 ? (s.value / mv.total * 100).toFixed(1) : '0.0';
        return `<tr>
          <td>${s.ticker}</td>
          <td>${fmtMoney(s.shares)}</td>
          <td>${fmtFloat(s.close, 2)}</td>
          <td>${fmtMoney(s.value)}</td>
          <td>${pct}%</td>
        </tr>`;
      })
      .join('');

    const pvSourceText = ins.pv_source === 'market_value'
      ? '（自動從收盤價 × 股數計算）'
      : '（使用者手動輸入）';

    wrap.innerHTML = `
      <div class="kpi" style="grid-template-columns: repeat(3, 1fr);">
        <div><small>估值日</small><b>${mv.as_of || '—'}</b></div>
        <div><small>組合市值（PV）</small><b style="color:#17365d">${fmtMoney(mv.total)}</b></div>
        <div><small>市值來源</small><b style="font-size:14px">${pvSourceText}</b></div>
      </div>
      <table style="margin-top:14px">
        <thead><tr><th>股票</th><th>股數</th><th>收盤價</th><th>市值</th><th>權重</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="5" class="hint">無資料</td></tr>'}</tbody>
      </table>
      ${missing.length > 0 ? `<p class="err">缺少價格資料：${missing.join(', ')}</p>` : ''}
    `;
  }

  // ────────── 渲染：歷史診斷（per-stock 加強版）──────────
  function renderHistory(d) {
    const wrap = $('hist');
    const per = d.history.per_stock || {};
    const ov = d.history.overview || {};
    const ins = d.inputs;
    const short = new Set(ins.short_history || []);

    const rows = Object.entries(per)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([t, info]) => {
        const warn = short.has(t) ? ' <b style="color:#b42318">⚠️</b>' : '';
        return `<tr>
          <td>${t}${warn}</td>
          <td>${info.start || '—'}</td>
          <td>${info.end || '—'}</td>
          <td>${info.rows || 0}</td>
          <td>${(info.years || 0).toFixed(2)}</td>
          <td>${info.first_close != null ? fmtFloat(info.first_close, 2) : '—'}</td>
        </tr>`;
      })
      .join('');

    wrap.innerHTML = `
      <table>
        <thead><tr>
          <th>股票</th><th>第一天</th><th>最後一天</th>
          <th>資料點</th><th>歷史年數</th><th>首日收盤</th>
        </tr></thead>
        <tbody>${rows}</tbody>
        <tfoot>
          <tr><th>股票數</th><td colspan="2">${ov.stocks || 0}</td>
            <th>最短 / 中位 / 最長</th>
            <td colspan="2">${(ov.min_years || 0).toFixed(2)} / ${(ov.median_years || 0).toFixed(2)} / ${(ov.max_years || 0).toFixed(2)} 年</td></tr>
        </tfoot>
      </table>`;
  }

  // ────────── 渲染：KPI + NAV ──────────
  function renderMode(mode) {
    const r = lastResult[mode];
    if (!r) {
      $('kpi').innerHTML = '<div class="hint">此模式無結果</div>';
      return;
    }
    const m = r.metrics;
    const kpi = [
      ['開始', m.start || '—'],
      ['結束', m.end || '—'],
      ['年數', fmtFloat(m.years, 2)],
      ['Total Return', fmtPct(m.total_return)],
      ['CAGR', fmtPct(m.cagr)],
      ['MDD', fmtPct(m.mdd)],
      ['Volatility', fmtPct(m.volatility)],
      ['Sharpe', fmtFloat(m.sharpe)],
    ];
    $('kpi').innerHTML = kpi
      .map(([k, v]) => `<div><small>${k}</small><b>${v}</b></div>`)
      .join('');

    renderNavChart();
  }

  function renderNavChart() {
    const r = lastResult[currentMode];
    const series = r.nav || [];
    const labels = series.map((p) => p.date);
    const data = series.map((p) => p.nav);

    if (navChart) navChart.destroy();
    const ctx = document.getElementById('navChart');
    navChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Portfolio NAV (' + currentMode + ')',
          data,
          borderColor: '#17365d',
          backgroundColor: 'rgba(23, 54, 93, 0.08)',
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.1,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: true, position: 'top' } },
        scales: {
          x: { ticks: { maxTicksLimit: 8, autoSkip: true }, grid: { display: false } },
          y: { ticks: { maxTicksLimit: 6 } },
        },
      },
    });
  }

  // ────────── 渲染：Forecast ──────────
  function renderForecast(d) {
    const f = d.forecast;
    $('fcBasis').textContent = f.basis || 'common';
    const tb = $('fcTable').querySelector('tbody');
    tb.innerHTML = (f.scenarios || [])
      .map((s) => {
        const isBase = s.label === 'Base';
        return `<tr class="${isBase ? 'highlight' : ''}">
          <td>${s.label}</td>
          <td>P${(s.quantile * 100) | 0}</td>
          <td>${fmtPct(s.cagr)}</td>
          <td>${fmtMoney(f.pv)}</td>
          <td><b>${fmtMoney(s.fv)}</b></td>
          <td>${fmtFloat(s.multiplier, 2)}x</td>
        </tr>`;
      })
      .join('');
    $('rCount').textContent = f.r_count;
    const basisMap = { common: '全體共同期間', dynamic: '逐步加入模式', full: '各標的完整歷史' };
    const basisZh = basisMap[f.basis] || f.basis || '—';
    $('forecastNote').innerHTML = `取「<b>${basisZh}</b>」模式下所有 N 年持有期間的歷史收益分布，依分位數算出 5 個情境的終值。FV = 目前資產 × (1+r)^N。<b>不模擬未來逐年路徑</b>。` + (d.inputs.pv_cost_text ? ' ' + d.inputs.pv_cost_text : '');

    const rs = f.rolling || [];
    if (rollChart) rollChart.destroy();
    const ctx = document.getElementById('rollChart');
    rollChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: rs.map((x) => x.end),
        datasets: [{
          label: 'Rolling N-Year CAGR %',
          data: rs.map((x) => x.cagr * 100),
          borderColor: '#58a6ff',
          backgroundColor: 'rgba(88, 166, 255, 0.1)',
          borderWidth: 1.5,
          pointRadius: 2,
          tension: 0.1,
          fill: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: true, position: 'top' } },
        scales: {
          x: { ticks: { maxTicksLimit: 8, autoSkip: true }, grid: { display: false } },
          y: { ticks: { maxTicksLimit: 6 } },
        },
      },
    });
  }

  // ────────── 全部渲染 ──────────
  function renderAll(d) {
    renderTickerMatch(d);
    renderMarketValue(d);
    renderHistory(d);
    renderMode(currentMode);
    renderForecast(d);
    renderBenchmark(d);
    $('out').hidden = false;
  }

  function renderBenchmark(d) {
    const card = $('benchCard');
    const wrap = $('bench');
    const b = d.benchmark;
    if (!b || !b.metrics) { card.hidden = true; return; }
    card.hidden = false;
    const m = b.metrics;
    const baseMetrics = (d.dynamic && d.dynamic.metrics) || (d.common && d.common.metrics) || {};
    const rows = [
      ['年數', fmtFloat(m.years, 2), fmtFloat(baseMetrics.years, 2)],
      ['CAGR', fmtPct(m.cagr), fmtPct(baseMetrics.cagr)],
      ['MDD', fmtPct(m.mdd), fmtPct(baseMetrics.mdd)],
      ['Vol', fmtPct(m.volatility), fmtPct(baseMetrics.volatility)],
      ['Sharpe', fmtFloat(m.sharpe, 3), fmtFloat(baseMetrics.sharpe, 3)],
    ];
    const delta = (a, b) => (a - b);
    const diffClass = (bench, port) => {
      const d = bench - port;
      if (Math.abs(d) < 0.001) return '';
      return d > 0 ? ' style="color:#3fb950"' : ' style="color:#f85149"';
    };
    wrap.innerHTML = `
      <table>
        <thead><tr><th>指標</th><th>Benchmark ${b.ticker}</th><th>組合 (Dynamic)</th></tr></thead>
        <tbody>
          <tr><td>年數</td><td>${fmtFloat(m.years, 2)}</td><td>${fmtFloat(baseMetrics.years, 2)}</td></tr>
          <tr><td>CAGR</td><td${diffClass(m.cagr, baseMetrics.cagr)}>${fmtPct(m.cagr)}</td><td>${fmtPct(baseMetrics.cagr)}</td></tr>
          <tr><td>MDD</td><td${diffClass(baseMetrics.mdd, m.mdd)}>${fmtPct(m.mdd)}</td><td>${fmtPct(baseMetrics.mdd)}</td></tr>
          <tr><td>Vol</td><td>${fmtPct(m.volatility)}</td><td>${fmtPct(baseMetrics.volatility)}</td></tr>
          <tr><td>Sharpe</td><td${diffClass(m.sharpe, baseMetrics.sharpe)}>${fmtFloat(m.sharpe, 3)}</td><td>${fmtFloat(baseMetrics.sharpe, 3)}</td></tr>
        </tbody>
      </table>
      <p class="hint">差異以綠/紅標示：綠色 = 該指標 <b>正向優勢</b>（CAGR/Sharpe 越高越好；MDD 越接近 0 越好）</p>`;
  }

  // ────────── Tab 切換 ──────────
  function bindTabs() {
    document.querySelectorAll('.tab').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        currentMode = btn.dataset.mode;
        if (lastResult) renderMode(currentMode);
      });
    });
  }

  // ────────── 匯出 ──────────
  async function exportResult(fmt) {
    if (!lastResult) return;
    const r = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        result: lastResult,
        format: fmt,
        profile_name: lastResult.inputs.profile,
      }),
    });
    const d = await r.json();
    if (!r.ok) {
      showErr(d.error || '匯出失敗');
      return;
    }
    window.open(d.url, '_blank');
  }

  // ────────── 綁定 ──────────
  document.addEventListener('DOMContentLoaded', () => {
    $('fAnalyze').addEventListener('submit', runAnalyze);
    $('btnExportPdf').addEventListener('click', () => exportResult('pdf'));
    $('btnExportHtml').addEventListener('click', () => exportResult('html'));
    bindTabs();
    bindUpload();
    loadProfiles();
  });
})();
