<?php
/**
 * GET /finmind/api/stock_price.php?stock_id=2330&start_date=2025-08-01&end_date=2026-08-13
 * 歷史股價
 */
require_once __DIR__ . '/../lib/finmind.php';

try {
    $stockId  = trim((string)($_GET['stock_id'] ?? ''));
    $startDate = trim((string)($_GET['start_date'] ?? ''));
    $endDate   = trim((string)($_GET['end_date'] ?? ''));

    if ($stockId === '')  json_error('stock_id required');
    if ($startDate === '') json_error('start_date required');
    if ($endDate === '')   json_error('end_date required');

    $client = new FinMindClient();
    $rows = $client->query('TaiwanStockPrice', [
        'data_id'    => $stockId,
        'start_date' => $startDate,
        'end_date'   => $endDate,
    ]);

    json_response([
        'stock_id'  => $stockId,
        'count'     => count($rows),
        'prices'    => $rows,
    ]);
} catch (Throwable $e) {
    json_error($e->getMessage(), 502);
}
