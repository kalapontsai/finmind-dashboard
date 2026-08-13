<?php
/**
 * GET /finmind/api/institutional.php?stock_id=2330&start_date=...
 * 三大法人買賣超
 */
require_once __DIR__ . '/../lib/finmind.php';

try {
    $stockId = trim((string)($_GET['stock_id'] ?? ''));
    $startDate = trim((string)($_GET['start_date'] ?? date('Y-m-d', strtotime('-3 month'))));
    $endDate   = trim((string)($_GET['end_date'] ?? date('Y-m-d')));

    if ($stockId === '') json_error('stock_id required');

    $client = new FinMindClient();
    $rows = $client->query('TaiwanStockInstitutionalInvestorsBuySell', [
        'data_id'    => $stockId,
        'start_date' => $startDate,
        'end_date'   => $endDate,
    ]);

    // 整理：依日期彙總 Foreign_Investor / Investment_Trust / Dealer
    $byDate = [];
    foreach ($rows as $r) {
        $d = $r['date'];
        if (!isset($byDate[$d])) {
            $byDate[$d] = [
                'date'          => $d,
                'foreign'       => 0,
                'trust'         => 0,
                'dealer'        => 0,
                'total'         => 0,
                'foreign_buy'   => 0,
                'foreign_sell'  => 0,
            ];
        }
        $name = $r['name'];
        $buy  = (int)$r['buy'];
        $sell = (int)$r['sell'];
        $net  = $buy - $sell;
        if ($name === 'Foreign_Investor') {
            $byDate[$d]['foreign']      += $net;
            $byDate[$d]['foreign_buy']  += $buy;
            $byDate[$d]['foreign_sell'] += $sell;
        } elseif ($name === 'Investment_Trust') {
            $byDate[$d]['trust'] += $net;
        } elseif ($name === 'Dealer') {
            $byDate[$d]['dealer'] += $net;
        }
        $byDate[$d]['total'] += $net;
    }
    $result = array_values($byDate);
    usort($result, fn($a, $b) => strcmp($a['date'], $b['date']));

    json_response([
        'stock_id' => $stockId,
        'count'    => count($result),
        'rows'     => $result,
    ]);
} catch (Throwable $e) {
    json_error($e->getMessage(), 502);
}
