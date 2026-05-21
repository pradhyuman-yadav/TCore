// TradeCore — Signal Monitor Page

const { useState: useSigState, useEffect: useSigEffect, useRef: useSigRef } = React;

const FILTERS = ['ALL','BUY','SELL','HOLD'];

const fmtTime = ts => {
  if (!ts) return '—';
  const d = ts instanceof Date ? ts : new Date(ts);
  return d.toTimeString().slice(0, 8);
};

// ─── Signal Row ───────────────────────────────────────────────────────────
const SignalRow = ({ signal }) => {
  const { ts, symbol, score, zone, action, reason } = signal;
  const col   = action === 'BUY' ? TC_COLORS.green : action === 'SELL' ? TC_COLORS.red : TC_COLORS.textMid;
  const pct   = Math.min(Math.abs(score), 1) * 50;

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '76px 100px 200px 76px 1fr',
        alignItems: 'center', gap: 0,
        padding: '0',
        borderBottom: `1px solid ${TC_COLORS.border}`,
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.025)'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
    >
      <span style={{ padding: '9px 14px', color: TC_COLORS.textMuted, fontFamily: TC_FONTS.mono, fontSize: 11 }}>
        {fmtTime(ts)}
      </span>
      <span style={{ padding: '9px 14px', color: TC_COLORS.text, fontFamily: TC_FONTS.mono, fontSize: 12, fontWeight: 500 }}>
        {symbol}
      </span>

      {/* Score bar cell */}
      <div style={{ padding: '9px 14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ color: col, fontFamily: TC_FONTS.mono, fontSize: 11, fontWeight: 600 }}>
            {score >= 0 ? '+' : ''}{score.toFixed(3)}
          </span>
          <span style={{ color: TC_COLORS.textMuted, fontFamily: TC_FONTS.mono, fontSize: 9 }}>
            {zone}
          </span>
        </div>
        <div style={{ position: 'relative', height: 3, background: TC_COLORS.surface2, borderRadius: 2, overflow: 'hidden' }}>
          <div style={{
            position: 'absolute', height: '100%',
            width: `${pct}%`,
            left: score >= 0 ? '50%' : `${50 - pct}%`,
            background: col, borderRadius: 2,
            boxShadow: `0 0 4px ${col}77`,
          }}/>
          <div style={{ position: 'absolute', left: '50%', top: 0, width: 1, height: '100%', background: TC_COLORS.borderHi }}/>
        </div>
      </div>

      <div style={{ padding: '9px 14px' }}>
        <TCBadge variant={action === 'BUY' ? 'buy' : action === 'SELL' ? 'sell' : 'neutral'}>{action}</TCBadge>
      </div>

      <span style={{ padding: '9px 14px 9px 0', color: TC_COLORS.textMid, fontFamily: TC_FONTS.ui, fontSize: 11.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {reason}
      </span>
    </div>
  );
};

// ─── Signal Page ──────────────────────────────────────────────────────────
const SignalPage = () => {
  const [filter,    setFilter]    = useSigState('ALL');
  const [signals,   setSignals]   = useSigState(() => tcGenerateSignals(50));
  const [latency,   setLatency]   = useSigState(28);
  const [highlight, setHighlight] = useSigState(null);
  const feedRef = useSigRef(null);

  // Simulate live incoming signals
  useSigEffect(() => {
    const iv = setInterval(() => {
      const fresh = tcGenerateSignals(1)[0];
      fresh.id  = Date.now();
      fresh.ts  = new Date();
      setSignals(prev => [fresh, ...prev.slice(0, 49)]);
      setLatency(Math.floor(18 + Math.random() * 35));
      setHighlight(fresh.id);
      setTimeout(() => setHighlight(null), 800);
    }, 3800);
    return () => clearInterval(iv);
  }, []);

  const filtered = filter === 'ALL' ? signals : signals.filter(s => s.action === filter);

  const filterColor = f =>
    f === 'BUY' ? TC_COLORS.green : f === 'SELL' ? TC_COLORS.red : TC_COLORS.accent;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

      {/* WS connection banner */}
      <div style={{
        padding: '8px 18px', flexShrink: 0,
        background: 'rgba(0,255,136,0.04)',
        borderBottom: `1px solid rgba(0,255,136,0.15)`,
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <div style={{ width: 7, height: 7, borderRadius: '50%', background: TC_COLORS.green, boxShadow: `0 0 9px ${TC_COLORS.green}`, animation: 'tcPulse 2s ease-in-out infinite' }}/>
        <span style={{ color: TC_COLORS.green, fontFamily: TC_FONTS.mono, fontSize: 11, fontWeight: 700 }}>CONNECTED</span>
        <span style={{ color: TC_COLORS.textMuted, fontFamily: TC_FONTS.mono, fontSize: 11 }}>
          ws://localhost:8080/signals
        </span>
        <div style={{ width: 1, height: 16, background: TC_COLORS.border }}/>
        <span style={{ fontFamily: TC_FONTS.mono, fontSize: 11, color: latency < 30 ? TC_COLORS.green : latency < 60 ? TC_COLORS.yellow : TC_COLORS.red }}>
          {latency}ms
        </span>
        <div style={{ marginLeft: 'auto', color: TC_COLORS.textMuted, fontSize: 10, fontFamily: TC_FONTS.mono }}>
          {signals.length} events · newest: {fmtTime(signals[0]?.ts)}
        </div>
      </div>

      {/* Filter chips */}
      <div style={{
        padding: '10px 18px', flexShrink: 0,
        borderBottom: `1px solid ${TC_COLORS.border}`,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        {FILTERS.map(f => {
          const on = filter === f;
          const fc = f === 'ALL' ? TC_COLORS.accent : filterColor(f);
          return (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding: '4px 14px', borderRadius: 4, cursor: 'pointer',
              border: `1px solid ${on ? fc : TC_COLORS.border}`,
              background: on ? fc + '20' : 'transparent',
              color: on ? fc : TC_COLORS.textMid,
              fontFamily: TC_FONTS.mono, fontSize: 11, fontWeight: 700,
              letterSpacing: '0.05em', transition: 'all 0.12s',
            }}>{f}</button>
          );
        })}
        <span style={{ marginLeft: 'auto', color: TC_COLORS.textMuted, fontSize: 10, fontFamily: TC_FONTS.mono }}>
          {filtered.length} events shown
        </span>
      </div>

      {/* Column headers */}
      <div style={{
        display: 'grid', gridTemplateColumns: '76px 100px 200px 76px 1fr',
        padding: '7px 0', flexShrink: 0,
        borderBottom: `1px solid ${TC_COLORS.border}`,
        background: TC_COLORS.surface,
      }}>
        {[['TIME','76px 14px'],['SYMBOL','76px 14px'],['SCORE','200px 14px'],['ACTION','76px 14px'],['REASON','1fr 14px 0']].map(([h]) => (
          <span key={h} style={{ padding: '0 14px', color: TC_COLORS.textMuted, fontSize: 9, fontFamily: TC_FONTS.mono, letterSpacing: '0.1em', textTransform: 'uppercase' }}>{h}</span>
        ))}
      </div>

      {/* Feed */}
      <div ref={feedRef} style={{ flex: 1, overflowY: 'auto' }}>
        {filtered.length === 0
          ? <TCEmpty message={`No ${filter} signals in feed`}/>
          : filtered.map((sig, i) => (
            <div key={sig.id} style={{
              transition: 'background 0.6s',
              background: highlight === sig.id ? (sig.action === 'BUY' ? 'rgba(0,255,136,0.06)' : sig.action === 'SELL' ? 'rgba(255,68,68,0.06)' : 'transparent') : 'transparent',
            }}>
              <SignalRow signal={sig}/>
            </div>
          ))
        }
      </div>
    </div>
  );
};

Object.assign(window, { SignalPage });
