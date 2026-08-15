// /compare page — v1.4 P2-1
const $ = (id) => document.getElementById(id);

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function readForm() {
  const pool = $('pool-input').value.split(',').map(s => s.trim()).filter(Boolean);
  const weights = {
    value: parseFloat($('w-value').value) || 0,
    momentum: parseFloat($('w-momentum').value) || 0,
    quality: parseFloat($('w-quality').value) || 0,
  };
  const wsum = (weights.value + weights.momentum + weights.quality).toFixed(2);
  $('weight-sum').textContent = '總和: ' + wsum;
  return {
    pool, weights,
    start: $('start-input').value || '2023-01-01',
    end:   $('end-input').value || new Date().toISOString().slice(0, 10),
    top_n: parseInt($('topn-input').value, 10) || 5,
  };
}

const updateWeightSum = debounce(() => readForm(), 200);
['w-value', 'w-momentum', 'w-quality'].forEach(id => $(id).addEventListener('input', updateWeightSum));

async function runCompare() {
  const body = readForm();
  $('run-btn').disabled = true;
  $('run-btn').textContent = '執行中...';
  try {
    const res = await fetch('/api/quant_compare', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!data.ok) {
      alert('對比失敗：' + (data.error || '未知錯誤'));
      return;
    }
    renderTable(data.results);
    renderChart(data.results);
  } catch (err) {
    alert('網路錯誤：' + err.message);
  } finally {
    $('run-btn').disabled = false;
    $('run-btn').textContent = '執行對比';
  }
}

function renderTable(results) {
  const tbody = document.querySelector('#kpi-table tbody');
  tbody.innerHTML = '';
  for (const r of results) {
    if (r.error) {
      tbody.insertAdjacentHTML('beforeend',
        `<tr><td>${r.name}</td><td colspan="4" style="color:red">${r.error}</td></tr>`);
      continue;
    }
    const k = r.kpis || {};
    tbody.insertAdjacentHTML('beforeend',
      `<tr>
        <td>${r.name}</td>
        <td>${(k.cum_return * 100 || 0).toFixed(2)}%</td>
        <td>${(k.sharpe || 0).toFixed(2)}</td>
        <td>${(k.mdd * 100 || 0).toFixed(2)}%</td>
        <td>${k.rebalance_count || 0}</td>
      </tr>`);
  }
}

function renderChart(results) {
  const el = $('nav-chart');
  el.innerHTML = '<pre>' + JSON.stringify(
    results.map(r => ({ name: r.name, n_points: (r.nav_curve || []).length })),
    null, 2) + '</pre>';
}

$('run-btn').addEventListener('click', runCompare);
