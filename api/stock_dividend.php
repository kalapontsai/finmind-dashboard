<?php
/**
 * GET /finmind/api/stock_dividend.php?stock_id=2330&start_date=...
 * 配息（TaiwanStockDividend - 單一 dataset，含現金 + 股票股利欄位）
 */
require_once __DIR__ . '/../lib/finmind.php';

try {
    $stockId = trim((string)($_GET['stock_id'] ?? ''));
    $startDate = trim((string)($_GET['start_date'] ?? date('Y-m-d', strtotime('-5 year'))));
    $endDate   = trim((string)($_GET['end_date'] ?? date('Y-m-d')));

    if ($stockId === '') json_error('stock_id required');

    $client = new FinMindClient();
    $rows = $client->query('TaiwanStockDividend', [
        'data_id'    => $stockId,
        'start_date' => $startDate,
        'end_date'   => $endDate,
    ]);

    // 整理：依年份彙總（除息日年份）
    $byYear = [];
    foreach ($rows as $r) {
        $d = $r['date'] ?? '';
        $year = substr($d, 0, 4);
        if ($year === '' || $year === '0000') continue;
        if (!isset($byYear[$year])) {
            $byYear[$year] = [
                'year'             => $year,
                'cash_dividend'    => 0,
                'stock_dividend'   => 0,
                'events'           => [],
            ];
        }
        $cash = (float)($r['CashEarningsDistribution'] ?? 0) + (float)($r['CashStatutorySurplus'] ?? 0);
        $stock = (float)($r['StockEarningsDistribution'] ?? 0) + (float)($r['StockStatutorySurplus'] ?? 0);
        $byYear[$year]['cash_dividend']  += $cash;
        $byYear[$year]['stock_dividend'] += $stock;
        $byYear[$year]['events'][] = [
            'date'       => $d,
            'cash'       => $cash,
            'stock'      => $stock,
            'announce'   => $r['AnnouncementDate'] ?? '',
        ];
    }
    $years = array_values($byYear);
    usort($years, fn($a, $b) => (int)$b['year'] - (int)$a['year']);

    json_response([
        'stock_id' => $stockId,
        'count'    => count($years),
        'rows'     => $years,
    ]);
} catch (Throwable $e) {
    json_error($e->getMessage(), 502);
}
