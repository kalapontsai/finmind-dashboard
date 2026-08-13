<?php
/**
 * GET /finmind/api/stock_revenue.php?stock_id=2330&start_date=...
 * 月營收
 */
require_once __DIR__ . '/../lib/finmind.php';

try {
    $stockId = trim((string)($_GET['stock_id'] ?? ''));
    $startDate = trim((string)($_GET['start_date'] ?? date('Y-m-d', strtotime('-2 year'))));
    $endDate   = trim((string)($_GET['end_date'] ?? date('Y-m-d')));

    if ($stockId === '') json_error('stock_id required');

    $client = new FinMindClient();
    $rows = $client->query('TaiwanStockMonthRevenue', [
        'data_id'    => $stockId,
        'start_date' => $startDate,
        'end_date'   => $endDate,
    ]);

    // 加 YoY 計算
    $byMonth = [];
    foreach ($rows as $r) {
        $key = substr($r['date'], 0, 7);   // YYYY-MM
        $byMonth[$key] = $r;
    }
    ksort($byMonth);
    $monthKeys = array_keys($byMonth);
    $enriched = [];
    foreach ($monthKeys as $i => $key) {
        $cur = $byMonth[$key];
        $yoy = null;
        if ($i >= 12) {
            $prevKey = $monthKeys[$i - 12];
            $prev = $byMonth[$prevKey];
            if ($prev['revenue'] > 0) {
                $yoy = round(($cur['revenue'] - $prev['revenue']) / $prev['revenue'] * 100, 2);
            }
        }
        $enriched[] = [
            'date'             => $cur['date'],
            'revenue'          => $cur['revenue'],
            'revenue_year'     => $cur['revenue_year'] ?? null,
            'revenue_month'    => $cur['revenue_month'] ?? null,
            'YoY'              => $yoy,
        ];
    }

    json_response([
        'stock_id' => $stockId,
        'count'    => count($enriched),
        'rows'     => $enriched,
    ]);
} catch (Throwable $e) {
    json_error($e->getMessage(), 502);
}
