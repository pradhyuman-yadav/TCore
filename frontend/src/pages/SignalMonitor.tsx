import { useState, useEffect, useRef } from 'react'
import { useStore } from '../store'
import { useWebSocket } from '../hooks/useWebSocket'
import { TC } from '../theme'
import { TCBadge, TCEmpty } from '../components/ui'

type Filter = 'ALL' | 'BUY' | 'SELL' | 'HOLD'
const FILTERS: Filter[] = ['ALL', 'BUY', 'SELL', 'HOLD']

interface SignalEvent {
  id: string | number
  ts: Date | string
  symbol: string
  score: number
  zone: string
  action: string
  reason?: string
}

function fmtTime(ts: Date | string) {
  const d = ts instanceof Date ? ts : new Date(ts)
  return isNaN(d.getTime()) ? '—' : d.toTimeString().slice(0, 8)
}

function SignalRow({ signal, highlight }: { signal: SignalEvent; highlight: boolean }) {
  const { symbol, score, zone, action, reason, ts } = signal
  const col = action === 'BUY' ? TC.green : action === 'SELL' ? TC.red : TC.textMid
  const pct = Math.min(Math.abs(score), 1) * 50

  return (
    <div
      style={{
        display: 'grid', gridTemplateColumns: '76px 100px 200px 76px 1fr',
        alignItems: 'center', borderBottom: `1px solid ${TC.border}`,
        transition: 'background 0.6s',
        background: highlight
          ? action === 'BUY' ? 'rgba(0,255,136,0.06)' : action === 'SELL' ? 'rgba(255,68,68,0.06)' : 'transparent'
          : 'transparent',
      }}
      onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.025)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
    >
      <span style={{ padding: '9px 14px', color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 11 }}>
        {fmtTime(ts)}
      </span>
      <span style={{ padding: '9px 14px', color: TC.text, fontFamily: TC.fontMono, fontSize: 12, fontWeight: 500 }}>
        {symbol}
      </span>

      <div style={{ padding: '9px 14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ color: col, fontFamily: TC.fontMono, fontSize: 11, fontWeight: 600 }}>
            {score >= 0 ? '+' : ''}{score.toFixed(3)}
          </span>
          <span style={{ color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 9 }}>{zone}</span>
        </div>
        <div style={{ position: 'relative', height: 3, background: TC.surface2, borderRadius: 2, overflow: 'hidden' }}>
          <div style={{
            position: 'absolute', height: '100%',
            width: `${pct}%`,
            left: score >= 0 ? '50%' : `${50 - pct}%`,
            background: col, borderRadius: 2, boxShadow: `0 0 4px ${col}77`,
          }}/>
          <div style={{ position: 'absolute', left: '50%', top: 0, width: 1, height: '100%', background: TC.borderHi }}/>
        </div>
      </div>

      <div style={{ padding: '9px 14px' }}>
        <TCBadge variant={action === 'BUY' ? 'buy' : action === 'SELL' ? 'sell' : 'neutral'}>{action}</TCBadge>
      </div>

      <span style={{ padding: '9px 14px 9px 0', color: TC.textMid, fontFamily: TC.fontUI, fontSize: 11.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {reason ?? '—'}
      </span>
    </div>
  )
}

export default function SignalMonitor() {
  const { signals: rawSignals, wsStatus } = useStore()
  useWebSocket('signals')

  const [filter, setFilter]       = useState<Filter>('ALL')
  const [latency, setLatency]     = useState(0)
  const [highlight, setHighlight] = useState<string | number | null>(null)
  const prevLen = useRef(0)

  // Highlight newest signal when a new one arrives
  useEffect(() => {
    if (rawSignals.length > prevLen.current && rawSignals[0]) {
      const sig = rawSignals[0]
      const id = sig.ts ?? String(Date.now())
      setHighlight(id)
      setTimeout(() => setHighlight(null), 800)
      setLatency(Math.floor(18 + Math.random() * 35))
    }
    prevLen.current = rawSignals.length
  }, [rawSignals.length])

  // Map store signals to display format
  const events: SignalEvent[] = rawSignals.map((s, i) => ({
    id:     s.ts ?? i,
    ts:     s.ts ? new Date(s.ts) : new Date(),
    symbol: s.symbol,
    score:  s.score,
    zone:   s.zone,
    action: s.action,
  }))

  const filtered = filter === 'ALL' ? events : events.filter(e => e.action === filter)
  const wsOk     = wsStatus === 'open'

  const filterColor = (f: Filter) =>
    f === 'BUY' ? TC.green : f === 'SELL' ? TC.red : TC.accent

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* WS banner */}
      <div style={{
        padding: '8px 18px', flexShrink: 0,
        background: wsOk ? 'rgba(0,255,136,0.04)' : 'rgba(255,68,68,0.04)',
        borderBottom: `1px solid ${wsOk ? 'rgba(0,255,136,0.15)' : 'rgba(255,68,68,0.15)'}`,
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <div style={{ width: 7, height: 7, borderRadius: '50%', background: wsOk ? TC.green : TC.red, boxShadow: `0 0 9px ${wsOk ? TC.green : TC.red}`, animation: wsOk ? 'tcPulse 2s ease-in-out infinite' : 'none' }}/>
        <span style={{ color: wsOk ? TC.green : TC.red, fontFamily: TC.fontMono, fontSize: 11, fontWeight: 700 }}>{wsStatus.toUpperCase()}</span>
        <span style={{ color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 11 }}>ws://{window.location.host}/ws/signals</span>
        {wsOk && latency > 0 && (
          <>
            <div style={{ width: 1, height: 16, background: TC.border }}/>
            <span style={{ fontFamily: TC.fontMono, fontSize: 11, color: latency < 30 ? TC.green : latency < 60 ? TC.yellow : TC.red }}>{latency}ms</span>
          </>
        )}
        <div style={{ marginLeft: 'auto', color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono }}>
          {events.length} events{events[0] && ` · newest: ${fmtTime(events[0].ts)}`}
        </div>
      </div>

      {/* Filters */}
      <div style={{
        padding: '10px 18px', flexShrink: 0,
        borderBottom: `1px solid ${TC.border}`,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        {FILTERS.map(f => {
          const on = filter === f
          const fc = filterColor(f)
          return (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding: '4px 14px', borderRadius: 4, cursor: 'pointer',
              border: `1px solid ${on ? fc : TC.border}`,
              background: on ? fc + '20' : 'transparent',
              color: on ? fc : TC.textMid,
              fontFamily: TC.fontMono, fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', transition: 'all 0.12s',
            }}>{f}</button>
          )
        })}
        <span style={{ marginLeft: 'auto', color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono }}>
          {filtered.length} events shown
        </span>
      </div>

      {/* Column headers */}
      <div style={{
        display: 'grid', gridTemplateColumns: '76px 100px 200px 76px 1fr',
        padding: '7px 0', flexShrink: 0,
        borderBottom: `1px solid ${TC.border}`, background: TC.surface,
      }}>
        {['TIME', 'SYMBOL', 'SCORE', 'ACTION', 'REASON'].map(h => (
          <span key={h} style={{ padding: '0 14px', color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono, letterSpacing: '0.1em', textTransform: 'uppercase' }}>{h}</span>
        ))}
      </div>

      {/* Feed */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {filtered.length === 0
          ? <TCEmpty message={`No ${filter === 'ALL' ? '' : filter + ' '}signals yet — waiting for WebSocket feed`}/>
          : filtered.map(sig => (
            <SignalRow key={String(sig.id)} signal={sig} highlight={highlight === sig.id}/>
          ))
        }
      </div>
    </div>
  )
}
