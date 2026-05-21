// TradeCore — Global constants, mock data, generators
// Exported to window for cross-script access

const TC_COLORS = {
  bg:           '#0a0a0f',
  surface:      '#0f0f1a',
  surface2:     '#141428',
  surface3:     '#1a1a35',
  border:       'rgba(255,255,255,0.07)',
  borderHi:     'rgba(255,255,255,0.12)',
  accent:       '#00d4ff',
  accentDim:    'rgba(0,212,255,0.12)',
  accentGlow:   'rgba(0,212,255,0.25)',
  green:        '#00ff88',
  greenDim:     'rgba(0,255,136,0.12)',
  red:          '#ff4444',
  redDim:       'rgba(255,68,68,0.12)',
  yellow:       '#ffcc00',
  yellowDim:    'rgba(255,204,0,0.12)',
  text:         '#dde2ed',
  textMid:      '#8892a4',
  textMuted:    '#454f63',
};

const TC_FONTS = {
  ui:   "'Inter', 'SF Pro Display', system-ui, sans-serif",
  mono: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
};

// ─── Candle data generator ─────────────────────────────────────────────────
function tcGenerateCandleData(basePrice = 62000, count = 200, volatility = 0.014) {
  const data = [];
  let price = basePrice;
  let t = Math.floor(new Date('2025-01-01').getTime() / 1000);
  const step = 900; // 15min in seconds

  for (let i = 0; i < count; i++) {
    const vol = price * volatility;
    const open = price;
    const drift = (Math.random() - 0.47) * vol;
    const close = Math.max(open * 0.5, open + drift);
    const high  = Math.max(open, close) + Math.random() * vol * 0.4;
    const low   = Math.min(open, close) - Math.random() * vol * 0.4;
    data.push({ time: t, open, high, low, close });
    price = close;
    t += step;
  }
  return data;
}

// ─── Equity curve generator ────────────────────────────────────────────────
function tcGenerateEquityCurve(initialCapital = 10000, count = 90) {
  const data = [];
  let equity = initialCapital;
  let t = Math.floor(new Date('2025-01-01').getTime() / 1000);
  const step = 86400;

  for (let i = 0; i < count; i++) {
    const ret = (Math.random() - 0.40) * equity * 0.022;
    equity = Math.max(equity * 0.4, equity + ret);
    data.push({ time: t, value: Math.round(equity * 100) / 100 });
    t += step;
  }
  return data;
}

// ─── Signal events generator ───────────────────────────────────────────────
function tcGenerateSignals(count = 50) {
  const symbols  = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT'];
  const reasons  = [
    'RSI oversold + MACD bullish crossover detected',
    'Composite score exceeded buy threshold (0.30)',
    'BB position at lower band with volume surge 1.8×',
    'EMA 9/21 cross confirmed on 15m candle',
    'Positive sentiment shift; score rising from 0.18',
    'Score below sell threshold — elevated risk',
    'Mixed signals — holding current position',
    'Volume below 7-day average; awaiting confirmation',
    'MACD histogram bearish divergence on 1h',
    'Trend reversal pattern: engulfing candle detected',
    'RSI approaching overbought (74) — caution',
    'Composite score flat; no actionable signal',
  ];
  const signals = [];
  const now = Date.now();

  for (let i = 0; i < count; i++) {
    const score  = parseFloat((Math.random() * 2 - 1).toFixed(3));
    const zone   = score >  0.3 ? 'BUY' : score < -0.3 ? 'SELL' : 'NEUTRAL';
    const action = zone === 'BUY' ? 'BUY' : zone === 'SELL' ? 'SELL' : 'HOLD';
    signals.push({
      id:     i,
      ts:     new Date(now - i * 68000 - Math.random() * 20000),
      symbol: symbols[Math.floor(Math.random() * symbols.length)],
      score, zone, action,
      reason: reasons[Math.floor(Math.random() * reasons.length)],
    });
  }
  return signals;
}

// ─── Static mock state ─────────────────────────────────────────────────────
const TC_POSITIONS = [
  { id: 1, symbol: 'BTC/USDT', side: 'LONG',  qty: 0.05, entry: 62380, current: 62847, pnl:  23.35, pnlPct:  0.75 },
  { id: 2, symbol: 'ETH/USDT', side: 'SHORT', qty: 1.20, entry:  3290, current:  3261, pnl:  34.80, pnlPct:  1.06 },
];

const TC_TRADES = [
  { id: 1, ts: '14:23:05', symbol: 'BTC/USDT', side: 'BUY',  price: 62380, qty: 0.05, pnl:  35.00 },
  { id: 2, ts: '14:15:42', symbol: 'ETH/USDT', side: 'SELL', price:  3290, qty: 1.20, pnl:  12.80 },
  { id: 3, ts: '13:58:11', symbol: 'SOL/USDT', side: 'BUY',  price:   142, qty: 5.00, pnl:  -8.50 },
  { id: 4, ts: '13:44:22', symbol: 'BTC/USDT', side: 'SELL', price: 62100, qty: 0.03, pnl:  62.10 },
  { id: 5, ts: '13:31:08', symbol: 'ETH/USDT', side: 'BUY',  price:  3240, qty: 0.80, pnl:  38.40 },
];

const TC_STRATEGIES = [
  { id: 1, name: 'BTC Momentum v2',      symbol: 'BTC/USDT', exchange: 'Binance', timeframe: '15m', active: true,
    weights: { rsi: 0.25, macd: 0.20, bb: 0.15, ema: 0.20, volume: 0.10, sentiment: 0.10 },
    buyThreshold: 0.30, sellThreshold: 0.30, usdtAmount: 500, maxPositions: 3, maxDailyLoss: 150 },
  { id: 2, name: 'ETH Mean Reversion',   symbol: 'ETH/USDT', exchange: 'Binance', timeframe: '1h',  active: false,
    weights: { rsi: 0.30, macd: 0.15, bb: 0.25, ema: 0.15, volume: 0.10, sentiment: 0.05 },
    buyThreshold: 0.25, sellThreshold: 0.25, usdtAmount: 300, maxPositions: 2, maxDailyLoss: 100 },
  { id: 3, name: 'Multi-Asset Scanner',  symbol: 'SOL/USDT', exchange: 'Binance', timeframe: '5m',  active: false,
    weights: { rsi: 0.20, macd: 0.20, bb: 0.20, ema: 0.20, volume: 0.10, sentiment: 0.10 },
    buyThreshold: 0.35, sellThreshold: 0.35, usdtAmount: 200, maxPositions: 5, maxDailyLoss:  80 },
];

const TC_INDICATORS = {
  rsi:       { label: 'RSI',          value:  0.68, rawLabel: '68.2',   weight: 0.25 },
  macd:      { label: 'MACD',         value:  0.55, rawLabel: '+0.023', weight: 0.20 },
  bb:        { label: 'BB Position',  value:  0.72, rawLabel: '0.72',   weight: 0.15 },
  ema:       { label: 'EMA Cross',    value:  0.60, rawLabel: '+0.60',  weight: 0.20 },
  volume:    { label: 'Volume Surge', value:  0.45, rawLabel: '1.34×',  weight: 0.10 },
  sentiment: { label: 'Sentiment',    value:  0.58, rawLabel: '+0.58',  weight: 0.10 },
};

const TC_BACKTEST_TRADES = [
  { id:1, entryTime:'2025-01-05 09:15', exitTime:'2025-01-05 14:32', side:'LONG',  entryPrice:95420, exitPrice:97850, pnl:  121.50, cumPnl:  121.50 },
  { id:2, entryTime:'2025-01-07 11:00', exitTime:'2025-01-07 16:45', side:'SHORT', entryPrice:98200, exitPrice:97100, pnl:   55.00, cumPnl:  176.50 },
  { id:3, entryTime:'2025-01-09 08:30', exitTime:'2025-01-09 12:15', side:'LONG',  entryPrice:96800, exitPrice:95200, pnl:  -80.00, cumPnl:   96.50 },
  { id:4, entryTime:'2025-01-11 10:00', exitTime:'2025-01-11 17:20', side:'LONG',  entryPrice:97500, exitPrice:99200, pnl:   85.00, cumPnl:  181.50 },
  { id:5, entryTime:'2025-01-14 09:45', exitTime:'2025-01-14 15:30', side:'SHORT', entryPrice:100200,exitPrice:98900, pnl:   65.00, cumPnl:  246.50 },
  { id:6, entryTime:'2025-01-16 10:15', exitTime:'2025-01-16 14:00', side:'LONG',  entryPrice:99400, exitPrice:98100, pnl:  -65.00, cumPnl:  181.50 },
  { id:7, entryTime:'2025-01-18 09:30', exitTime:'2025-01-19 11:20', side:'LONG',  entryPrice:97800, exitPrice:101500,pnl:  185.00, cumPnl:  366.50 },
];

Object.assign(window, {
  TC_COLORS, TC_FONTS,
  TC_POSITIONS, TC_TRADES, TC_STRATEGIES, TC_INDICATORS, TC_BACKTEST_TRADES,
  tcGenerateCandleData, tcGenerateEquityCurve, tcGenerateSignals,
});
