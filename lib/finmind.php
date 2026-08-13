<?php
/**
 * FinMind API Client
 * 統一封裝 v4 API 呼叫 + 快取 + 錯誤處理
 */

require_once __DIR__ . '/../config.php';

class FinMindClient {
    private string $token;
    private int $rateLimitMs;
    private static int $lastCallMs = 0;

    public function __construct(?string $token = null, int $rateLimitMs = FINMIND_RATE_LIMIT_MS) {
        $this->token = $token ?? $GLOBALS['FINMIND_TOKEN'];
        $this->rateLimitMs = $rateLimitMs;
    }

    /**
     * 通用查詢（data endpoint）
     * @param array $params 額外參數（data_id, start_date, end_date 等）
     */
    public function query(string $dataset, array $params = []): array {
        // 過濾掉 null 或字串 "undefined"（前端 bug 會傳過來）
        $cleanParams = [];
        foreach ($params as $k => $v) {
            if ($v === null) continue;
            if (is_string($v) && in_array(strtolower($v), ['undefined', 'null'], true)) continue;
            if ($v === '') continue;
            $cleanParams[$k] = $v;
        }
        $url = FINMIND_API_BASE . '?' . http_build_query(array_merge([
            'dataset' => $dataset,
            'token'   => $this->token,
        ], $cleanParams));

        $resp = $this->fetchWithRateLimit($url);
        $json = json_decode($resp, true);
        if (!is_array($json)) {
            throw new RuntimeException("Invalid JSON from FinMind for {$dataset}");
        }
        if (($json['status'] ?? 0) !== 200) {
            throw new RuntimeException("FinMind error [{$dataset}]: " . ($json['msg'] ?? 'unknown'));
        }
        return $json['data'] ?? [];
    }

    /**
     * 個股清單（含快取）
     * @param bool $useCache 是否用本地快取（24h TTL）
     */
    public function getStockList(bool $useCache = true): array {
        $cacheFile = STOCK_LIST_CACHE_FILE;
        if ($useCache && is_file($cacheFile)) {
            $mtime = filemtime($cacheFile);
            if (time() - $mtime < STOCK_LIST_CACHE_TTL) {
                $cached = json_decode(file_get_contents($cacheFile), true);
                if (is_array($cached)) return $cached;
            }
        }

        $rows = $this->query('TaiwanStockInfo');

        // 過濾 + 整理：取最新一筆（每個 stock_id 的最新 date）
        $byStock = [];
        foreach ($rows as $r) {
            $sid = $r['stock_id'];
            if (!isset($byStock[$sid]) || $byStock[$sid]['date'] < $r['date']) {
                $byStock[$sid] = [
                    'stock_id'   => $sid,
                    'stock_name' => $r['stock_name'],
                    'industry'   => $r['industry_category'] ?? '',
                    'type'       => $r['type'] ?? '',
                ];
            }
        }
        $list = array_values($byStock);
        usort($list, fn($a, $b) => strcmp($a['stock_id'], $b['stock_id']));

        // 寫快取
        if (!is_dir(dirname($cacheFile))) mkdir(dirname($cacheFile), 0777, true);
        file_put_contents($cacheFile, json_encode($list, JSON_UNESCAPED_UNICODE));

        return $list;
    }

    /**
     * 個股搜尋（依代碼或名稱）
     */
    public function searchStock(string $q, int $limit = 30): array {
        $list = $this->getStockList();
        $q = trim($q);
        if ($q === '') return [];
        $qLower = mb_strtolower($q);
        $hits = [];
        foreach ($list as $s) {
            if (str_contains($s['stock_id'], $q) || mb_strtolower($s['stock_name']) === $qLower) {
                $hits[] = $s;   // 完全匹配優先
                if (count($hits) >= $limit) break;
            }
        }
        if (count($hits) < $limit) {
            foreach ($list as $s) {
                if (in_array($s, $hits, true)) continue;
                if (mb_strpos($s['stock_name'], $q) !== false || mb_strpos(mb_strtolower($s['stock_name']), $qLower) !== false) {
                    $hits[] = $s;
                    if (count($hits) >= $limit) break;
                }
            }
        }
        return $hits;
    }

    /**
     * 帶 rate-limit 的 HTTP GET
     */
    private function fetchWithRateLimit(string $url): string {
        $nowMs = (int)(microtime(true) * 1000);
        $gap = $nowMs - self::$lastCallMs;
        if ($gap < $this->rateLimitMs) {
            usleep(($this->rateLimitMs - $gap) * 1000);
        }
        self::$lastCallMs = (int)(microtime(true) * 1000);

        $ch = curl_init();
        curl_setopt_array($ch, [
            CURLOPT_URL            => $url,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 30,
            CURLOPT_CONNECTTIMEOUT => 10,
            CURLOPT_FOLLOWLOCATION => true,
            CURLOPT_USERAGENT      => 'finmind-dashboard/1.0',
        ]);
        $body = curl_exec($ch);
        $errno = curl_errno($ch);
        $err   = curl_error($ch);
        $code  = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($errno) throw new RuntimeException("curl error ({$errno}): {$err}");
        if ($code !== 200) throw new RuntimeException("HTTP {$code}: " . substr($body, 0, 200));
        return $body;
    }
}
