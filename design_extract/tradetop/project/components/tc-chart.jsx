// TradeCore — Chart View Page

const { useState: useChartState, useEffect: useChartEffect, useRef: useChartRef } = React;

const CHART_SYMBOLS = [
  { label: 'BTC/USDT', base: 62000, vol: 0.014 },
  { label: 'ETH/USDT', base:  3280, vol: 0.016 },
  { label: 'SOL/USDT', base:   142, vol: 0.022 },
];
const CHART_TFS = ['1m','5m','15m','1h','4h','1d'];

// ─── Indicator Bar ────────────────────────────────────────────────────────
const IndicatorBar = ({ label, value, rawLabel, weight }) => {
  const col  = value > 0.3 ? TC_COLORS.green : value < -0.3 ? TC_COLORS.red : TC_COLORS.textMid;
  const contrib = (value * weight).toFixed(4);
  const pctHalf = Math.min(Math.abs(value), 1) * 50; // 0–50% from center

  return (
    <div style={{ padding: '9px 16px', borderRight: `1px solid ${TC_COLORS.border}` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.05em' }}>{label}</span>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ color: col, fontSize: 10, fontFamily: TC_FONTS.mono, fontWeight: 600 }}>
            {value >= 0 ? '+' : ''}{value.toFixed(3)}
          </span>
          <span style={{ color: TC_COLORS.textMuted, fontSize: 9, fontFamily: TC_FONTS.mono }}>
            ×{weight.toFixed(2)}={contrib > 0 ? '+' : ''}{contrib}
          </span>
          <span style={{ color: TC_COLORS.textMuted, fontSize: 9, fontFamily: TC_FONTS.mono, opacity: 0.6 }}>({rawLabel})</span>
        </div>
      </div>
      <div style={{ position: 'relative', height: 3, background: TC_COLORS.surface2, borderRadius: 2 }}>
        <div style={{
          position: 'absolute', height: '100%',
          width: `${pctHalf}%`,
          left: value >= 0 ? '50%' : `${50 - pctHalf}%`,
          background: col, borderRadius: 2,
          boxShadow: `0 0 5px ${col}55`,
        }}/>
        <div style={{ position: 'absolute', left: '50%', top: 0, width: 1, height: '100%', background: TC_COLORS.borderHi }}/>
      </div>
    </div>
  );
};

// ─── Chart LW wrapper ─────────────────────────────────────────────────────
const LWChart = ({ symbol, timeframe }) => {
  const containerRef = useChartRef(null);
  const chartRef     = useChartRef(null);

  useChartEffect(() => {
    if (!containerRef.current || !window.LightweightCharts) return;

    const sym  = CHART_SYMBOLS.find(s => s.label === symbol) || CHART_SYMBOLS[0];
    const data = tcGenerateCandleData(sym.base, 200, sym.vol);

    const chart = LightweightCharts.createChart(containerRef.current, {
      layout: {
        background: { color: TC_COLORS.bg },
        textColor:   TC_COLORS.textMuted,
        fontFamily:  TC_FONTS.mono,
        fontSize:    11,
      },
      grid: {
        vertLines: { color: 'rgba(255,255,255,0.04)' },
        horzLines: { color: 'rgba(255,255,255,0.04)' },
      },
      crosshair: {
        vertLine: { color: TC_COLORS.accent + '66', labelBackgroundColor: TC_COLORS.surface2 },
        horzLine: { color: TC_COLORS.accent + '66', labelBackgroundColor: TC_COLORS.surface2 },
      },
      rightPriceScale: { borderColor: TC_COLORS.border },
      timeScale:       { borderColor: TC_COLORS.border, timeVisible: true },
      width:  containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    });

    const series = chart.addCandlestickSeries({
      upColor:        TC_COLORS.green,
      downColor:      TC_COLORS.red,
      borderUpColor:  TC_COLORS.green,
      borderDownColor:TC_COLORS.red,
      wickUpColor:    TC_COLORS.green,
      wickDownColor:  TC_COLORS.red,
    });
    series.setData(data);
    chart.timeScale().fitContent();
    chartRef.current = chart;

    const ro = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width:  containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    });
    ro.observe(containerRef.current);

    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; };
  }, [symbol, timeframe]);

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }}/>;
};

// ─── Chart Page ───────────────────────────────────────────────────────────
const ChartPage = () => {
  const [symbol,    setSymbol]    = useChartState('BTC/USDT');
  const [timeframe, setTimeframe] = useChartState('15m');

  const score = 0.67;
  const zone  = score > 0.3 ? 'BUY' : score < -0.3 ? 'SELL' : 'NEUTRAL';
  const inds  = Object.entries(TC_INDICATORS);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

      {/* Controls bar */}
      <div style={{
        padding: '10px 18px', borderBottom: `1px solid ${TC_COLORS.border}`,
        display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0,
        background: TC_COLORS.surface,
      }}>
        {/* Symbol pills */}
        <div style={{ display: 'flex', gap: 5 }}>
          {CHART_SYMBOLS.map(s => {
            const on = symbol === s.label;
            return (
              <button key={s.label} onClick={() => setSymbol(s.label)} style={{
                padding: '4px 12px', borderRadius: 5, cursor: 'pointer',
                border: `1px solid ${on ? TC_COLORS.accent : TC_COLORS.border}`,
                background: on ? TC_COLORS.accentDim : 'transparent',
                color: on ? TC_COLORS.accent : TC_COLORS.textMid,
                fontFamily: TC_FONTS.mono, fontSize: 11.5, fontWeight: on ? 600 : 400,
                transition: 'all 0.12s',
              }}>{s.label}</button>
            );
          })}
        </div>

        <div style={{ width: 1, height: 18, background: TC_COLORS.border }}/>

        {/* Timeframe pills */}
        <div style={{ display: 'flex', gap: 3 }}>
          {CHART_TFS.map(tf => {
            const on = timeframe === tf;
            return (
              <button key={tf} onClick={() => setTimeframe(tf)} style={{
                padding: '3px 9px', borderRadius: 4, cursor: 'pointer',
                border: 'none',
                background: on ? TC_COLORS.surface3 : 'transparent',
                color: on ? TC_COLORS.text : TC_COLORS.textMuted,
                fontFamily: TC_FONTS.mono, fontSize: 11, fontWeight: on ? 600 : 400,
                transition: 'all 0.12s',
              }}>{tf}</button>
            );
          })}
        </div>

        {/* Composite score pill */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
          <TCBadge variant={zone === 'BUY' ? 'buy' : zone === 'SELL' ? 'sell' : 'neutral'}>
            {zone} ZONE
          </TCBadge>
          <span style={{
            color: zone === 'BUY' ? TC_COLORS.green : zone === 'SELL' ? TC_COLORS.red : TC_COLORS.textMid,
            fontFamily: TC_FONTS.mono, fontSize: 18, fontWeight: 700,
          }}>
            {score > 0 ? '+' : ''}{score.toFixed(3)}
          </span>
        </div>
      </div>

      {/* Chart area */}
      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        <LWChart symbol={symbol} timeframe={timeframe}/>
      </div>

      {/* Indicator panel */}
      <div style={{ flexShrink: 0, borderTop: `1px solid ${TC_COLORS.border}`, background: TC_COLORS.surface }}>
        <TCSectionHeader title="Indicator Snapshot" right={
          <span style={{ color: TC_COLORS.textMuted, fontSize: 9, fontFamily: TC_FONTS.mono }}>
            Last: {new Date().toTimeString().slice(0, 8)}
          </span>
        }/>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)' }}>
          {inds.map(([key, ind]) => (
            <IndicatorBar key={key} label={ind.label} value={ind.value} rawLabel={ind.rawLabel} weight={ind.weight}/>
          ))}
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { ChartPage });
