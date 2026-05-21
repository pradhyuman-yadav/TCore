// TradeCore — Shared UI components, Navbar, Sidebar
// Exports to window for cross-script access

const { useState: useStateUI } = React;

// ─── SVG Icons ────────────────────────────────────────────────────────────
const TCIcons = {
  Dashboard: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="1" y="1" width="6" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="9" y="1" width="6" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="1" y="9" width="6" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.4"/>
      <rect x="9" y="9" width="6" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.4"/>
    </svg>
  ),
  Chart: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <polyline points="1,12 4,7 7,9 11,3 15,5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      <line x1="1" y1="15" x2="15" y2="15" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" opacity="0.5"/>
    </svg>
  ),
  Strategy: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <line x1="1" y1="8" x2="15" y2="8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      <line x1="1" y1="3" x2="15" y2="3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      <line x1="1" y1="13" x2="15" y2="13" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      <circle cx="10" cy="8"  r="2" fill={TC_COLORS.surface} stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="5"  cy="3"  r="2" fill={TC_COLORS.surface} stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="12" cy="13" r="2" fill={TC_COLORS.surface} stroke="currentColor" strokeWidth="1.3"/>
    </svg>
  ),
  Backtest: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.4"/>
      <polyline points="8,4.5 8,8 11,10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  Signals: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <polyline points="1,8 3.5,3.5 6,11 9,5 11.5,9.5 15,7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  Power: () => (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
      <path d="M6.5 1.5v4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      <path d="M4 3A5 5 0 1 0 9 3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" fill="none"/>
    </svg>
  ),
  Warn: () => (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <path d="M7 1L13.5 13H0.5L7 1Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
      <line x1="7" y1="5.5" x2="7" y2="9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
      <circle cx="7" cy="11" r="0.7" fill="currentColor"/>
    </svg>
  ),
};

// ─── Card ─────────────────────────────────────────────────────────────────
const TCCard = ({ children, style, glow, glowColor }) => {
  const gc = glowColor || TC_COLORS.accent;
  return (
    <div style={{
      background: TC_COLORS.surface,
      border: `1px solid ${glow ? gc + '44' : TC_COLORS.border}`,
      borderRadius: 8,
      boxShadow: glow ? `0 0 0 1px ${gc}22, 0 0 24px ${gc}18` : 'none',
      overflow: 'hidden',
      ...style,
    }}>
      {children}
    </div>
  );
};

// ─── Badge ────────────────────────────────────────────────────────────────
const TCBadge = ({ children, variant = 'default' }) => {
  const map = {
    default:  { bg: 'rgba(255,255,255,0.08)', color: TC_COLORS.textMid },
    buy:      { bg: TC_COLORS.greenDim,       color: TC_COLORS.green   },
    sell:     { bg: TC_COLORS.redDim,         color: TC_COLORS.red     },
    neutral:  { bg: 'rgba(255,255,255,0.06)', color: TC_COLORS.textMid },
    paper:    { bg: TC_COLORS.yellowDim,      color: TC_COLORS.yellow  },
    live:     { bg: TC_COLORS.redDim,         color: TC_COLORS.red     },
    accent:   { bg: TC_COLORS.accentDim,      color: TC_COLORS.accent  },
  };
  const c = map[variant] || map.default;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      padding: '2px 7px', borderRadius: 4,
      fontSize: 10, fontWeight: 700, letterSpacing: '0.07em',
      fontFamily: TC_FONTS.mono, textTransform: 'uppercase',
      background: c.bg, color: c.color, whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  );
};

// ─── Status Dot ───────────────────────────────────────────────────────────
const TCStatusDot = ({ ok, label }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
    <div style={{
      width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
      background: ok ? TC_COLORS.green : TC_COLORS.red,
      boxShadow: `0 0 7px ${ok ? TC_COLORS.green : TC_COLORS.red}`,
    }}/>
    <span style={{ color: TC_COLORS.textMuted, fontSize: 11, fontFamily: TC_FONTS.mono }}>{label}</span>
  </div>
);

// ─── Section Header ───────────────────────────────────────────────────────
const TCSectionHeader = ({ title, right }) => (
  <div style={{
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '10px 16px', borderBottom: `1px solid ${TC_COLORS.border}`,
  }}>
    <span style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
      {title}
    </span>
    <div>{right}</div>
  </div>
);

// ─── Empty State ──────────────────────────────────────────────────────────
const TCEmpty = ({ message = 'No data' }) => (
  <div style={{ padding: '32px 20px', textAlign: 'center', color: TC_COLORS.textMuted, fontFamily: TC_FONTS.mono, fontSize: 11 }}>
    <div style={{ marginBottom: 6, opacity: 0.35, letterSpacing: '0.2em' }}>· · ·</div>
    {message}
  </div>
);

// ─── Data Table ───────────────────────────────────────────────────────────
const TCTable = ({ columns, rows, emptyMsg }) => (
  <div style={{ overflowX: 'auto' }}>
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ borderBottom: `1px solid ${TC_COLORS.border}` }}>
          {columns.map(col => (
            <th key={col.key} style={{
              padding: '7px 14px', textAlign: col.right ? 'right' : 'left',
              color: TC_COLORS.textMuted, fontSize: 9, fontFamily: TC_FONTS.mono,
              letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 500,
            }}>{col.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.length === 0
          ? <tr><td colSpan={columns.length}><TCEmpty message={emptyMsg || 'No data'}/></td></tr>
          : rows.map((row, i) => (
            <tr key={row.id ?? i}
              style={{ borderBottom: `1px solid ${TC_COLORS.border}`, transition: 'background 0.1s' }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.025)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              {columns.map(col => (
                <td key={col.key} style={{
                  padding: '9px 14px', textAlign: col.right ? 'right' : 'left',
                  fontFamily: col.mono ? TC_FONTS.mono : TC_FONTS.ui, fontSize: 12,
                  color: TC_COLORS.text,
                }}>
                  {col.render ? col.render(row[col.key], row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))
        }
      </tbody>
    </table>
  </div>
);

// ─── Slider Control ───────────────────────────────────────────────────────
const TCSlider = ({ label, value, onChange, min = 0, max = 1, step = 0.01 }) => {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, gap: 8 }}>
        <span style={{ color: TC_COLORS.textMid, fontSize: 11, fontFamily: TC_FONTS.mono }}>{label}</span>
        <span style={{ color: TC_COLORS.accent, fontFamily: TC_FONTS.mono, fontSize: 11, fontWeight: 600 }}>{value.toFixed(2)}</span>
      </div>
      <div style={{ position: 'relative', height: 4 }}>
        <div style={{ height: 4, background: TC_COLORS.surface2, borderRadius: 2 }}/>
        <div style={{
          position: 'absolute', left: 0, top: 0, height: 4,
          width: `${pct}%`, background: TC_COLORS.accent,
          borderRadius: 2, boxShadow: `0 0 6px ${TC_COLORS.accentGlow}`,
          pointerEvents: 'none',
        }}/>
        <input type="range" min={min} max={max} step={step} value={value}
          onChange={e => onChange(parseFloat(e.target.value))}
          style={{ position: 'absolute', inset: '-6px 0', opacity: 0, cursor: 'pointer', width: '100%', height: 16 }}
        />
      </div>
    </div>
  );
};

// ─── Top Navbar ───────────────────────────────────────────────────────────
const TCNavbar = ({ mode, killSwitch, setKillSwitch, wsOk, dbOk, strategyName }) => {
  const [ksHover, setKsHover] = useStateUI(false);
  return (
    <nav style={{
      height: 52, flexShrink: 0, zIndex: 200,
      background: TC_COLORS.surface,
      borderBottom: `1px solid ${TC_COLORS.border}`,
      display: 'flex', alignItems: 'center', padding: '0 20px', gap: 0,
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexShrink: 0 }}>
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
          <path d="M11 2L2 6.5l9 4.5 9-4.5L11 2Z" fill={TC_COLORS.accent} opacity="0.95"/>
          <path d="M2 15.5l9 4.5 9-4.5" stroke={TC_COLORS.accent} strokeWidth="1.8" fill="none"/>
          <path d="M2 11l9 4.5 9-4.5" stroke={TC_COLORS.accent} strokeWidth="1.8" fill="none" opacity="0.45"/>
        </svg>
        <span style={{ color: TC_COLORS.accent, fontFamily: TC_FONTS.mono, fontWeight: 700, fontSize: 14, letterSpacing: '0.14em' }}>
          TRADECORE
        </span>
      </div>

      <div style={{ width: 1, height: 22, background: TC_COLORS.border, margin: '0 20px' }}/>

      {/* Center: strategy + mode */}
      <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10 }}>
        <span style={{ color: TC_COLORS.text, fontFamily: TC_FONTS.ui, fontSize: 13, fontWeight: 500 }}>
          {strategyName}
        </span>
        <TCBadge variant={mode === 'PAPER' ? 'paper' : 'live'}>{mode}</TCBadge>
      </div>

      {/* Right: status + kill switch */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexShrink: 0 }}>
        <TCStatusDot ok={wsOk}  label="WS"/>
        <TCStatusDot ok={dbOk}  label="DB"/>
        <div style={{ width: 1, height: 22, background: TC_COLORS.border }}/>
        <button
          onClick={() => setKillSwitch(!killSwitch)}
          onMouseEnter={() => setKsHover(true)}
          onMouseLeave={() => setKsHover(false)}
          style={{
            display: 'flex', alignItems: 'center', gap: 7,
            padding: '6px 13px', borderRadius: 6, cursor: 'pointer',
            border: `1px solid ${killSwitch ? TC_COLORS.red : ksHover ? 'rgba(255,68,68,0.5)' : 'rgba(255,68,68,0.25)'}`,
            background: killSwitch ? 'rgba(255,68,68,0.18)' : ksHover ? 'rgba(255,68,68,0.08)' : 'transparent',
            color: TC_COLORS.red, fontFamily: TC_FONTS.mono, fontSize: 10.5, fontWeight: 700,
            letterSpacing: '0.06em', textTransform: 'uppercase', transition: 'all 0.15s',
          }}
        >
          <TCIcons.Power/>
          {killSwitch ? 'KILL ACTIVE' : 'Kill Switch'}
        </button>
      </div>
    </nav>
  );
};

// ─── Sidebar ──────────────────────────────────────────────────────────────
const TC_NAV = [
  { id: 'dashboard', label: 'Dashboard',        Icon: TCIcons.Dashboard },
  { id: 'chart',     label: 'Chart View',        Icon: TCIcons.Chart     },
  { id: 'strategy',  label: 'Strategy Builder',  Icon: TCIcons.Strategy  },
  { id: 'backtest',  label: 'Backtest',           Icon: TCIcons.Backtest  },
  { id: 'signals',   label: 'Signal Monitor',    Icon: TCIcons.Signals   },
];

const TCSidebar = ({ active, setActive }) => (
  <aside style={{
    width: 210, flexShrink: 0,
    background: TC_COLORS.surface,
    borderRight: `1px solid ${TC_COLORS.border}`,
    padding: '10px 0', display: 'flex', flexDirection: 'column', gap: 2,
  }}>
    {TC_NAV.map(({ id, label, Icon }) => {
      const on = active === id;
      return (
        <button key={id} onClick={() => setActive(id)} style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '10px 18px', border: 'none', cursor: 'pointer', width: '100%', textAlign: 'left',
          background: on ? 'rgba(0,212,255,0.07)' : 'transparent',
          color: on ? TC_COLORS.accent : TC_COLORS.textMid,
          fontFamily: TC_FONTS.ui, fontSize: 12.5, fontWeight: on ? 600 : 400,
          borderLeft: `2px solid ${on ? TC_COLORS.accent : 'transparent'}`,
          transition: 'all 0.12s',
        }}>
          <Icon/>{label}
        </button>
      );
    })}
  </aside>
);

// ─── Kill Switch Banner ───────────────────────────────────────────────────
const TCKillBanner = () => (
  <div style={{
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
    padding: '7px 24px', background: 'rgba(255,68,68,0.1)',
    borderBottom: `1px solid rgba(255,68,68,0.35)`,
    animation: 'tcPulse 1.8s ease-in-out infinite',
  }}>
    <TCIcons.Warn/>
    <span style={{ color: TC_COLORS.red, fontFamily: TC_FONTS.mono, fontSize: 11, fontWeight: 700, letterSpacing: '0.1em' }}>
      ⚠ KILL SWITCH ACTIVE — ALL TRADING HALTED — ORDERS REJECTED ⚠
    </span>
    <TCIcons.Warn/>
  </div>
);

Object.assign(window, {
  TCIcons, TCCard, TCBadge, TCStatusDot, TCSectionHeader,
  TCEmpty, TCTable, TCSlider, TCNavbar, TCSidebar, TCKillBanner,
});
