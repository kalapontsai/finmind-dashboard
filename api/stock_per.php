<?php
/**
 * GET /finmind/api/stock_per.php?stock_id=2330&start_date=...
 * 本益比 / 淨值比 / 殖利率
 */
require_once __DIR__ . '/../lib/finmind.php';

try {
    $stockId = trim((string)($_GET['stock_id'] ?? ''));
    $startDate = trim((string)($_GET['start_date'] ?? date('Y-m-d', strtotime('-1 year'))));
    $endDate   = trim((string)($_GET['end_date'] ?? date('Y-m-d')));

    if ($stockId === '') json_error('stock_id required');

    $client = new FinMindClient();
    $rows = $client->query('TaiwanStockPER', [
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
