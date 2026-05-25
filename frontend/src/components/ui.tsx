import React, { CSSProperties } from 'react'
import { TC } from '../theme'

// ── Card ────────────────────────────────────────────────────────────────────
interface CardProps { children: React.ReactNode; style?: CSSProperties; glow?: boolean; glowColor?: string }
export const TCCard = ({ children, style, glow, glowColor }: CardProps) => {
  const gc = glowColor ?? TC.accent
  return (
    <div style={{
      background: TC.surface,
      border: `1px solid ${glow ? gc + '44' : TC.border}`,
      borderRadius: 8,
      boxShadow: glow ? `0 0 0 1px ${gc}22, 0 0 24px ${gc}18` : 'none',
      overflow: 'hidden',
      ...style,
    }}>
      {children}
    </div>
  )
}

// ── Badge ───────────────────────────────────────────────────────────────────
type BadgeVariant = 'default' | 'buy' | 'sell' | 'neutral' | 'paper' | 'live' | 'accent'
const BADGE_MAP: Record<BadgeVariant, { bg: string; color: string }> = {
  default: { bg: 'rgba(255,255,255,0.08)', color: TC.textMid },
  buy:     { bg: TC.greenDim,             color: TC.green    },
  sell:    { bg: TC.redDim,               color: TC.red      },
  neutral: { bg: 'rgba(255,255,255,0.06)', color: TC.textMid },
  paper:   { bg: TC.yellowDim,            color: TC.yellow   },
  live:    { bg: TC.redDim,               color: TC.red      },
  accent:  { bg: TC.accentDim,            color: TC.accent   },
}
export const TCBadge = ({ children, variant = 'default' }: { children: React.ReactNode; variant?: BadgeVariant }) => {
  const c = BADGE_MAP[variant]
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      padding: '2px 7px', borderRadius: 4,
      fontSize: 10, fontWeight: 700, letterSpacing: '0.07em',
      fontFamily: TC.fontMono, textTransform: 'uppercase',
      background: c.bg, color: c.color, whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  )
}

// ── Status Dot ──────────────────────────────────────────────────────────────
export const TCStatusDot = ({ ok, label }: { ok: boolean; label: string }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
    <div style={{
      width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
      background: ok ? TC.green : TC.red,
      boxShadow: `0 0 7px ${ok ? TC.green : TC.red}`,
    }}/>
    <span style={{ color: TC.textMuted, fontSize: 11, fontFamily: TC.fontMono }}>{label}</span>
  </div>
)

// ── Section Header ──────────────────────────────────────────────────────────
export const TCSectionHeader = ({ title, right }: { title: string; right?: React.ReactNode }) => (
  <div style={{
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '10px 16px', borderBottom: `1px solid ${TC.border}`,
  }}>
    <span style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
      {title}
    </span>
    <div>{right}</div>
  </div>
)

// ── Empty State ─────────────────────────────────────────────────────────────
export const TCEmpty = ({ message = 'No data' }: { message?: string }) => (
  <div style={{ padding: '32px 20px', textAlign: 'center', color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 11 }}>
    <div style={{ marginBottom: 6, opacity: 0.35, letterSpacing: '0.2em' }}>· · ·</div>
    {message}
  </div>
)

// ── Table ───────────────────────────────────────────────────────────────────
export interface ColDef<T> {
  key: keyof T & string
  label: string
  right?: boolean
  mono?: boolean
  render?: (value: T[keyof T], row: T) => React.ReactNode
}
interface TableProps<T> { columns: ColDef<T>[]; rows: T[]; emptyMsg?: string }
export function TCTable<T>({ columns, rows, emptyMsg }: TableProps<T>) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${TC.border}` }}>
            {columns.map(col => (
              <th key={col.key} style={{
                padding: '7px 14px', textAlign: col.right ? 'right' : 'left',
                color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono,
                letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 500,
              }}>{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0
            ? <tr><td colSpan={columns.length}><TCEmpty message={emptyMsg ?? 'No data'}/></td></tr>
            : rows.map((row, i) => (
              <tr key={(row as Record<string, unknown>).id != null ? String((row as Record<string, unknown>).id) : i}
                style={{ borderBottom: `1px solid ${TC.border}`, transition: 'background 0.1s' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.025)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                {columns.map(col => (
                  <td key={col.key} style={{
                    padding: '9px 14px', textAlign: col.right ? 'right' : 'left',
                    fontFamily: col.mono ? TC.fontMono : TC.fontUI, fontSize: 12,
                    color: TC.text,
                  }}>
                    {col.render ? col.render(row[col.key], row) : String(row[col.key] ?? '')}
                  </td>
                ))}
              </tr>
            ))
          }
        </tbody>
      </table>
    </div>
  )
}

// ── Slider ──────────────────────────────────────────────────────────────────
interface SliderProps { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number }
export const TCSlider = ({ label, value, onChange, min = 0, max = 1, step = 0.01 }: SliderProps) => {
  const pct = ((value - min) / (max - min)) * 100
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, gap: 8 }}>
        <span style={{ color: TC.textMid, fontSize: 11, fontFamily: TC.fontMono }}>{label}</span>
        <span style={{ color: TC.accent, fontFamily: TC.fontMono, fontSize: 11, fontWeight: 600 }}>{value.toFixed(2)}</span>
      </div>
      <div style={{ position: 'relative', height: 4 }}>
        <div style={{ height: 4, background: TC.surface2, borderRadius: 2 }}/>
        <div style={{
          position: 'absolute', left: 0, top: 0, height: 4,
          width: `${pct}%`, background: TC.accent,
          borderRadius: 2, boxShadow: `0 0 6px ${TC.accentGlow}`,
          pointerEvents: 'none',
        }}/>
        <input type="range" min={min} max={max} step={step} value={value}
          onChange={e => onChange(parseFloat(e.target.value))}
          style={{ position: 'absolute', inset: '-6px 0', opacity: 0, cursor: 'pointer', width: '100%', height: 16 }}
        />
      </div>
    </div>
  )
}

// ── Text / Number Input ─────────────────────────────────────────────────────
interface InputProps { label: string; value: string | number; onChange: (v: string | number) => void; type?: string; suffix?: string }
export const TCInput = ({ label, value, onChange, type = 'text', suffix }: InputProps) => (
  <div>
    <div style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono, letterSpacing: '0.08em', marginBottom: 5, textTransform: 'uppercase' }}>{label}</div>
    <div style={{ position: 'relative' }}>
      <input
        type={type} value={value}
        onChange={e => onChange(type === 'number' ? parseFloat(e.target.value) || 0 : e.target.value)}
        style={{
          width: '100%', padding: '7px 10px', boxSizing: 'border-box',
          background: TC.surface2, border: `1px solid ${TC.border}`,
          borderRadius: 5, color: type === 'number' ? TC.accent : TC.text,
          fontFamily: TC.fontMono, fontSize: 12, outline: 'none',
          transition: 'border-color 0.15s',
        }}
        onFocus={e => (e.target.style.borderColor = TC.accent + '66')}
        onBlur={e => (e.target.style.borderColor = TC.border)}
      />
      {suffix && (
        <span style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono, pointerEvents: 'none' }}>
          {suffix}
        </span>
      )}
    </div>
  </div>
)

// ── Select ──────────────────────────────────────────────────────────────────
interface SelectProps { label: string; value: string; onChange: (v: string) => void; options: string[] }
export const TCSelect = ({ label, value, onChange, options }: SelectProps) => (
  <div>
    <div style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono, letterSpacing: '0.08em', marginBottom: 5, textTransform: 'uppercase' }}>{label}</div>
    <select
      value={value} onChange={e => onChange(e.target.value)}
      style={{
        width: '100%', padding: '7px 10px', boxSizing: 'border-box',
        background: TC.surface2, border: `1px solid ${TC.border}`,
        borderRadius: 5, color: TC.text, fontFamily: TC.fontMono, fontSize: 12,
        outline: 'none', cursor: 'pointer', appearance: 'none',
      }}
    >
      {options.map(o => <option key={o} value={o} style={{ background: TC.surface2 }}>{o}</option>)}
    </select>
  </div>
)

// ── SVG Icons ───────────────────────────────────────────────────────────────
export const TCIcons = {
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
      <circle cx="10" cy="8"  r="2" fill={TC.surface} stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="5"  cy="3"  r="2" fill={TC.surface} stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="12" cy="13" r="2" fill={TC.surface} stroke="currentColor" strokeWidth="1.3"/>
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
  News: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="1.5" y="2" width="13" height="12" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
      <line x1="4" y1="5.5" x2="12" y2="5.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      <line x1="4" y1="8" x2="12" y2="8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      <line x1="4" y1="10.5" x2="9" y2="10.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  ),
  Social: () => (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="6" r="2.5" stroke="currentColor" strokeWidth="1.4"/>
      <circle cx="2.5" cy="11" r="1.8" stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="13.5" cy="11" r="1.8" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M5.5 13.5C5.5 11.5 10.5 11.5 10.5 13.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  ),
}

// ── Mode Toggle ─────────────────────────────────────────────────────────────
interface ModeToggleProps { mode: string; onChange: (m: string) => void }
const ModeToggle = ({ mode, onChange }: ModeToggleProps) => {
  const [open, setOpen] = React.useState(false)
  const isLive = mode === 'live'

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(o => !o)}
        title="Switch trading mode"
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '4px 10px', borderRadius: 5, cursor: 'pointer',
          border: `1px solid ${isLive ? TC.red : TC.yellow}`,
          background: isLive ? TC.redDim : TC.yellowDim,
          color: isLive ? TC.red : TC.yellow,
          fontFamily: TC.fontMono, fontSize: 11, fontWeight: 700,
          letterSpacing: '0.07em', transition: 'all 0.15s',
        }}
      >
        {mode.toUpperCase()}
        <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor">
          <path d={open ? 'M0 6L4 2L8 6' : 'M0 2L4 6L8 2'}/>
        </svg>
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: '110%', right: 0, zIndex: 300,
          background: TC.surface2, border: `1px solid ${TC.borderHi}`,
          borderRadius: 7, overflow: 'hidden', minWidth: 160,
          boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
        }}>
          <div style={{ padding: '8px 12px 6px', color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            Trading Mode
          </div>
          {(['paper', 'live'] as const).map(m => (
            <button key={m} onClick={() => { onChange(m); setOpen(false) }} style={{
              width: '100%', padding: '9px 14px', display: 'flex', alignItems: 'center', gap: 10,
              border: 'none', cursor: 'pointer', textAlign: 'left',
              background: mode === m ? (m === 'live' ? TC.redDim : TC.yellowDim) : 'transparent',
              color: mode === m ? (m === 'live' ? TC.red : TC.yellow) : TC.textMid,
              fontFamily: TC.fontMono, fontSize: 12, fontWeight: mode === m ? 700 : 400,
              transition: 'background 0.1s',
            }}>
              <div style={{ width: 7, height: 7, borderRadius: '50%', background: m === 'live' ? TC.red : TC.yellow, boxShadow: mode === m ? `0 0 6px ${m === 'live' ? TC.red : TC.yellow}` : 'none' }}/>
              {m.toUpperCase()}
              {m === 'live' && <span style={{ marginLeft: 'auto', fontSize: 9, color: TC.red, opacity: 0.7 }}>REAL MONEY</span>}
              {mode === m && <span style={{ marginLeft: m === 'paper' ? 'auto' : 0 }}>✓</span>}
            </button>
          ))}
          <div style={{ padding: '6px 12px 8px', borderTop: `1px solid ${TC.border}` }}>
            <span style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono }}>Persisted to DB</span>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Navbar ──────────────────────────────────────────────────────────────────
interface NavbarProps {
  mode: string
  onModeChange: (m: string) => void
  killSwitch: boolean
  setKillSwitch: (v: boolean) => void
  wsOk: boolean
  dbOk: boolean
  strategyName: string
}
export const TCNavbar = ({ mode, onModeChange, killSwitch, setKillSwitch, wsOk, dbOk, strategyName }: NavbarProps) => {
  const [ksHover, setKsHover] = React.useState(false)
  return (
    <nav style={{
      height: 52, flexShrink: 0, zIndex: 200,
      background: TC.surface,
      borderBottom: `1px solid ${TC.border}`,
      display: 'flex', alignItems: 'center', padding: '0 20px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexShrink: 0 }}>
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
          <path d="M11 2L2 6.5l9 4.5 9-4.5L11 2Z" fill={TC.accent} opacity="0.95"/>
          <path d="M2 15.5l9 4.5 9-4.5" stroke={TC.accent} strokeWidth="1.8" fill="none"/>
          <path d="M2 11l9 4.5 9-4.5" stroke={TC.accent} strokeWidth="1.8" fill="none" opacity="0.45"/>
        </svg>
        <span style={{ color: TC.accent, fontFamily: TC.fontMono, fontWeight: 700, fontSize: 14, letterSpacing: '0.14em' }}>
          TRADECORE
        </span>
      </div>

      <div style={{ width: 1, height: 22, background: TC.border, margin: '0 20px' }}/>

      <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10 }}>
        <span style={{ color: TC.text, fontFamily: TC.fontUI, fontSize: 13, fontWeight: 500 }}>
          {strategyName || 'No Active Strategy'}
        </span>
        <ModeToggle mode={mode} onChange={onModeChange}/>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexShrink: 0 }}>
        <TCStatusDot ok={wsOk} label="WS"/>
        <TCStatusDot ok={dbOk} label="DB"/>
        <div style={{ width: 1, height: 22, background: TC.border }}/>
        <button
          onClick={() => setKillSwitch(!killSwitch)}
          onMouseEnter={() => setKsHover(true)}
          onMouseLeave={() => setKsHover(false)}
          style={{
            display: 'flex', alignItems: 'center', gap: 7,
            padding: '6px 13px', borderRadius: 6, cursor: 'pointer',
            border: `1px solid ${killSwitch ? TC.red : ksHover ? 'rgba(255,68,68,0.5)' : 'rgba(255,68,68,0.25)'}`,
            background: killSwitch ? 'rgba(255,68,68,0.18)' : ksHover ? 'rgba(255,68,68,0.08)' : 'transparent',
            color: TC.red, fontFamily: TC.fontMono, fontSize: 10.5, fontWeight: 700,
            letterSpacing: '0.06em', textTransform: 'uppercase', transition: 'all 0.15s',
          }}
        >
          <TCIcons.Power/>
          {killSwitch ? 'KILL ACTIVE' : 'Kill Switch'}
        </button>
      </div>
    </nav>
  )
}

// ── Sidebar ─────────────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id: '/',         label: 'Dashboard',        Icon: TCIcons.Dashboard },
  { id: '/chart',    label: 'Chart View',        Icon: TCIcons.Chart     },
  { id: '/strategy', label: 'Strategy Builder',  Icon: TCIcons.Strategy  },
  { id: '/backtest', label: 'Backtest',           Icon: TCIcons.Backtest  },
  { id: '/signals',  label: 'Signal Monitor',    Icon: TCIcons.Signals   },
  { id: '/news',     label: 'News',              Icon: TCIcons.News      },
  { id: '/social',   label: 'Social',            Icon: TCIcons.Social    },
]

interface SidebarProps {
  activePath: string
  navigate: (p: string) => void
  workspace: 'crypto' | 'stock'
  onWorkspaceChange: (w: 'crypto' | 'stock') => void
}

export const TCSidebar = ({ activePath, navigate, workspace, onWorkspaceChange }: SidebarProps) => (
  <aside style={{
    width: 210, flexShrink: 0,
    background: TC.surface,
    borderRight: `1px solid ${TC.border}`,
    display: 'flex', flexDirection: 'column',
  }}>
    {/* Workspace switcher */}
    <div style={{
      display: 'flex', margin: '10px 10px 6px',
      background: TC.surface2, borderRadius: 6, padding: 3,
      border: `1px solid ${TC.border}`,
    }}>
      {(['crypto', 'stock'] as const).map(w => (
        <button key={w} onClick={() => onWorkspaceChange(w)} style={{
          flex: 1, padding: '6px 0', border: 'none', cursor: 'pointer', borderRadius: 4,
          background: workspace === w ? TC.surface3 : 'transparent',
          color: workspace === w ? TC.text : TC.textMuted,
          fontFamily: TC.fontMono, fontSize: 11, fontWeight: workspace === w ? 700 : 400,
          transition: 'all 0.12s',
          boxShadow: workspace === w ? `0 0 0 1px ${TC.border}` : 'none',
        }}>
          {w === 'crypto' ? '₿ Crypto' : '📈 Stocks'}
        </button>
      ))}
    </div>

    <div style={{ width: 'auto', margin: '0 10px 8px', height: 1, background: TC.border }}/>

    {/* Nav items */}
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 2, padding: '2px 0' }}>
      {NAV_ITEMS.map(({ id, label, Icon }) => {
        const on = activePath === id
        return (
          <button key={id} onClick={() => navigate(id)} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '10px 18px', border: 'none', cursor: 'pointer', width: '100%', textAlign: 'left',
            background: on ? 'rgba(0,212,255,0.07)' : 'transparent',
            color: on ? TC.accent : TC.textMid,
            fontFamily: TC.fontUI, fontSize: 12.5, fontWeight: on ? 600 : 400,
            borderLeft: `2px solid ${on ? TC.accent : 'transparent'}`,
            transition: 'all 0.12s',
          }}>
            <Icon/>{label}
          </button>
        )
      })}
    </div>
  </aside>
)

// ── Kill Banner ─────────────────────────────────────────────────────────────
export const TCKillBanner = () => (
  <div style={{
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
    padding: '7px 24px', background: 'rgba(255,68,68,0.1)',
    borderBottom: '1px solid rgba(255,68,68,0.35)',
    animation: 'tcPulse 1.8s ease-in-out infinite',
  }}>
    <TCIcons.Warn/>
    <span style={{ color: TC.red, fontFamily: TC.fontMono, fontSize: 11, fontWeight: 700, letterSpacing: '0.1em' }}>
      KILL SWITCH ACTIVE — ALL TRADING HALTED — ORDERS REJECTED
    </span>
    <TCIcons.Warn/>
  </div>
)
