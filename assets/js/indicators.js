/**
 * 技術指標計算（前端複用 / 預覽用）
 * 主要計算交給後端，這裡提供前端即時計算給 chart 用
 */

const Indicators = {
    /**
     * 簡單移動平均
     * @returns number[]，前 n-1 個為 null
     */
    sma(values, period) {
        const out = new Array(values.length).fill(null);
        let sum = 0;
        for (let i = 0; i < values.length; i++) {
            sum += values[i];
            if (i >= period) sum -= values[i - period];
            if (i >= period - 1) out[i] = sum / period;
        }
        return out;
    },

    /**
     * 指數移動平均
     */
    ema(values, period) {
        const out = new Array(values.length).fill(null);
        const k = 2 / (period + 1);
        let prev = null;
        for (let i = 0; i < values.length; i++) {
            if (i === 0) {
                out[i] = values[i];
                prev = values[i];
            } else {
                out[i] = values[i] * k + prev * (1 - k);
                prev = out[i];
            }
        }
        return out;
    },

    /**
     * RSI (Wilder smoothing)
     */
    rsi(closes, period = 14) {
        const n = closes.length;
        const out = new Array(n).fill(null);
        if (n < period + 1) return out;
        let g = 0, l = 0;
        for (let i = 1; i <= period; i++) {
            const d = closes[i] - closes[i - 1];
            if (d >= 0) g += d; else l -= d;
        }
        let avgG = g / period, avgL = l / period;
        out[period] = avgL > 0 ? 100 - 100 / (1 + avgG / avgL) : 100;
        for (let i = period + 1; i < n; i++) {
            const d = closes[i] - closes[i - 1];
            const gg = d > 0 ? d : 0;
            const ll = d < 0 ? -d : 0;
            avgG = (avgG * (period - 1) + gg) / period;
            avgL = (avgL * (period - 1) + ll) / period;
            out[i] = avgL > 0 ? 100 - 100 / (1 + avgG / avgL) : 100;
        }
        return out;
    },

    /**
     * KD 隨機指標（EMA 型平滑）
     */
    kd(highs, lows, closes, period = 9, kSm = 3, dSm = 3) {
        const n = closes.length;
        const k = new Array(n).fill(null);
        const d = new Array(n).fill(null);
        let prevK = 50, prevD = 50;
        for (let i = 0; i < n; i++) {
            if (i < period - 1) continue;
            let h = -Infinity, l = Infinity;
            for (let j = i - period + 1; j <= i; j++) {
                if (highs[j] > h) h = highs[j];
                if (lows[j] < l) l = lows[j];
            }
            const rsv = (h === l) ? 50 : (closes[i] - l) / (h - l) * 100;
            k[i] = prevK * (kSm - 1) / kSm + rsv / kSm;
            d[i] = prevD * (dSm - 1) / dSm + k[i] / dSm;
            prevK = k[i];
            prevD = d[i];
        }
        return { k, d };
    },

    /**
     * MACD
     */
    macd(closes, fast = 12, slow = 26, signal = 9) {
        const emaF = this.ema(closes, fast);
        const emaS = this.ema(closes, slow);
        const dif = emaF.map((v, i) => v - emaS[i]);
        const macd = this.ema(dif, signal);
        const osc = dif.map((v, i) => v - macd[i]);
        return { dif, macd, osc };
    },

    /**
     * 日期格式化
     */
    fmtNum(v, dec = 2) {
        if (v === null || v === undefined || isNaN(v)) return '-';
        return Number(v).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
    },

    fmtInt(v) {
        if (v === null || v === undefined || isNaN(v)) return '-';
        return Math.round(v).toLocaleString('en-US');
    },

    fmtPct(v, dec = 2) {
        if (v === null || v === undefined || isNaN(v)) return '-';
        return `${Number(v).toFixed(dec)}%`;
    },

    fmtDate(s) {
        if (!s) return '-';
        return s.slice(0, 10);
    },
};

/**
 * Chart.js 共用設定
 */
const ChartDefaults = {
    color: '#c9d1d9',
    grid:  '#21262d',
    border:'#30363d',
    tooltip: {
        backgroundColor: '#161b22',
        titleColor: '#58a6ff',
        bodyColor: '#c9d1d9',
        borderColor: '#30363d',
        borderWidth: 1,
        padding: 10,
        cornerRadius: 6,
        titleFont: { family: 'inherit' },
        bodyFont:  { family: 'inherit' },
    },
};

Chart.defaults.color = ChartDefaults.color;
Chart.defaults.borderColor = ChartDefaults.grid;
Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
