<?php
/**
 * GET /finmind/api/stock_list.php?q=台積電&limit=20
 * 個股清單 + 搜尋
 */
require_once __DIR__ . '/../lib/finmind.php';

try {
    $client = new FinMindClient();
    $q = isset($_GET['q']) ? trim((string)$_GET['q']) : '';
    $limit = isset($_GET['limit']) ? max(1, min(200, (int)$_GET['limit'])) : 50;

    if ($q !== '') {
        $results = $client->searchStock($q, $limit);
    } else {
        // 沒給 q：回前 N 檔（依 stock_id 排序，給前端預設清單）
        $all = $client->getStockList();
        $results = array_slice($all, 0, $limit);
    }

    json_response([
        'count'   => count($results),
        'stocks'  => $results,
    ]);
} catch (Throwable $e) {
    json_error($e->getMessage(), 502);
}
