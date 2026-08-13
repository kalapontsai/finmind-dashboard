<?php
/**
 * POST /finmind/api/quant_run.php
 * 執行多因子回測（會呼叫 Python 腳本）
 *
 * 設計：
 * - 優先用容器內的 Python3（如果有 pandas/FinMind）
 * - 沒有則回錯誤，提示在 WSL 手動跑
 */
require_once __DIR__ . '/../config.php';

$quantDir = realpath(__DIR__ . '/../quant');
$mainScript = $quantDir . '/main.py';

if (!is_dir($quantDir)) {
    json_error('找不到 quant 程式碼目錄', 404, ['hint' => '確認 /finmind/quant/ 存在']);
}
if (!is_file($mainScript)) {
    json_error('找不到 main.py', 404, ['hint' => '確認 Python 程式碼已部署']);
}

// 檢查 Python 環境
$python = trim(shell_exec('which python3 2>/dev/null'));
if (!$python) {
    json_error('容器沒有 python3', 500, [
        'python_available' => false,
        'hint' => 'WSL 終端機跑：cd /mnt/d/docker-volumn/ubuntu-apache2/html/finmind/quant && python3 main.py',
    ]);
}

// 檢查 Python 套件
$hasPkg = shell_exec('python3 -c "import pandas, FinMind, plotly" 2>&1');
if (strpos($hasPkg, 'ModuleNotFoundError') !== false || strpos($hasPkg, 'ImportError') !== false) {
    json_error('容器 Python 缺套件（pandas/FinMind/plotly）', 500, [
        'python_available' => true,
        'has_packages' => false,
        'hint' => '需先在容器安裝：pip install pandas FinMind plotly numpy\n或直接在 WSL 跑：cd /mnt/d/docker-volumn/ubuntu-apache2/html/finmind/quant && python3 main.py',
    ]);
}

// 執行回測（背景跑，timeout 600 秒）
$startTime = microtime(true);
$output = shell_exec("cd {$quantDir} && timeout 600 python3 main.py 2>&1");
$elapsed = round(microtime(true) - $startTime, 1);

// 檢查是否成功產出 report.html
$reportPath = $quantDir . '/output/report.html';
if (!is_file($reportPath) || (time() - filemtime($reportPath)) > 60) {
    json_error('回測執行失敗或沒產出報告', 500, [
        'output' => $output,
        'elapsed_sec' => $elapsed,
    ]);
}

// 解析 KPI
$kpis = null;
$resultsPath = $quantDir . '/output/backtest_results.json';
if (is_file($resultsPath)) {
    $data = json_decode(file_get_contents($resultsPath), true);
    if (is_array($data) && isset($data['kpis'])) {
        $k = $data['kpis'];
        $kpis = [
            'total_return'     => round($k['total_return'] * 100, 2) . '%',
            'benchmark_return' => round($k['benchmark_return'] * 100, 2) . '%',
            'excess_return'    => round($k['excess_return'] * 100, 2) . '%',
            'mdd'              => round($k['mdd'] * 100, 2) . '%',
            'sharpe'           => round($k['sharpe'], 2),
            'rebalance_count'  => $k['rebalance_count'] ?? null,
        ];
    }
}

json_response([
    'ok'             => true,
    'elapsed_sec'    => $elapsed,
    'kpis'           => $kpis,
    'last_log'       => mb_substr($output, -2000),  // 最後 2000 字
]);
