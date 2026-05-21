// TradeCore — Dashboard Page

const { useState: useDashState, useEffect: useDashEffect } = React;

// ─── Composite Score Gauge (SVG semicircle) ───────────────────────────────
const TCScoreGauge = ({ score }) => {
  const CX = 100, CY = 90, OR = 68, IR = 52;
  const zone  = score > 0.3 ? 'BUY' : score < -0.3 ? 'SELL' : 'NEUTRAL';
  const zoneC = zone === 'BUY' ? TC_COLORS.green : zone === 'SELL' ? TC_COLORS.red : TC_COLORS.textMid;

  // polar: angle in degrees from top, clockwise positive
  const P = (deg, r) => ({
    x: CX + r * Math.sin(deg * Math.PI / 180),
    y: CY - r * Math.cos(deg * Math.PI / 180),
  });

  const arc = (a1, a2, ri = IR, ro = OR) => {
    const s = P(a1, ro), e = P(a2, ro), si = P(a1, ri), ei = P(a2, ri);
    const lg = a2 - a1 > 180 ? 1 : 0;
    const fx = v => v.toFixed(2);
    return `M${fx(s.x)} ${fx(s.y)} A${ro} ${ro} 0 ${lg} 1 ${fx(e.x)} ${fx(e.y)} L${fx(ei.x)} ${fx(ei.y)} A${ri} ${ri} 0 ${lg} 0 ${fx(si.x)} ${fx(si.y)}Z`;
  };

  const needleDeg = Math.max(-90, Math.min(90, score * 90));
  const tip  = P(needleDeg, OR - 4);
  const base = P(needleDeg, 14);

  return (
    <div style={{ textAlign: 'center' }}>
      <svg viewBox="0 0 200 110" style={{ width: '100%', maxWidth: 250, overflow: 'visible', display: 'block', margin: '0 auto' }}>
        {/* Track arcs */}
        <path d={arc(-90, 90)} fill="rgba(255,255,255,0.03)"/>
        {/* SELL */}
        <path d={arc(-90, -27)} fill="rgba(255,68,68,0.22)"/>
        {/* NEUTRAL */}
        <path d={arc(-27, 27)} fill="rgba(255,255,255,0.06)"/>
        {/* BUY */}
        <path d={arc(27, 90)} fill="rgba(0,255,136,0.22)"/>

        {/* Zone ticks */}
        {[-90, -27, 0, 27, 90].map(a => {
          const t1 = P(a, OR + 3), t2 = P(a, OR + 9);
          return <line key={a} x1={t1.x.toFixed(1)} y1={t1.y.toFixed(1)} x2={t2.x.toFixed(1)} y2={t2.y.toFixed(1)} stroke={TC_COLORS.border} strokeWidth="1"/>;
        })}

        {/* Zone labels */}
        <text x="12"  y="100" textAnchor="middle" fill={TC_COLORS.red}     fontSize="7.5" fontFamily="monospace" fontWeight="700" letterSpacing="1">SELL</text>
        <text x="100" y="15"  textAnchor="middle" fill={TC_COLORS.textMuted} fontSize="7.5" fontFamily="monospace" letterSpacing="1">NEUT</text>
        <text x="188" y="100" textAnchor="middle" fill={TC_COLORS.green}   fontSize="7.5" fontFamily="monospace" fontWeight="700" letterSpacing="1">BUY</text>

        {/* Needle glow */}
        <line x1={CX.toFixed(1)} y1={CY.toFixed(1)} x2={tip.x.toFixed(1)} y2={tip.y.toFixed(1)}
          stroke={zoneC} strokeWidth="6" strokeLinecap="round" opacity="0.08"/>
        {/* Needle */}
        <line x1={base.x.toFixed(1)} y1={base.y.toFixed(1)} x2={tip.x.toFixed(1)} y2={tip.y.toFixed(1)}
          stroke={zoneC} strokeWidth="2" strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 3px ${zoneC})` }}/>
        {/* Pivot */}
        <circle cx={CX} cy={CY} r="5" fill={TC_COLORS.surface2} stroke={zoneC} strokeWidth="1.5"/>

        {/* Score text */}
        <text x={CX} y={CY + 20} textAnchor="middle" fill={zoneC} fontSize="19" fontFamily="monospace" fontWeight="700">
          {score > 0 ? '+' : ''}{score.toFixed(3)}
        </text>
      </svg>
      <div style={{ marginTop: 4 }}>
        <TCBadge variant={zone === 'BUY' ? 'buy' : zone === 'SELL' ? 'sell' : 'neutral'}>{zone} ZONE</TCBadge>
      </div>
    </div>
  );
};

// ─── Daily PnL Meter ──────────────────────────────────────────────────────
const TCPnLMeter = ({ pnl, max = 2000 }) => {
  const pos  = pnl >= 0;
  const pct  = Math.min(Math.abs(pnl) / max, 1);
  const col  = pos ? TC_COLORS.green : TC_COLORS.red;
  const meta = [
    { label: 'WIN RATE', value: '68%',   color: TC_COLORS.green   },
    { label: 'TRADES',   value: '12',    color: TC_COLORS.text     },
    { label: 'FEES',     value: '$4.28', color: TC_COLORS.textMid  },
  ];
  return (
    <div style={{ padding: '14px 18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
        <span style={{ color: TC_COLORS.textMuted, fontSize: 9, fontFamily: TC_FONTS.mono, letterSpacing: '0.12em', textTransform: 'uppercase' }}>Daily P&amp;L</span>
        <span style={{ color: col, fontFamily: TC_FONTS.mono, fontSize: 22, fontWeight: 700, letterSpacing: '-0.01em' }}>
          {pos ? '+' : '-'}${Math.abs(pnl).toFixed(2)}
        </span>
      </div>
      {/* Bar */}
      <div style={{ position: 'relative', height: 6, background: TC_COLORS.surface2, borderRadius: 3, overflow: 'hidden' }}>
        <div style={{
          position: 'absolute', height: '100%',
          width: `${pct * 50}%`,
          left: pos ? '50%' : `${50 - pct * 50}%`,
          background: col, borderRadius: 3,
          boxShadow: `0 0 8px ${col}`,
          transition: 'all 0.5s ease',
        }}/>
        <div style={{ position: 'absolute', left: '50%', top: 0, width: 1, height: '100%', background: TC_COLORS.borderHi }}/>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5 }}>
        <span style={{ color: TC_COLORS.red,     fontSize: 9, fontFamily: TC_FONTS.mono }}>-${max}</span>
        <span style={{ color: TC_COLORS.textMuted, fontSize: 9, fontFamily: TC_FONTS.mono }}>0</span>
        <span style={{ color: TC_COLORS.green,   fontSize: 9, fontFamily: TC_FONTS.mono }}>+${max}</span>
      </div>
      {/* Stats row */}
      <div style={{ display: 'flex', gap: 20, marginTop: 16 }}>
        {meta.map(({ label, value, color }) => (
          <div key={label}>
            <div style={{ color: TC_COLORS.textMuted, fontSize: 9, fontFamily: TC_FONTS.mono, letterSpacing: '0.1em', marginBottom: 3 }}>{label}</div>
            <div style={{ color, fontFamily: TC_FONTS.mono, fontSize: 14, fontWeight: 600 }}>{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ─── Status Card ──────────────────────────────────────────────────────────
const TCStatusCard = ({ label, value, sub, status }) => {
  const col = status === 'ok' ? TC_COLORS.green : status === 'warn' ? TC_COLORS.yellow : TC_COLORS.red;
  return (
    <TCCard style={{ padding: '14px 16px', flex: 1, minWidth: 0 }}>
      <div style={{ color: TC_COLORS.textMuted, fontSize: 9, fontFamily: TC_FONTS.mono, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 10 }}>
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 7, height: 7, borderRadius: '50%', background: col, boxShadow: `0 0 7px ${col}`, flexShrink: 0 }}/>
        <span style={{ color: TC_COLORS.text, fontFamily: TC_FONTS.mono, fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</span>
      </div>
      {sub && <div style={{ color: TC_COLORS.textMuted, fontSize: 10, fontFamily: TC_FONTS.mono, marginTop: 5 }}>{sub}</div>}
    </TCCard>
  );
};

// ─── Dashboard Page ───────────────────────────────────────────────────────
const DashboardPage = ({ killSwitch }) => {
  const [tick, setTick] = useDashState(0);

  useDashEffect(() => {
    const iv = setInterval(() => setTick(t => t + 1), 2500);
    return () => clearInterval(iv);
  }, []);

  // Simulate live PnL ticking
  const livePnl = 847.23 + Math.sin(tick * 0.7) * 12;

  const posColumns = [
    { key: 'symbol', label: 'Symbol', mono: true },
    { key: 'side',   label: 'Side',   render: v => <TCBadge variant={v === 'LONG' ? 'buy' : 'sell'}>{v}</TCBadge> },
    { key: 'qty',    label: 'Qty',    mono: true, right: true, render: v => <span style={{ fontFamily: TC_FONTS.mono, color: TC_COLORS.textMid }}>{v}</span> },
    { key: 'entry',  label: 'Entry',  mono: true, right: true, render: v => <span style={{ fontFamily: TC_FONTS.mono }}>${v.toLocaleString()}</span> },
    { key: 'pnl',    label: 'P&L',    mono: true, right: true, render: (v, row) => (
      <span style={{ fontFamily: TC_FONTS.mono, color: v >= 0 ? TC_COLORS.green : TC_COLORS.red, fontWeight: 600 }}>
        {v >= 0 ? '+' : ''}${v.toFixed(2)}&nbsp;
        <span style={{ opacity: 0.6, fontSize: 10 }}>({row.pnlPct >= 0 ? '+' : ''}{row.pnlPct.toFixed(2)}%)</span>
      </span>
    )},
  ];

  const tradeColumns = [
    { key: 'ts',     label: 'Time',   mono: true, render: v => <span style={{ fontFamily: TC_FONTS.mono, color: TC_COLORS.textMuted, fontSize: 11 }}>{v}</span> },
    { key: 'symbol', label: 'Symbol', mono: true },
    { key: 'side',   label: 'Side',   render: v => <TCBadge variant={v === 'BUY' ? 'buy' : 'sell'}>{v}</TCBadge> },
    { key: 'price',  label: 'Price',  mono: true, right: true, render: v => <span style={{ fontFamily: TC_FONTS.mono }}>${v.toLocaleString()}</span> },
    { key: 'pnl',    label: 'P&L',    mono: true, right: true, render: v => (
      <span style={{ fontFamily: TC_FONTS.mono, color: v >= 0 ? TC_COLORS.green : TC_COLORS.red, fontWeight: 600 }}>
        {v >= 0 ? '+' : '-'}${Math.abs(v).toFixed(2)}
      </span>
    )},
  ];

  return (
    <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Row 1: status cards */}
      <div style={{ display: 'flex', gap: 12 }}>
        <TCStatusCard label="Database"        value="Connected"         sub="pg://localhost:5432"           status="ok"/>
        <TCStatusCard label="Scheduler"       value="Running"           sub={`Next cycle: 00:${String(42 - (tick % 42)).padStart(2,'0')}s`} status="ok"/>
        <TCStatusCard label="Kill Switch"     value={killSwitch ? 'ACTIVE' : 'Off'} sub={killSwitch ? 'Trading halted' : 'Trading enabled'} status={killSwitch ? 'error' : 'ok'}/>
        <TCStatusCard label="Active Strategy" value="BTC Momentum v2"   sub="15m · Binance · PAPER"         status="ok"/>
      </div>

      {/* Row 2: positions + trades */}
      <div style={{ display: 'flex', gap: 12 }}>
        <TCCard style={{ flex: 1 }}>
          <TCSectionHeader title="Open Positions" right={<TCBadge variant="accent">{TC_POSITIONS.length} active</TCBadge>}/>
          <TCTable columns={posColumns} rows={TC_POSITIONS} emptyMsg="No open positions"/>
        </TCCard>
        <TCCard style={{ flex: 1 }}>
          <TCSectionHeader title="Recent Trades" right={<TCBadge>{TC_TRADES.length} today</TCBadge>}/>
          <TCTable columns={tradeColumns} rows={TC_TRADES} emptyMsg="No recent trades"/>
        </TCCard>
      </div>

      {/* Row 3: PnL meter + Composite score */}
      <div style={{ display: 'flex', gap: 12 }}>
        <TCCard style={{ flex: 1 }}>
          <TCSectionHeader title="Daily P&L" right={<span style={{ color: TC_COLORS.textMuted, fontSize: 9, fontFamily: TC_FONTS.mono, animation: 'tcPulse 2s infinite' }}>● LIVE</span>}/>
          <TCPnLMeter pnl={livePnl}/>
        </TCCard>
        <TCCard style={{ flex: 1 }}>
          <TCSectionHeader title="Composite Score" right={<span style={{ color: TC_COLORS.textMuted, fontSize: 9, fontFamily: TC_FONTS.mono }}>BTC/USDT · 15m</span>}/>
          <div style={{ padding: '14px 12px' }}>
            <TCScoreGauge score={0.67}/>
          </div>
        </TCCard>
      </div>
    </div>
  );
};

Object.assign(window, { DashboardPage });
