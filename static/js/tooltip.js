/**
 * 指標教學 Tooltip
 * - 在 card-title 旁插入 ⓘ 圖示
 * - hover / focus 顯示說明文字
 * - 純 CSS 動畫，不需額外套件
 *
 * 使用：
 *   IndicatorTip.attach(cardTitleSelector, '說明文字')
 *   或在 card-title 內放 data-tooltip="說明文字"，呼叫 IndicatorTip.bindAll()
 */

const IndicatorTip = {
    /**
     * 說明文字字典（key = card-title 文字前綴）
     */
    HINTS: {
        '股價走勢':           '收盤價走勢圖，搭配 5/20/60 日移動平均線（MA）。MA 可視為「一段時間的平均成本」，價格在 MA 上方偏多、下方偏空。',
        '移動平均線':           '簡單移動平均線（SMA）：前 N 日收盤價的平均。常用 5（短）、20（中）、60（長）日。',
        '成交量':              '每日成交量（股數），漲日綠柱 / 跌日紅柱。量是價的燃料：價漲量增 → 健康；價漲量縮 → 警訊。',
        'RSI':                 '相對強弱指標（Relative Strength Index）。0-100，>70 超買、<30 超賣。短線反轉參考，但強勢股可維持超買區很久。',
        'KD':                  '隨機指標（Stochastic）。K 值（快線）>D 值（慢線）偏多；K<20 黃金交叉常見反彈訊號。',
        'MACD':                '指數平滑異同移動平均線。柱狀圖翻正 = 短期動能轉強；MACD 線由下穿上 Signal 線 = 黃金交叉，偏多。',
        '基本面':              '本益比（PER）= 股價 / 每股盈餘，越低越便宜；淨值比（PBR）= 股價 / 每股淨值；殖利率 = 現金股利 / 股價。',
        '本益比':              'PER（Price-to-Earnings Ratio）。< 15 通常被視為合理，< 10 便宜但可能是陷阱；需搭配產業與成長性看。',
        '月營收':              '公司每月公告的營收。YoY = 與去年同期比，>0 成長、<0 衰退。連 2-3 個月 YoY > 20% 是強勢股訊號。',
        '三大法人':            '外資 + 投信 + 自營商的買賣超（張數）。三大法人合計買超 → 主力進場跡象。',
        '融資融券':            '融資 = 借錢買股票（槓桿多單）；融券 = 借股票賣（放空）。券資比↑ = 軋空潛力大。',
        '配息':                '公司過去發放的現金股利紀錄。穩定配息 → 防禦型 / 高殖利率股；高股息不必然是好事（要看 EPS 撐不撐得住）。',
    },

    /**
     * 插入 ⓘ 到 card-title 元素
     */
    attach(titleEl, hint) {
        if (!titleEl || titleEl.querySelector('.tip-trigger')) return;
        const trigger = document.createElement('span');
        trigger.className = 'tip-trigger';
        trigger.tabIndex = 0;
        trigger.textContent = 'ⓘ';
        trigger.setAttribute('aria-label', '說明');

        const bubble = document.createElement('span');
        bubble.className = 'tip-bubble';
        bubble.textContent = hint;

        trigger.appendChild(bubble);
        titleEl.appendChild(trigger);
    },

    /**
     * 自動偵測 card-title 文字並綁定對應說明
     * 規則：標題開頭部分字串 in HINTS
     */
    bindAll(root = document) {
        root.querySelectorAll('.card-title').forEach(el => {
            const text = el.textContent.trim();
            for (const [key, hint] of Object.entries(this.HINTS)) {
                if (text.includes(key)) {
                    this.attach(el, hint);
                    break;
                }
            }
        });
    },
};