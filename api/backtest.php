<?php
/**
 * POST /finmind/api/backtest.php
 * body: {
 *   stock_id, start_date, end_date,
 *   capital,
 *   strategies: { ma: {enabled, short, long}, rsi: {enabled, period, low, high},
 *                 kd: {enabled, period, k_smooth, d_smooth, low, high},
 *                 macd: {enabled, fast, slow, signal} },
 *   combine_mode: 'AND' | 'OR'
 * }
 *
 * 計算策略回測：依策略觸發買賣，全部現金買入/全部庫存賣出
 */
require_once __DIR__ . '/../lib/finmind.php';

function bt_ma(array $closes, int $short, int $long): array {
    $n = count($closes);
    $maS = array_fill(0, $n, null);
    $maL = array_fill(0, $n, null);
    $sumS = 0; $sumL = 0;
    for ($i = 0; $i < $n; $i++) {
        $sumS += $closes[$i]; if ($i >= $short) $sumS -= $closes[$i - $short];
        $sumL += $closes[$i]; if ($i >= $long)  $sumL -= $closes[$i - $long];
        if ($i >= $short - 1) $maS[$i] = $sumS / $short;
        if ($i >= $long  - 1) $maL[$i] = $sumL / $long;
    }
    return [$maS, $maL];
}

function bt_rsi(array $closes, int $period): array {
    $n = count($closes);
    $rsi = array_fill(0, $n, null);
    if ($n < $period + 1) return [$rsi];
    $gains = 0; $losses = 0;
    for ($i = 1; $i <= $period; $i++) {
        $diff = $closes[$i] - $closes[$i-1];
        if ($diff >= 0) $gains += $diff; else $losses -= $diff;
    }
    $avgG = $gains / $period; $avgL = $losses / $period;
    $rs = $avgL > 0 ? $avgG / $avgL : 100;
    $rsi[$period] = $avgL > 0 ? 100 - 100 / (1 + $rs) : 100;
    for ($i = $period + 1; $i < $n; $i++) {
        $diff = $closes[$i] - $closes[$i-1];
        $g = $diff > 0 ? $diff : 0;
        $l = $diff < 0 ? -$diff : 0;
        $avgG = ($avgG * ($period - 1) + $g) / $period;
        $avgL = ($avgL * ($period - 1) + $l) / $period;
        $rs = $avgL > 0 ? $avgG / $avgL : 100;
        $rsi[$i] = $avgL > 0 ? 100 - 100 / (1 + $rs) : 100;
    }
    return [$rsi];
}

function bt_kd(array $highs, array $lows, array $closes, int $n, int $kSm, int $dSm): array {
    $len = count($closes);
    $k = array_fill(0, $len, null);
    $d = array_fill(0, $len, null);
    $prevK = 50; $prevD = 50;
    for ($i = 0; $i < $len; $i++) {
        if ($i < $n - 1) continue;
        $h = max(array_slice($highs, $i - $n + 1, $n));
        $l = min(array_slice($lows,  $i - $n + 1, $n));
        $rsv = ($h == $l) ? 50 : round(($closes[$i] - $l) / ($h - $l) * 100, 2);
        $k[$i] = round($prevK * ($kSm - 1) / $kSm + $rsv / $kSm, 2);
        $d[$i] = round($prevD * ($dSm - 1) / $dSm + $k[$i] / $dSm, 2);
        $prevK = $k[$i]; $prevD = $d[$i];
    }
    return [$k, $d];
}

function bt_macd(array $closes, int $fast, int $slow, int $signal): array {
    $len = count($closes);
    // EMA 序列
    $emaF = []; $emaS = [];
    $kF = 2 / ($fast + 1); $kS = 2 / ($slow + 1);
    $prevF = $closes[0]; $prevS = $closes[0];
    for ($i = 0; $i < $len; $i++) {
        $prevF = $i === 0 ? $closes[$i] : $closes[$i] * $kF + $prevF * (1 - $kF);
        $prevS = $i === 0 ? $closes[$i] : $closes[$i] * $kS + $prevS * (1 - $kS);
        $emaF[$i] = $prevF; $emaS[$i] = $prevS;
    }
    $dif = array_map(fn($a, $b) => $a - $b, $emaF, $emaS);
    $macd = []; $prevM = $dif[0]; $kM = 2 / ($signal + 1);
    for ($i = 0; $i < $len; $i++) {
        $prevM = $i === 0 ? $dif[$i] : $dif[$i] * $kM + $prevM * (1 - $kM);
        $macd[$i] = $prevM;
    }
    $osc = array_map(fn($a, $b) => $a - $b, $dif, $macd);
    return [$dif, $macd, $osc];
}

try {
    $body = json_decode(file_get_contents('php://input'), true) ?: [];
    $stockId = trim((string)($body['stock_id'] ?? ''));
    $start   = trim((string)($body['start_date'] ?? ''));
    $end     = trim((string)($body['end_date']   ?? ''));
    $capital = (float)($body['capital'] ?? 1000000);
    $strats  = $body['strategies'] ?? [];
    $combine = strtoupper((string)($body['combine_mode'] ?? 'OR'));
    $combine = ($combine === 'AND') ? 'AND' : 'OR';

    if ($stockId === '' || $start === '' || $end === '') {
        json_error('stock_id / start_date / end_date required');
    }

    // 取股價
    $client = new FinMindClient();
    $rows = $client->query('TaiwanStockPrice', [
        'data_id'    => $stockId,
        'start_date' => $start,
        'end_date'   => $end,
    ]);
    if (count($rows) === 0) json_error('No price data', 404);

    $dates  = array_column($rows, 'date');
    $opens  = array_map('floatval', array_column($rows, 'open'));
    $highs  = array_map('floatval', array_column($rows, 'max'));
    $lows   = array_map('floatval', array_column($rows, 'min'));
    $closes = array_map('floatval', array_column($rows, 'close'));

    $n = count($rows);

    // 交易頻率：建動作日索引（只有動作日才評估買賣訊號）
    $frequency = strtolower(trim((string)($body['frequency'] ?? 'day')));
    $monthDay  = max(1, min(31, (int)($body['month_day'] ?? 15)));
    $actionDayIdx = [];
    $actionDates  = [];   // 實際動作日期（debug 顯示用）
    if ($frequency === 'month') {
        $processedMonths = [];
        for ($i = 0; $i < $n; $i++) {
            $ym = substr($dates[$i], 0, 7);   // YYYY-MM
            if (isset($processedMonths[$ym])) continue;
            $processedMonths[$ym] = true;
            // 找本月內第一個交易日 ≥ monthDay
            for ($j = $i; $j < $n; $j++) {
                if (substr($dates[$j], 0, 7) !== $ym) break;
                $day = (int)substr($dates[$j], 8, 2);
                if ($day >= $monthDay) {
                    $actionDayIdx[] = $j;
                    $actionDates[]  = $dates[$j];
                    break;
                }
            }
        }
    } else {
        // 每日（預設）
        $frequency = 'day';
        for ($i = 0; $i < $n; $i++) {
            $actionDayIdx[] = $i;
            $actionDates[]  = $dates[$i];
        }
    }
    $actionSet = array_flip($actionDayIdx);

    // 計算指標
    $indMa   = $strats['ma']['enabled']   ? bt_ma($closes, (int)$strats['ma']['short'], (int)$strats['ma']['long'])     : null;
    $indRsi  = $strats['rsi']['enabled']  ? bt_rsi($closes, (int)$strats['rsi']['period'])                              : null;
    $indKd   = $strats['kd']['enabled']   ? bt_kd($highs, $lows, $closes, (int)$strats['kd']['period'],
                                                  (int)$strats['kd']['k_smooth'], (int)$strats['kd']['d_smooth'])        : null;
    $indMacd = $strats['macd']['enabled'] ? bt_macd($closes, (int)$strats['macd']['fast'], (int)$strats['macd']['slow'],
                                                    (int)$strats['macd']['signal'])                                       : null;

    // 每日評估訊號
    $signals = array_fill(0, $n, ['buy' => [], 'sell' => []]);
    for ($i = 1; $i < $n; $i++) {   // 從 i=1 開始（需要前一天比較）

        // MA 黃金交叉 / 死亡交叉
        if ($indMa !== null) {
            [$maS, $maL] = $indMa;
            if ($maS[$i-1] !== null && $maL[$i-1] !== null && $maS[$i] !== null && $maL[$i] !== null) {
                if ($maS[$i-1] <= $maL[$i-1] && $maS[$i] > $maL[$i]) $signals[$i]['buy'][] = 'MA_GOLDEN';
                if ($maS[$i-1] >= $maL[$i-1] && $maS[$i] < $maL[$i]) $signals[$i]['sell'][] = 'MA_DEATH';
            }
        }

        // RSI 超賣 / 超買
        if ($indRsi !== null) {
            [$rsi] = $indRsi;
            if ($rsi[$i] !== null) {
                if ($rsi[$i] < (float)$strats['rsi']['low'])  $signals[$i]['buy'][]  = 'RSI_OVERSOLD';
                if ($rsi[$i] > (float)$strats['rsi']['high']) $signals[$i]['sell'][] = 'RSI_OVERBOUGHT';
            }
        }

        // KD
        if ($indKd !== null) {
            [$k, $d] = $indKd;
            if ($k[$i] !== null && $d[$i] !== null) {
                if ($k[$i] < (float)$strats['kd']['low']  && $k[$i] > $d[$i]) $signals[$i]['buy'][]  = 'KD_OVERSOLD';
                if ($k[$i] > (float)$strats['kd']['high'] && $k[$i] < $d[$i]) $signals[$i]['sell'][] = 'KD_OVERBOUGHT';
            }
        }

        // MACD 柱狀由負轉正 / 由正轉負
        if ($indMacd !== null) {
            [$dif, $macd, $osc] = $indMacd;
            if ($osc[$i-1] !== null && $osc[$i] !== null) {
                if ($osc[$i-1] <= 0 && $osc[$i] > 0) $signals[$i]['buy'][]  = 'MACD_BUY';
                if ($osc[$i-1] >= 0 && $osc[$i] < 0) $signals[$i]['sell'][] = 'MACD_SELL';
            }
        }
    }

    // 套用 combine_mode
    $finalBuy  = array_fill(0, $n, false);
    $finalSell = array_fill(0, $n, false);
    for ($i = 0; $i < $n; $i++) {
        $b = count($signals[$i]['buy'])  > 0;
        $s = count($signals[$i]['sell']) > 0;
        if ($combine === 'AND') {
            // AND 模式：需要所有啟用的策略都觸發；當沒啟用任何策略時不動作
            $enabledCount = (int)!empty($strats['ma']['enabled'])
                          + (int)!empty($strats['rsi']['enabled'])
                          + (int)!empty($strats['kd']['enabled'])
                          + (int)!empty($strats['macd']['enabled']);
            $finalBuy[$i]  = $enabledCount > 0 && $b && ($signals[$i]['buy']  >= $enabledCount) === false
                            ? $signals[$i]['buy'] && (count($signals[$i]['buy']) === $enabledCount)
                            : ($b && false);  // 永遠 false（AND 模式需 >= enabledCount）
            $finalSell[$i] = false;  // 簡化：AND 模式下賣出用對稱邏輯
        } else {
            // OR 模式：任一觸發即動作
            $finalBuy[$i]  = $b;
            $finalSell[$i] = $s;
        }
    }

    // 重新跑 AND 邏輯（清晰寫法）
    if ($combine === 'AND') {
        $enabledCount = (int)!empty($strats['ma']['enabled'])
                      + (int)!empty($strats['rsi']['enabled'])
                      + (int)!empty($strats['kd']['enabled'])
                      + (int)!empty($strats['macd']['enabled']);
        for ($i = 0; $i < $n; $i++) {
            $b = count($signals[$i]['buy'])  === $enabledCount;
            $s = count($signals[$i]['sell']) === $enabledCount;
            $finalBuy[$i]  = $enabledCount > 0 && $b;
            $finalSell[$i] = $enabledCount > 0 && $s;
        }
    }

    // 逐日交易
    $cash = $capital; $shares = 0;
    $nav = array_fill(0, $n, 0.0);          // 策略淨值
    $buyHoldNav = array_fill(0, $n, 0.0);  // 買進持有對照
    $trades = [];

    $initBuyHoldShares = floor($capital / $closes[0]);

    for ($i = 0; $i < $n; $i++) {
        $price = $closes[$i];
        $isActionDay = isset($actionSet[$i]);

        if ($isActionDay && $finalBuy[$i] && $shares === 0 && $cash > 0) {
            $qty = (int)floor($cash / $price);
            if ($qty > 0) {
                $cost = $qty * $price;
                $cash -= $cost;
                $shares += $qty;
                $trades[] = ['date' => $dates[$i], 'action' => 'BUY',  'price' => $price, 'qty' => $qty, 'amount' => $cost];
            }
        } elseif ($isActionDay && $finalSell[$i] && $shares > 0) {
            $proceeds = $shares * $price;
            $cash += $proceeds;
            $trades[] = ['date' => $dates[$i], 'action' => 'SELL', 'price' => $price, 'qty' => $shares, 'amount' => $proceeds];
            $shares = 0;
        }

        $nav[$i] = $cash + $shares * $price;
        $buyHoldNav[$i] = $initBuyHoldShares * $price + ($capital - $initBuyHoldShares * $closes[0]);
    }

    // KPI
    $finalNav = $nav[$n-1];
    $totalRet = ($finalNav - $capital) / $capital;
    $days = max(1, (strtotime($dates[$n-1]) - strtotime($dates[0])) / 86400);
    $annRet = $days > 0 ? pow($finalNav / $capital, 365 / $days) - 1 : 0;

    // MDD
    $peak = $nav[0]; $mdd = 0;
    for ($i = 0; $i < $n; $i++) {
        if ($nav[$i] > $peak) $peak = $nav[$i];
        $dd = ($peak - $nav[$i]) / $peak;
        if ($dd > $mdd) $mdd = $dd;
    }

    // 勝率
    $wins = 0; $losses = 0;
    $buys = array_values(array_filter($trades, fn($t) => $t['action'] === 'BUY'));
    $sells = array_values(array_filter($trades, fn($t) => $t['action'] === 'SELL'));
    for ($i = 0; $i < min(count($buys), count($sells)); $i++) {
        if ($sells[$i]['price'] > $buys[$i]['price']) $wins++; else $losses++;
    }
    $winRate = ($wins + $losses) > 0 ? $wins / ($wins + $losses) : 0;

    $bhFinal = $buyHoldNav[$n-1];
    $bhRet = ($bhFinal - $capital) / $capital;

    $result = [
        'stock_id'     => $stockId,
        'start_date'   => $dates[0],
        'end_date'     => $dates[$n-1],
        'trading_days' => $n,
        'action_days'  => count($actionDayIdx),
        'frequency'    => $frequency,
        'month_day'    => $frequency === 'month' ? $monthDay : null,
        'capital'      => $capital,
        'final_nav'    => round($finalNav, 0),
        'total_return' => round($totalRet * 100, 2),     // %
        'annual_return'=> round($annRet * 100, 2),
        'max_drawdown' => round($mdd * 100, 2),
        'win_rate'     => round($winRate * 100, 2),
        'trade_count'  => count($trades),
        'buy_hold_return' => round($bhRet * 100, 2),
        'equity_curve' => array_map(fn($v) => round($v, 0), $nav),
        'buy_hold_curve' => array_map(fn($v) => round($v, 0), $buyHoldNav),
        'dates'        => $dates,
        'prices'       => array_map(fn($v) => round($v, 2), $closes),
        'trades'       => $trades,
        'signals'      => array_map(fn($s) => ['buy' => $s['buy'], 'sell' => $s['sell']], $signals),
        'indicators'   => [
            'ma'    => $indMa   ? array_map(fn($a, $b) => ['short' => $a, 'long' => $b], $indMa[0],   $indMa[1])   : null,
            'rsi'   => $indRsi  ? $indRsi[0]  : null,
            'kd'    => $indKd   ? array_map(fn($a, $b) => ['k' => $a, 'd' => $b], $indKd[0],   $indKd[1])   : null,
            'macd'  => $indMacd ? array_map(fn($a, $b, $c) => ['dif' => round($a,3), 'macd' => round($b,3), 'osc' => round($c,3)], $indMacd[0], $indMacd[1], $indMacd[2]) : null,
        ],
        'settings'     => $strats,
        'combine_mode' => $combine,
        'created_at'   => date('c'),
    ];

    // 儲存到本地（append-only，上限 50 筆）
    if (is_dir(dirname(BACKTEST_RESULTS_FILE)) || mkdir(dirname(BACKTEST_RESULTS_FILE), 0777, true)) {
        $list = [];
        if (is_file(BACKTEST_RESULTS_FILE)) {
            $list = json_decode(file_get_contents(BACKTEST_RESULTS_FILE), true) ?: [];
        }
        array_unshift($list, [
            'id'             => uniqid('bt_', true),
            'stock_id'       => $stockId,
            'start_date'     => $dates[0],
            'end_date'       => $dates[$n-1],
            'total_return'   => $result['total_return'],
            'annual_return'  => $result['annual_return'],
            'max_drawdown'   => $result['max_drawdown'],
            'win_rate'       => $result['win_rate'],
            'trade_count'    => $result['trade_count'],
            'buy_hold_return'=> $result['buy_hold_return'],
            'combine_mode'   => $combine,
            'frequency'      => $frequency,
            'month_day'      => $frequency === 'month' ? $monthDay : null,
            'settings'       => $strats,
            'created_at'     => $result['created_at'],
        ]);
        if (count($list) > 50) $list = array_slice($list, 0, 50);
        file_put_contents(BACKTEST_RESULTS_FILE, json_encode($list, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));
    }

    json_response($result);
} catch (Throwable $e) {
    json_error($e->getMessage(), 502);
}
