<?php
/**
 * GET /finmind/api/stock_finance.php?stock_id=2330&start_date=...
 * 三大財報（綜合損益表 + 資產負債表 + 現金流量表）
 */
require_once __DIR__ . '/../lib/finmind.php';

try {
    $stockId = trim((string)($_GET['stock_id'] ?? ''));
    $startDate = trim((string)($_GET['start_date'] ?? date('Y-m-d', strtotime('-2 year'))));
    $endDate   = trim((string)($_GET['end_date'] ?? date('Y-m-d')));

    if ($stockId === '') json_error('stock_id required');

    $client = new FinMindClient();
    $rows = $client->query('TaiwanStockFinancialStatements', [
        'data_id'    => $stockId,
        'start_date' => $startDate,
        'end_date'   => $endDate,
    ]);

    json_response([
        'stock_id' => $stockId,
        'count'    => count($rows),
        'rows'     => $rows,
    ]);
} catch (Throwable $e) {
    json_error($e->getMessage(), 502);
}
