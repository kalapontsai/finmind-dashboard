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
      pv: parseFloat(f.pv.value),
      weights: f.weights.value.trim() || null,
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

  // ────────── 渲染：歷史診斷 ──────────
  function renderHistory(d) {
    const wrap = $('hist');
    const per = d.history.all_per_stock || {};
    const ov = d.history.overview || {};
    const rows = Object.entries(per)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([t, y]) => `<tr><td>${t}</td><td>${Number(y).toFixed(2)} 年</td></tr>`)
      .join('');
    wrap.innerHTML = `
      <table>
        <thead><tr><th>股票代號</th><th>歷史年數</th></tr></thead>
        <tbody>${rows}</tbody>
        <tfoot>
          <tr><th>股票數</th><td>${ov.stocks || 0}</td></tr>
          <tr><th>最短 / 中位 / 最長</th><td>
            ${(ov.min_years || 0).toFixed(2)} / ${(ov.median_years || 0).toFixed(2)} / ${(ov.max_years || 0).toFixed(2)} 年
          </td></tr>
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
    const tb = $('fcTable').querySelector('tbody');
    tb.innerHTML = (f.scenarios || [])
      .map((s) => {
        const isBase = s.name === 'Base';
        return `<tr class="${isBase ? 'highlight' : ''}">
          <td>${s.scenario}</td>
          <td>P${(s.percentile * 100) | 0}</td>
          <td>${fmtPct(s.cagr)}</td>
          <td>${fmtMoney(f.pv)}</td>
          <td><b>${fmtMoney(s.future_value)}</b></td>
          <td>${fmtFloat(s.multiple, 2)}x</td>
        </tr>`;
      })
      .join('');
    $('rCount').textContent = f.rolling_count;

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
    renderHistory(d);
    renderMode(currentMode);
    renderForecast(d);
    $('out').hidden = false;
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
    loadProfiles();
  });
})();
