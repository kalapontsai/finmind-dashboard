<?php
/**
 * FinMind 設定檔
 * - 兩段式讀 token：
 *   1) container 內的 data/finmind_token.txt  （PHP 在 docker 跑時用）
 *   2) host 的 .env（FINMIND_TOKEN=...）        （PHP 在 WSL 直跑時用，設定環境變數 FINMIND_ENV_FILE）
 * - 兩個檔案都受 .htaccess 403 保護，無法由 web 直接讀取
 */

$FINMIND_TOKEN = '';

// 第二段 fallback 路徑改由環境變數指定，避免把個人本機路徑寫死進版本庫。
// 設定方式：export FINMIND_ENV_FILE=/path/to/your/.env
$hostEnv = getenv('FINMIND_ENV_FILE');

$candidates = [
    __DIR__ . '/data/finmind_token.txt',                                          // 容器內 fallback
    $hostEnv !== false && $hostEnv !== '' ? $hostEnv : null,                      // WSL/host .env
];

foreach ($candidates as $f) {
    if (!is_readable($f)) continue;
    $content = file_get_contents($f);

    if (str_ends_with($f, '.env')) {
        // parse KEY=VALUE
        foreach (explode("\n", $content) as $line) {
            $line = trim($line);
            if ($line === '' || str_starts_with($line, '#') || !str_contains($line, '=')) continue;
            [$k, $v] = explode('=', $line, 2);
            if (trim($k) === 'FINMIND_TOKEN') {
                $FINMIND_TOKEN = trim($v);
                break;
            }
        }
    } else {
        // 純 token 檔（單行）
        $FINMIND_TOKEN = trim($content);
    }

    if ($FINMIND_TOKEN !== '') break;
}

if ($FINMIND_TOKEN === '') {
    http_response_code(500);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['error' => 'FINMIND_TOKEN not found. Place it in finmind/data/finmind_token.txt or set FINMIND_TOKEN in .env']);
    exit;
}

define('FINMIND_API_BASE', 'https://api.finmindtrade.com/api/v4/data');
define('FINMIND_RATE_LIMIT_MS', 200);
define('STOCK_LIST_CACHE_TTL', 86400);
define('BACKTEST_RESULTS_FILE', __DIR__ . '/data/backtest_results.json');
define('STOCK_LIST_CACHE_FILE', __DIR__ . '/data/stock_list.json');

ini_set('display_errors', '0');
error_reporting(E_ALL);

function json_response($data, int $code = 200): void {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}

function json_error(string $msg, int $code = 400, array $extra = []): void {
    json_response(array_merge(['error' => $msg], $extra), $code);
}
