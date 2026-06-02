import { useState, useEffect, useRef } from 'react'
import { api } from '../api'
import { useStore, SysEvent } from '../store'
import { TC } from '../theme'
import { TCEmpty } from '../components/ui'

const CATEGORIES = ['ALL', 'decision', 'trade', 'risk', 'agent', 'regime', 'control', 'job', 'data', 'error'] as const
type Cat = typeof CATEGORIES[number]

// Per-category accent colour for the badge / left border.
const CAT_COLOR: Record<string, string> = {
  decision: TC.accent,
  trade:    TC.green,
  risk:     TC.red,
  agent:    '#b48cff',
  regime:   TC.yellow,
  control:  '#ff9d3c',
  job:      TC.textMid,
  data:     '#4aa3ff',
  error:    TC.red,
}

function catColor(c: string) { return CAT_COLOR[c] ?? TC.textMid }

function levelColor(level: string) {
  return level === 'error' ? TC.red : level === 'warn' ? TC.yellow : TC.textMid
}

function fmtTime(ts: string) {
  const d = new Date(ts)
  return isNaN(d.getTime()) ? '—' : d.toTimeString().slice(0, 8)
}

function EventRowView({ ev, highlight }: { ev: SysEvent; highlight: boolean }) {
  const col = catColor(ev.category)
  const hasPayload = ev.payload && Object.keys(ev.payload).length > 0
  const [open, setOpen] = useState(false)
  return (
    <div
      style={{
        borderBottom: `1px solid ${TC.border}`,
        borderLeft: `2px solid ${col}`,
        background: highlight ? col + '12' : 'transparent',
        transition: 'background 0.6s',
        cursor: hasPayload ? 'pointer' : 'default',
      }}
      onClick={() => hasPayload && setOpen(o => !o)}
      onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.025)')}
      onMouseLeave={e => (e.currentTarget.style.background = highlight ? col + '12' : 'transparent')}
    >
      <div style={{ display: 'grid', gridTemplateColumns: '76px 92px 110px 1fr', alignItems: 'center' }}>
        <span style={{ padding: '8px 14px', color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 11 }}>
          {fmtTime(ev.ts)}
        </span>
        <span style={{
          padding: '8px 0', margin: '0 8px', textAlign: 'center',
          color: col, fontFamily: TC.fontMono, fontSize: 9.5, fontWeight: 700,
          letterSpacing: '0.08em', textTransform: 'uppercase',
          border: `1px solid ${col}55`, borderRadius: 4, background: col + '12',
        }}>
          {ev.category}
        </span>
        <span style={{ padding: '8px 14px', color: TC.text, fontFamily: TC.fontMono, fontSize: 11.5 }}>
          {ev.symbol ?? '—'}
        </span>
        <span style={{
          padding: '8px 14px 8px 0', color: levelColor(ev.level),
          fontFamily: TC.fontUI, fontSize: 12, overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: open ? 'normal' : 'nowrap',
        }}>
          {ev.message}
        </span>
      </div>
      {open && hasPayload && (
        <pre style={{
          margin: 0, padding: '6px 14px 10px 92px', color: TC.textMuted,
          fontFamily: TC.fontMono, fontSize: 10.5, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
        }}>
          {JSON.stringify(ev.payload, null, 2)}
        </pre>
      )}
    </div>
  )
}

export default function Activity() {
  const { events, wsStatus, setEvents } = useStore()
  const [cat, setCat] = useState<Cat>('ALL')
  const [paused, setPaused] = useState(false)
  const [highlightTs, setHighlightTs] = useState<string | null>(null)
  const prevLen = useRef(0)
  const loaded = useRef(false)

  // Load history once on mount.
  useEffect(() => {
    if (loaded.current) return
    loaded.current = true
    api.getEvents({ limit: 300 })
      .then(rows => setEvents(rows.map(r => ({
        ts: r.ts, category: r.category, level: r.level,
        symbol: r.symbol, message: r.message, payload: r.payload,
      }))))
      .catch(() => {})
  }, [setEvents])

  // Highlight newest event arriving via WS.
  useEffect(() => {
    if (events.length > prevLen.current && events[0]) {
      setHighlightTs(events[0].ts)
      setTimeout(() => setHighlightTs(null), 800)
    }
    prevLen.current = events.length
  }, [events.length])

  const filtered = cat === 'ALL' ? events : events.filter(e => e.category === cat)
  const shown = paused ? filtered.slice(0, prevLen.current) : filtered
  const wsOk = wsStatus === 'open'

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
        <span style={{ color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 11 }}>ws://{window.location.host}/ws/events</span>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={() => setPaused(p => !p)} style={{
            padding: '3px 12px', borderRadius: 4, cursor: 'pointer',
            border: `1px solid ${paused ? TC.yellow : TC.border}`,
            background: paused ? TC.yellow + '20' : 'transparent',
            color: paused ? TC.yellow : TC.textMid,
            fontFamily: TC.fontMono, fontSize: 10, fontWeight: 700,
          }}>{paused ? '▶ RESUME' : '⏸ PAUSE'}</button>
          <span style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono }}>
            {events.length} events
          </span>
        </div>
      </div>

      {/* Category filters */}
      <div style={{
        padding: '10px 18px', flexShrink: 0, borderBottom: `1px solid ${TC.border}`,
        display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap',
      }}>
        {CATEGORIES.map(c => {
          const on = cat === c
          const fc = c === 'ALL' ? TC.accent : catColor(c)
          return (
            <button key={c} onClick={() => setCat(c)} style={{
              padding: '4px 12px', borderRadius: 4, cursor: 'pointer',
              border: `1px solid ${on ? fc : TC.border}`,
              background: on ? fc + '20' : 'transparent',
              color: on ? fc : TC.textMid,
              fontFamily: TC.fontMono, fontSize: 10.5, fontWeight: 700,
              letterSpacing: '0.05em', textTransform: 'uppercase', transition: 'all 0.12s',
            }}>{c}</button>
          )
        })}
        <span style={{ marginLeft: 'auto', color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono }}>
          {shown.length} shown
        </span>
      </div>

      {/* Column headers */}
      <div style={{
        display: 'grid', gridTemplateColumns: '76px 92px 110px 1fr',
        padding: '7px 0', flexShrink: 0,
        borderBottom: `1px solid ${TC.border}`, background: TC.surface,
      }}>
        {['TIME', 'CATEGORY', 'SYMBOL', 'EVENT'].map(h => (
          <span key={h} style={{ padding: '0 14px', color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono, letterSpacing: '0.1em' }}>{h}</span>
        ))}
      </div>

      {/* Feed */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {shown.length === 0
          ? <TCEmpty message="No events yet — system activity will stream here live"/>
          : shown.map((ev, i) => (
            <EventRowView key={`${ev.ts}|${i}`} ev={ev} highlight={highlightTs === ev.ts}/>
          ))
        }
      </div>
    </div>
  )
}
