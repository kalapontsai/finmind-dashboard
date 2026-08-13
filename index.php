<?php
/**
 * FinMind Dashboard - 主入口
 * - Sidebar（個股分析 / 回測）+ Content area
 * - Hash-based 路由，由前端 JS 處理頁面切換
 */
?>
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FinMind Dashboard</title>
    <link rel="stylesheet" href="/finmind/assets/css/style.css">
</head>
<body>
    <div class="app">

        <aside class="sidebar">
            <div class="sidebar-header">
                <div class="sidebar-title">FinMind</div>
                <div class="sidebar-subtitle">台股分析 + 策略回測</div>
            </div>

            <div class="nav-section">
                <div class="nav-label">分析</div>
                <a class="nav-link" data-nav="analysis" href="#/taiwan-stock-analysis">
                    <span class="nav-icon">📊</span>
                    <span>個股分析</span>
                </a>
            </div>

            <div class="nav-section">
                <div class="nav-label">策略</div>
                <a class="nav-link" data-nav="backtest" href="#/back-testing">
                    <span class="nav-icon">⚡</span>
                    <span>回測</span>
                </a>
            </div>

            <div class="nav-section">
                <div class="nav-label">量化</div>
                <a class="nav-link" data-nav="quant" href="#/quant-backtest">
                    <span class="nav-icon">📈</span>
                    <span>多因子回測</span>
                </a>
            </div>

            <div class="sidebar-footer">
                <div>資料來源：<a href="https://finmindtrade.com/" target="_blank" rel="noopener">FinMind</a></div>
                <div style="margin-top:6px;">v1.0</div>
            </div>
        </aside>

        <main class="main">
            <button class="menu-toggle" id="menuToggle">☰</button>

            <div class="page-header">
                <h1 class="page-title" id="pageTitle">個股分析</h1>
                <div class="page-desc" id="pageDesc"></div>
            </div>

            <div id="pageContent"></div>
        </main>

    </div>

    <script src="/finmind/assets/lib/chart.umd.js"></script>
    <script src="/finmind/assets/js/api.js"></script>
    <script src="/finmind/assets/js/indicators.js"></script>
    <script src="/finmind/assets/js/analysis.js"></script>
    <script src="/finmind/assets/js/backtest.js"></script>
    <script src="/finmind/assets/js/quant.js"></script>
    <script src="/finmind/assets/js/app.js"></script>
</body>
</html>
