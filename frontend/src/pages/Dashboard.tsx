import { useEffect, useState } from 'react'
import { api, ClaudeHealth, ProxyHealth, HealthStatus, Position, Trade } from '../api'
import { useStore } from '../store'
import { TC } from '../theme'
import { TCCard, TCBadge, TCSectionHeader, TCTable, TCEmpty, ColDef } from '../components/ui'

const SEED_CONFIG: Record<string, { symbols: string[]; exchange: string; tf: string; days: number }> = {
  crypto: { symbols: ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'], exchange: 'binanceus', tf: '1h', days: 90 },
  stock:  { symbols: ['AAPL', 'MSFT', 'GOOGL'],             exchange: 'yfinance_us', tf: '1d', days: 365 },
}

// ── Data Seed Panel ─────────────────────────────────────────────────────────
function DataSeedPanel({ workspace }: { workspace: 'crypto' | 'stock' }) {
  const cfg  = SEED_CONFIG[workspace]
  const [rows, setRows] = useState<Record<string, { count: number; syncing: boolean; result: string }>>({})

  useEffect(() => {
    setRows({})
    cfg.symbols.forEach(sym => {
      api.getOhlcvCount(sym, cfg.exchange).then(r => {
        setRows(prev => ({ ...prev, [sym]: { count: r.count, syncing: false, result: '' } }))
      }).catch(() => {
        setRows(prev => ({ ...prev, [sym]: { count: 0, syncing: false, result: '' } }))
      })
    })
  }, [workspace])

  const sync = async (sym: string) => {
    setRows(prev => ({ ...prev, [sym]: { ...prev[sym], syncing: true, result: '' } }))
    try {
      const r = await api.syncMarket(sym, cfg.exchange, cfg.tf, cfg.days)
      setRows(prev => ({ ...prev, [sym]: { count: r.upserted, syncing: false, result: `✓ ${r.upserted} bars` } }))
    } catch (e: unknown) {
      setRows(prev => ({ ...prev, [sym]: { ...prev[sym], syncing: false, result: `✗ ${e instanceof Error ? e.message : 'failed'}` } }))
    }
  }

  const syncAll = () => cfg.symbols.forEach(sync)
  const anyMissing = cfg.symbols.some(s => (rows[s]?.count ?? 0) === 0)

  return (
    <TCCard>
      <TCSectionHeader title="Market Data" right={
        <button onClick={syncAll} style={{
          padding: '3px 12px', borderRadius: 4, cursor: 'pointer',
          border: `1px solid ${TC.accent}`, background: TC.accentDim,
          color: TC.accent, fontFamily: TC.fontMono, fontSize: 10, fontWeight: 700,
        }}>
          Sync All ({cfg.days}d)
        </button>
      }/>
      {anyMissing && (
        <div style={{ padding: '8px 16px', background: 'rgba(255,204,0,0.05)', borderBottom: `1px solid rgba(255,204,0,0.2)` }}>
          <span style={{ color: TC.yellow, fontFamily: TC.fontMono, fontSize: 10 }}>
            ⚠ Some symbols have no OHLCV data. Sync before running strategy.
          </span>
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)' }}>
        {cfg.symbols.map(sym => {
          const row = rows[sym]
          const hasData = (row?.count ?? 0) > 0
          return (
            <div key={sym} style={{ padding: '12px 16px', borderRight: `1px solid ${TC.border}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <span style={{ fontFamily: TC.fontMono, fontSize: 12, color: TC.text }}>{sym}</span>
                <TCBadge variant={hasData ? 'buy' : 'sell'}>{hasData ? 'OK' : 'EMPTY'}</TCBadge>
              </div>
              <div style={{ color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 10, marginBottom: 8 }}>
                {row === undefined ? '…' : `${row.count.toLocaleString()} bars · ${cfg.tf}`}
              </div>
              <button onClick={() => sync(sym)} disabled={row?.syncing} style={{
                width: '100%', padding: '5px 0', borderRadius: 4, cursor: row?.syncing ? 'not-allowed' : 'pointer',
                border: `1px solid ${TC.border}`, background: 'transparent',
                color: row?.syncing ? TC.textMuted : TC.accent, fontFamily: TC.fontMono, fontSize: 10, fontWeight: 700,
                transition: 'all 0.15s',
              }}>
                {row?.syncing ? '⟳ Syncing…' : `⟳ Sync ${cfg.days}d`}
              </button>
              {row?.result && (
                <div style={{ marginTop: 4, color: row.result.startsWith('✓') ? TC.green : TC.red, fontSize: 9, fontFamily: TC.fontMono }}>
                  {row.result}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </TCCard>
  )
}

// ── Score Gauge ─────────────────────────────────────────────────────────────
function ScoreGauge({ score }: { score: number }) {
  const CX = 100, CY = 90, OR = 68, IR = 52
  const zone  = score > 0.3 ? 'BUY' : score < -0.3 ? 'SELL' : 'NEUTRAL'
  const zoneC = zone === 'BUY' ? TC.green : zone === 'SELL' ? TC.red : TC.textMid

  const P = (deg: number, r: number) => ({
    x: CX + r * Math.sin(deg * Math.PI / 180),
    y: CY - r * Math.cos(deg * Math.PI / 180),
  })
  const arc = (a1: number, a2: number, ri = IR, ro = OR) => {
    const s = P(a1, ro), e = P(a2, ro), si = P(a1, ri), ei = P(a2, ri)
    const lg = a2 - a1 > 180 ? 1 : 0
    const fx = (v: number) => v.toFixed(2)
    return `M${fx(s.x)} ${fx(s.y)} A${ro} ${ro} 0 ${lg} 1 ${fx(e.x)} ${fx(e.y)} L${fx(ei.x)} ${fx(ei.y)} A${ri} ${ri} 0 ${lg} 0 ${fx(si.x)} ${fx(si.y)}Z`
  }

  const needleDeg = Math.max(-90, Math.min(90, score * 90))
  const tip  = P(needleDeg, OR - 4)
  const base = P(needleDeg, 14)

  return (
    <div style={{ textAlign: 'center' }}>
      <svg viewBox="0 0 200 110" style={{ width: '100%', maxWidth: 250, overflow: 'visible', display: 'block', margin: '0 auto' }}>
        <path d={arc(-90, 90)} fill="rgba(255,255,255,0.03)"/>
        <path d={arc(-90, -27)} fill="rgba(255,68,68,0.22)"/>
        <path d={arc(-27, 27)} fill="rgba(255,255,255,0.06)"/>
        <path d={arc(27, 90)} fill="rgba(0,255,136,0.22)"/>
        {[-90, -27, 0, 27, 90].map(a => {
          const t1 = P(a, OR + 3), t2 = P(a, OR + 9)
          return <line key={a} x1={t1.x.toFixed(1)} y1={t1.y.toFixed(1)} x2={t2.x.toFixed(1)} y2={t2.y.toFixed(1)} stroke={TC.border} strokeWidth="1"/>
        })}
        <text x="12"  y="100" textAnchor="middle" fill={TC.red}      fontSize="7.5" fontFamily="monospace" fontWeight="700" letterSpacing="1">SELL</text>
        <text x="100" y="15"  textAnchor="middle" fill={TC.textMuted} fontSize="7.5" fontFamily="monospace" letterSpacing="1">NEUT</text>
        <text x="188" y="100" textAnchor="middle" fill={TC.green}    fontSize="7.5" fontFamily="monospace" fontWeight="700" letterSpacing="1">BUY</text>
        <line x1={CX.toFixed(1)} y1={CY.toFixed(1)} x2={tip.x.toFixed(1)} y2={tip.y.toFixed(1)}
          stroke={zoneC} strokeWidth="6" strokeLinecap="round" opacity="0.08"/>
        <line x1={base.x.toFixed(1)} y1={base.y.toFixed(1)} x2={tip.x.toFixed(1)} y2={tip.y.toFixed(1)}
          stroke={zoneC} strokeWidth="2" strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 3px ${zoneC})` }}/>
        <circle cx={CX} cy={CY} r="5" fill={TC.surface2} stroke={zoneC} strokeWidth="1.5"/>
        <text x={CX} y={CY + 20} textAnchor="middle" fill={zoneC} fontSize="19" fontFamily="monospace" fontWeight="700">
          {score > 0 ? '+' : ''}{score.toFixed(3)}
        </text>
      </svg>
      <div style={{ marginTop: 4 }}>
        <TCBadge variant={zone === 'BUY' ? 'buy' : zone === 'SELL' ? 'sell' : 'neutral'}>{zone} ZONE</TCBadge>
      </div>
    </div>
  )
}

// ── PnL Meter ───────────────────────────────────────────────────────────────
function PnLMeter({ pnl, max = 2000 }: { pnl: number; max?: number }) {
  const pos = pnl >= 0
  const pct = Math.min(Math.abs(pnl) / max, 1)
  const col = pos ? TC.green : TC.red
  return (
    <div style={{ padding: '14px 18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
        <span style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono, letterSpacing: '0.12em', textTransform: 'uppercase' }}>Daily P&amp;L</span>
        <span style={{ color: col, fontFamily: TC.fontMono, fontSize: 22, fontWeight: 700 }}>
          {pos ? '+' : '-'}${Math.abs(pnl).toFixed(2)}
        </span>
      </div>
      <div style={{ position: 'relative', height: 6, background: TC.surface2, borderRadius: 3, overflow: 'hidden' }}>
        <div style={{
          position: 'absolute', height: '100%',
          width: `${pct * 50}%`,
          left: pos ? '50%' : `${50 - pct * 50}%`,
          background: col, borderRadius: 3,
          boxShadow: `0 0 8px ${col}`,
          transition: 'all 0.5s ease',
        }}/>
        <div style={{ position: 'absolute', left: '50%', top: 0, width: 1, height: '100%', background: TC.borderHi }}/>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5 }}>
        <span style={{ color: TC.red,      fontSize: 9, fontFamily: TC.fontMono }}>-${max}</span>
        <span style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono }}>0</span>
        <span style={{ color: TC.green,    fontSize: 9, fontFamily: TC.fontMono }}>+${max}</span>
      </div>
    </div>
  )
}

// ── Status Card ─────────────────────────────────────────────────────────────
function StatusCard({ label, value, sub, status }: { label: string; value: string; sub?: string; status: 'ok' | 'warn' | 'error' }) {
  const col = status === 'ok' ? TC.green : status === 'warn' ? TC.yellow : TC.red
  return (
    <TCCard style={{ padding: '14px 16px', flex: 1, minWidth: 0 }}>
      <div style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 10 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 7, height: 7, borderRadius: '50%', background: col, boxShadow: `0 0 7px ${col}`, flexShrink: 0 }}/>
        <span style={{ color: TC.text, fontFamily: TC.fontMono, fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</span>
      </div>
      {sub && <div style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono, marginTop: 5 }}>{sub}</div>}
    </TCCard>
  )
}

// ── Claude Health Card ───────────────────────────────────────────────────────
function ClaudeCard() {
  const [proxyHealth, setProxyHealth] = useState<ProxyHealth | null>(null)
  const [inference, setInference]     = useState<ClaudeHealth | null>(null)
  const [testing, setTesting]         = useState(false)

  // Poll proxy health every 60s — no inference call
  useEffect(() => {
    const check = () => api.getProxyHealth().then(setProxyHealth).catch(() => {})
    check()
    const iv = setInterval(check, 60_000)
    return () => clearInterval(iv)
  }, [])

  const runTest = async () => {
    setTesting(true)
    try {
      const h = await api.getClaudeHealth()
      setInference(h)
    } catch {
      setInference({ status: 'error', model: null, test_score: null, latency_ms: null, detail: 'Request failed' })
    }
    setTesting(false)
  }

  const proxyOk = proxyHealth?.proxy?.status === 'ok'
  const col     = proxyHealth === null ? TC.textMuted : proxyOk ? TC.green : proxyHealth?.proxy === null ? TC.yellow : TC.red
  const modeLabel = proxyHealth === null ? '…' : (proxyHealth.mode ?? 'direct').toUpperCase()

  return (
    <TCCard style={{ padding: '14px 16px', flex: 1, minWidth: 0 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 10 }}>Claude AI</div>
        <button onClick={runTest} disabled={testing} style={{
          padding: '2px 8px', borderRadius: 3, cursor: testing ? 'not-allowed' : 'pointer',
          border: `1px solid ${TC.border}`, background: 'transparent',
          color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 9, fontWeight: 700,
        }}>
          {testing ? '…' : '▶ TEST'}
        </button>
      </div>

      {/* Status dot + mode */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 7, height: 7, borderRadius: '50%', background: col, boxShadow: `0 0 7px ${col}`, flexShrink: 0 }}/>
        <span style={{ color: TC.text, fontFamily: TC.fontMono, fontWeight: 600, fontSize: 13 }}>{modeLabel}</span>
      </div>

      {/* Proxy stats (only when proxy is configured and reachable) */}
      {proxyHealth?.proxy && (
        <div style={{ marginTop: 8, display: 'flex', gap: 10 }}>
          <span style={{ color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 9 }}>
            ↑ {Math.floor((proxyHealth.proxy.uptime_seconds ?? 0) / 60)}m
          </span>
          <span style={{ color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 9 }}>
            {proxyHealth.proxy.requests} req
          </span>
          <span style={{ color: proxyHealth.proxy.errors > 0 ? TC.red : TC.textMuted, fontFamily: TC.fontMono, fontSize: 9 }}>
            {proxyHealth.proxy.errors} err
          </span>
          <span style={{ color: proxyHealth.proxy.auth_configured ? TC.green : TC.red, fontFamily: TC.fontMono, fontSize: 9 }}>
            {proxyHealth.proxy.auth_configured ? '✓ auth' : '✗ auth'}
          </span>
        </div>
      )}
      {proxyHealth?.error && (
        <div style={{ color: TC.red, fontSize: 10, fontFamily: TC.fontMono, marginTop: 5 }}>
          {proxyHealth.error}
        </div>
      )}

      {/* Inference result — only shown after TEST clicked */}
      {inference && (
        <div style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${TC.border}` }}>
          {inference.status === 'ok' && inference.test_score !== null ? (
            <div style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              score {inference.test_score > 0 ? '+' : ''}{inference.test_score.toFixed(3)} · {inference.latency_ms}ms · {inference.model}
            </div>
          ) : (
            <div style={{ color: TC.red, fontSize: 10, fontFamily: TC.fontMono, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {inference.detail ?? 'Error'}
            </div>
          )}
        </div>
      )}
    </TCCard>
  )
}

// ── Dashboard ───────────────────────────────────────────────────────────────
export default function Dashboard() {
  const { killSwitch, tradingMode, activeStrategy, signals, workspace } = useStore()
  const [positions, setPositions]   = useState<Position[]>([])
  const [trades, setTrades]         = useState<Trade[]>([])
  const [health, setHealth]         = useState<HealthStatus | null>(null)

  useEffect(() => {
    const load = tradingMode === 'live' ? api.livePositions : api.paperPositions
    load().then(setPositions).catch(() => {})
    const loadTrades = tradingMode === 'live' ? api.liveTrades : api.paperTrades
    loadTrades(20).then(setTrades).catch(() => {})
  }, [tradingMode])

  // Poll /health every 15s to get real DB + scheduler status
  useEffect(() => {
    const check = () => api.health().then(setHealth).catch(() => setHealth(null))
    check()
    const iv = setInterval(check, 15000)
    return () => clearInterval(iv)
  }, [])

  const dailyPnl = trades.reduce((sum, t) => sum + (t.pnl ?? 0), 0)

  // Live composite score from most recent signal in store
  const liveScore = signals.length > 0 ? (signals[0].score ?? 0) : 0
  const scoreSymbol = (activeStrategy?.symbol as string)
    ?? (workspace === 'crypto' ? 'BTC/USDT' : 'AAPL')

  const posColumns: ColDef<Position>[] = [
    { key: 'symbol', label: 'Symbol', mono: true },
    { key: 'side',   label: 'Side',   render: v => <TCBadge variant={String(v).toUpperCase() === 'LONG' ? 'buy' : 'sell'}>{String(v)}</TCBadge> },
    { key: 'quantity', label: 'Qty',  mono: true, right: true, render: v => <span style={{ fontFamily: TC.fontMono, color: TC.textMid }}>{String(v)}</span> },
    { key: 'avg_entry_price', label: 'Entry', mono: true, right: true, render: v => <span style={{ fontFamily: TC.fontMono }}>${Number(v).toLocaleString()}</span> },
  ]

  const tradeColumns: ColDef<Trade>[] = [
    { key: 'created_at', label: 'Time', mono: true, render: v => <span style={{ fontFamily: TC.fontMono, color: TC.textMuted, fontSize: 11 }}>{v ? new Date(String(v)).toLocaleTimeString() : '—'}</span> },
    { key: 'symbol', label: 'Symbol', mono: true },
    { key: 'side',   label: 'Side',   render: v => <TCBadge variant={String(v).toUpperCase() === 'BUY' ? 'buy' : 'sell'}>{String(v)}</TCBadge> },
    { key: 'price',  label: 'Price',  mono: true, right: true, render: v => <span style={{ fontFamily: TC.fontMono }}>${Number(v).toLocaleString()}</span> },
    { key: 'pnl',    label: 'P&L',    mono: true, right: true, render: v => (
      <span style={{ fontFamily: TC.fontMono, color: Number(v) >= 0 ? TC.green : TC.red, fontWeight: 600 }}>
        {Number(v) >= 0 ? '+' : '-'}${Math.abs(Number(v)).toFixed(2)}
      </span>
    )},
  ]

  const stratName  = (activeStrategy?.name as string) ?? 'None'
  const dbStatus   = health?.db === 'connected' ? 'ok' : health === null ? 'warn' : 'error'
  const schStatus  = health?.scheduler === 'running' ? 'ok' : health === null ? 'warn' : 'error'
  const dbLabel    = health ? (health.db === 'connected' ? 'Connected' : 'Disconnected') : '…'
  const schLabel   = health ? (health.scheduler === 'running' ? 'Running' : 'Stopped') : '…'
  const schSub     = health?.active_strategy ? `Strategy: ${health.active_strategy}` : 'No active strategy'

  return (
    <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Status cards */}
      <div style={{ display: 'flex', gap: 12 }}>
        <StatusCard label="Database"        value={dbLabel}                          sub="PostgreSQL / TimescaleDB"                    status={dbStatus as 'ok' | 'warn' | 'error'}/>
        <StatusCard label="Scheduler"       value={schLabel}                         sub={schSub}                                      status={schStatus as 'ok' | 'warn' | 'error'}/>
        <StatusCard label="Kill Switch"     value={killSwitch ? 'ACTIVE' : 'Off'}    sub={killSwitch ? 'Trading halted' : 'Enabled'}   status={killSwitch ? 'error' : 'ok'}/>
        <StatusCard label="Active Strategy" value={stratName}                        sub={tradingMode.toUpperCase()}                   status={stratName === 'None' ? 'warn' : 'ok'}/>
        <ClaudeCard/>
      </div>

      {/* Positions + Trades */}
      <div style={{ display: 'flex', gap: 12 }}>
        <TCCard style={{ flex: 1 }}>
          <TCSectionHeader title="Open Positions" right={<TCBadge variant="accent">{positions.length} active</TCBadge>}/>
          <TCTable columns={posColumns} rows={positions} emptyMsg="No open positions"/>
        </TCCard>
        <TCCard style={{ flex: 1 }}>
          <TCSectionHeader title="Recent Trades" right={<TCBadge>{trades.length} total</TCBadge>}/>
          <TCTable columns={tradeColumns} rows={trades} emptyMsg="No recent trades"/>
        </TCCard>
      </div>

      {/* Data seed panel */}
      <DataSeedPanel workspace={workspace}/>

      {/* PnL + Score */}
      <div style={{ display: 'flex', gap: 12 }}>
        <TCCard style={{ flex: 1 }}>
          <TCSectionHeader title="Daily P&L" right={
            <span style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono, animation: 'tcPulse 2s infinite' }}>● LIVE</span>
          }/>
          <PnLMeter pnl={dailyPnl}/>
        </TCCard>
        <TCCard style={{ flex: 1 }}>
          <TCSectionHeader title="Composite Score" right={
            <span style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono }}>
              {scoreSymbol} · {signals.length > 0 ? 'live' : 'no data'}
            </span>
          }/>
          <div style={{ padding: '14px 12px' }}>
            <ScoreGauge score={liveScore}/>
          </div>
        </TCCard>
      </div>
    </div>
  )
}
