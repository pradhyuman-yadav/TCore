// TradeCore — Backtest Page

const { useState: useBTState, useEffect: useBTEffect, useRef: useBTRef } = React;

const BT_STATS = { totalReturn: 34.7, sharpe: 1.82, winRate: 64.3, maxDrawdown: -12.4, totalTrades: 127 };

const BTStatCard = ({ label, value, color, prefix = '', suffix = '' }) => (
  <TCCard style={{ flex: 1, padding: '14px 16px', textAlign: 'center' }}>
    <div style={{ color: TC_COLORS.textMuted, fontSize: 9, fontFamily: TC_FONTS.mono, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 10 }}>{label}</div>
    <div style={{ color: color || TC_COLORS.text, fontFamily: TC_FONTS.mono, fontSize: 21, fontWeight: 700, letterSpacing: '-0.01em' }}>
      {prefix}{value}{suffix}
    </div>
  </TCCard>
);

// ─── Equity Curve chart ───────────────────────────────────────────────────
const EquityChart = ({ capital }) => {
  const ref  = useBTRef(null);
  const inst = useBTRef(null);

  useBTEffect(() => {
    if (!ref.current || !window.LightweightCharts) return;
    if (inst.current) { inst.current.remove(); inst.current = null; }

    const chart = LightweightCharts.createChart(ref.current, {
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
      width:  ref.current.clientWidth,
      height: 210,
    });

    const series = chart.addLineSeries({
      color:               TC_COLORS.accent,
      lineWidth:           2,
      priceLineVisible:    false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius:  4,
    });

    // Add a baseline series for initial capital
    const baselineSeries = chart.addLineSeries({
      color:            TC_COLORS.border,
      lineWidth:        1,
      lineStyle:        2, // dashed
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });

    const data = tcGenerateEquityCurve(capital, 90);
    series.setData(data);
    baselineSeries.setData([{ time: data[0].time, value: capital }, { time: data[data.length - 1].time, value: capital }]);
    chart.timeScale().fitContent();
    inst.current = chart;

    const ro = new ResizeObserver(() => {
      if (ref.current && inst.current) {
        inst.current.applyOptions({ width: ref.current.clientWidth });
      }
    });
    ro.observe(ref.current);

    return () => { ro.disconnect(); if (inst.current) { inst.current.remove(); inst.current = null; } };
  }, [capital]);

  return <div ref={ref} style={{ width: '100%' }}/>;
};

// ─── Backtest Page ────────────────────────────────────────────────────────
const BacktestPage = () => {
  const [dateFrom, setDateFrom] = useBTState('2025-01-01');
  const [dateTo,   setDateTo]   = useBTState('2025-04-01');
  const [capital,  setCapital]  = useBTState(10000);
  const [hasResults, setResults] = useBTState(true);
  const [running,   setRunning]  = useBTState(false);

  const run = () => {
    setRunning(true);
    setTimeout(() => { setRunning(false); setResults(true); }, 1600);
  };

  const tradeColumns = [
    { key: 'entryTime', label: 'Entry',      render: v => <span style={{ fontFamily: TC_FONTS.mono, color: TC_COLORS.textMuted, fontSize: 11 }}>{v}</span> },
    { key: 'exitTime',  label: 'Exit',       render: v => <span style={{ fontFamily: TC_FONTS.mono, color: TC_COLORS.textMuted, fontSize: 11 }}>{v}</span> },
    { key: 'side',      label: 'Side',       render: v => <TCBadge variant={v === 'LONG' ? 'buy' : 'sell'}>{v}</TCBadge> },
    { key: 'entryPrice',label: 'Entry $',    right: true, render: v => <span style={{ fontFamily: TC_FONTS.mono }}>${v.toLocaleString()}</span> },
    { key: 'exitPrice', label: 'Exit $',     right: true, render: v => <span style={{ fontFamily: TC_FONTS.mono }}>${v.toLocaleString()}</span> },
    { key: 'pnl',       label: 'P&L',        right: true, render: v => (
      <span style={{ fontFamily: TC_FONTS.mono, color: v >= 0 ? TC_COLORS.green : TC_COLORS.red, fontWeight: 600 }}>
        {v >= 0 ? '+' : ''}${v.toFixed(2)}
      </span>
    )},
    { key: 'cumPnl',    label: 'Cum. P&L',   right: true, render: v => (
      <span style={{ fontFamily: TC_FONTS.mono, color: TC_COLORS.accent }}>${v.toFixed(2)}</span>
    )},
  ];

  const inputStyle = {
    padding: '7px 10px', background: TC_COLORS.surface2, border: `1px solid ${TC_COLORS.border}`,
    borderRadius: 5, color: TC_COLORS.text, fontFamily: TC_FONTS.mono, fontSize: 12, outline: 'none',
  };

  return (
    <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Controls */}
      <TCCard style={{ padding: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, flexWrap: 'wrap' }}>
          <div>
            <div style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.08em', marginBottom: 5, textTransform: 'uppercase' }}>From</div>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ ...inputStyle, colorScheme: 'dark' }}/>
          </div>
          <div>
            <div style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.08em', marginBottom: 5, textTransform: 'uppercase' }}>To</div>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ ...inputStyle, colorScheme: 'dark' }}/>
          </div>
          <div>
            <div style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.08em', marginBottom: 5, textTransform: 'uppercase' }}>Initial Capital (USDT)</div>
            <input type="number" value={capital} onChange={e => setCapital(parseFloat(e.target.value) || 10000)}
              style={{ ...inputStyle, color: TC_COLORS.accent, width: 150 }}/>
          </div>
          <div>
            <div style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.08em', marginBottom: 5, textTransform: 'uppercase' }}>Strategy</div>
            <select style={{ ...inputStyle, cursor: 'pointer', appearance: 'none', paddingRight: 28 }}>
              {TC_STRATEGIES.map(s => <option key={s.id} style={{ background: TC_COLORS.surface2 }}>{s.name}</option>)}
            </select>
          </div>
          <button onClick={run} disabled={running} style={{
            marginLeft: 'auto', padding: '8px 22px', borderRadius: 5, cursor: running ? 'not-allowed' : 'pointer',
            background: running ? TC_COLORS.surface2 : TC_COLORS.accent,
            border: `1px solid ${running ? TC_COLORS.border : TC_COLORS.accent}`,
            color: running ? TC_COLORS.textMid : TC_COLORS.bg,
            fontFamily: TC_FONTS.mono, fontSize: 11, fontWeight: 700, letterSpacing: '0.06em',
            transition: 'all 0.2s',
          }}>
            {running ? '⏳ RUNNING…' : '▶ RUN BACKTEST'}
          </button>
        </div>
      </TCCard>

      {hasResults && (
        <>
          {/* Stat row */}
          <div style={{ display: 'flex', gap: 10 }}>
            <BTStatCard label="Total Return"  value={`+${BT_STATS.totalReturn}`}  suffix="%"  color={TC_COLORS.green}/>
            <BTStatCard label="Sharpe Ratio"  value={BT_STATS.sharpe}                          color={TC_COLORS.accent}/>
            <BTStatCard label="Win Rate"      value={BT_STATS.winRate}            suffix="%"  color={TC_COLORS.green}/>
            <BTStatCard label="Max Drawdown"  value={BT_STATS.maxDrawdown}        suffix="%"  color={TC_COLORS.red}/>
            <BTStatCard label="Total Trades"  value={BT_STATS.totalTrades}/>
          </div>

          {/* Equity curve */}
          <TCCard>
            <TCSectionHeader title="Equity Curve" right={
              <span style={{ color: TC_COLORS.textMuted, fontSize: 9, fontFamily: TC_FONTS.mono }}>Initial: ${capital.toLocaleString()}</span>
            }/>
            <EquityChart capital={capital}/>
          </TCCard>

          {/* Trade log */}
          <TCCard>
            <TCSectionHeader title="Trade Log" right={<TCBadge>{TC_BACKTEST_TRADES.length} trades</TCBadge>}/>
            <TCTable columns={tradeColumns} rows={TC_BACKTEST_TRADES} emptyMsg="No trades"/>
          </TCCard>
        </>
      )}
    </div>
  );
};

Object.assign(window, { BacktestPage });
