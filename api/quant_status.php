<?php
/**
 * GET /finmind/api/quant_status.php
 * 查詢多因子回測狀態：報告檔案資訊、容器 Python 可用性
 */
require_once __DIR__ . '/../config.php';

date_default_timezone_set('Asia/Taipei');

$reportPath = __DIR__ . '/../quant/output/report.html';
$resultsPath = __DIR__ . '/../quant/output/backtest_results.json';

$lastUpdate = null;
$fileSize = 0;
if (is_file($reportPath)) {
    $mtime = filemtime($reportPath);
    $lastUpdate = date('Y-m-d H:i:s', $mtime);
    $fileSize = filesize($reportPath);
}

$pythonAvail = !empty(trim(shell_exec('which python3 2>/dev/null')));
$hasPandas = false;
if ($pythonAvail) {
    $check = shell_exec('python3 -c "import pandas" 2>&1');
    $hasPandas = (strpos($check, 'ModuleNotFoundError') === false);
}

$kpis = null;
if (is_file($resultsPath)) {
    $data = json_decode(file_get_contents($resultsPath), true);
    if (is_array($data) && isset($data['kpis'])) {
        $kpis = $data['kpis'];
    }
}

json_response([
    'ok'                => true,
    'last_update'       => $lastUpdate,
    'file_size'         => $fileSize,
    'python_available'  => $pythonAvail && $hasPandas,
    'python_in_path'    => $pythonAvail,
    'has_pandas'        => $hasPandas,
    'kpis'              => $kpis,
]);
