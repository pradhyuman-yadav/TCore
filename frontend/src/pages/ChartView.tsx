import { useEffect, useRef, useState, useCallback } from 'react'
import { api, WatchedSymbol } from '../api'
import { TC } from '../theme'
import { TCBadge, TCSectionHeader } from '../components/ui'

// ── TradingView helpers ────────────────────────────────────────────────────
const TV_EXCHANGE_MAP: Record<string, string> = {
  binanceus:  'BINANCEUS',
  binance:    'BINANCE',
  coinbase:   'COINBASE',
  kraken:     'KRAKEN',
  bybit:      'BYBIT',
  yfinance_us:  'NASDAQ',
  yfinance_in:  'NSE',
}

const toTvSymbol = (symbol: string, exchange: string): string => {
  const pair = symbol.replace('/', '')
  const ex = TV_EXCHANGE_MAP[exchange.toLowerCase()] ?? exchange.toUpperCase()
  return `${ex}:${pair}`
}

// ── TradingView widget ────────────────────────────────────────────────────
interface TVWidgetInstance {
  setSymbol: (s: string, interval: string, cb: () => void) => void
}

declare global {
  interface Window {
    TradingView?: { widget: new (config: Record<string, unknown>) => TVWidgetInstance }
  }
}

let tvScriptLoaded = false
let tvScriptCallbacks: Array<() => void> = []

function loadTvScript(cb: () => void) {
  if (tvScriptLoaded) { cb(); return }
  tvScriptCallbacks.push(cb)
  if (tvScriptCallbacks.length > 1) return
  const s = document.createElement('script')
  s.src = 'https://s3.tradingview.com/tv.js'
  s.async = true
  s.onload = () => { tvScriptLoaded = true; tvScriptCallbacks.forEach(f => f()); tvScriptCallbacks = [] }
  document.head.appendChild(s)
}

interface TVChartProps {
  symbol: string
  exchange: string
  containerId: string
  widgetRef: React.MutableRefObject<TVWidgetInstance | null>
}

function TradingViewChart({ symbol, exchange, containerId, widgetRef }: TVChartProps) {
  useEffect(() => {
    const tvSym = toTvSymbol(symbol, exchange)

    loadTvScript(() => {
      if (!window.TradingView) return
      const el = document.getElementById(containerId)
      if (el) el.innerHTML = ''

      widgetRef.current = new window.TradingView.widget({
        container_id:        containerId,
        autosize:            true,
        symbol:              tvSym,
        interval:            '15',
        timezone:            'Etc/UTC',
        theme:               'dark',
        style:               '1',
        locale:              'en',
        toolbar_bg:          TC.surface,
        backgroundColor:     TC.bg,
        enable_publishing:   false,
        withdateranges:      true,
        hide_top_toolbar:    false,
        allow_symbol_change: true,
        save_image:          false,
        hide_side_toolbar:   false,
        studies:             [],
        overrides: {
          'mainSeriesProperties.candleStyle.upColor':         TC.green,
          'mainSeriesProperties.candleStyle.downColor':       TC.red,
          'mainSeriesProperties.candleStyle.borderUpColor':   TC.green,
          'mainSeriesProperties.candleStyle.borderDownColor': TC.red,
          'mainSeriesProperties.candleStyle.wickUpColor':     TC.green,
          'mainSeriesProperties.candleStyle.wickDownColor':   TC.red,
          'paneProperties.background':                        TC.bg,
          'paneProperties.backgroundType':                    'solid',
          'scalesProperties.textColor':                       TC.textMuted,
        },
      }) as TVWidgetInstance
    })
  }, [symbol, exchange, containerId])

  return <div id={containerId} style={{ width: '100%', height: '100%', minHeight: 450 }}/>
}

// ── Live trades panel ─────────────────────────────────────────────────────
interface LiveTrade {
  price: number
  qty: number
  isBuyerMaker: boolean
  time: number
}

function useLiveTrades(symbol: string): LiveTrade[] {
  const [trades, setTrades] = useState<LiveTrade[]>([])
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!symbol) return
    // Strip exchange prefix and convert to binance stream format
    const base = symbol.replace('/', '').toLowerCase()
    const url = `wss://stream.binance.us:9443/stream?streams=${base}@trade`

    let ws: WebSocket
    let dead = false

    function connect() {
      if (dead) return
      try {
        ws = new WebSocket(url)
        wsRef.current = ws
        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data)
            const t = msg.data || msg
            setTrades(prev => [{
              price: parseFloat(t.p),
              qty: parseFloat(t.q),
              isBuyerMaker: t.m,
              time: Math.floor(t.T / 1000),
            }, ...prev].slice(0, 50))
          } catch { /* ignore */ }
        }
        ws.onclose = () => { if (!dead) setTimeout(connect, 3000) }
        ws.onerror = () => ws.close()
      } catch { /* not a crypto symbol */ }
    }

    connect()
    return () => { dead = true; ws?.close() }
  }, [symbol])

  return trades
}

function LiveTradesPanel({ symbol }: { symbol: string }) {
  const trades = useLiveTrades(symbol)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div style={{ padding: '8px 10px', borderBottom: `1px solid ${TC.border}`, flexShrink: 0 }}>
        <span style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
          Live Trades
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', padding: '4px 8px', borderBottom: `1px solid ${TC.border}` }}>
        {['Price', 'Qty', 'Time'].map(h => (
          <span key={h} style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono }}>{h}</span>
        ))}
      </div>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {trades.length === 0 && (
          <div style={{ padding: '20px 10px', color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono, textAlign: 'center' }}>
            Waiting for trades…
          </div>
        )}
        {trades.map((t, i) => {
          const col = t.isBuyerMaker ? TC.red : TC.green
          const time = new Date(t.time * 1000).toTimeString().slice(0, 8)
          return (
            <div key={i} style={{
              display: 'grid', gridTemplateColumns: '1fr 1fr auto',
              padding: '3px 8px', borderBottom: `1px solid ${TC.border}`,
              background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
            }}>
              <span style={{ color: col, fontSize: 10, fontFamily: TC.fontMono, fontWeight: 600 }}>
                {t.price.toFixed(2)}
              </span>
              <span style={{ color: TC.textMid, fontSize: 10, fontFamily: TC.fontMono }}>
                {t.qty.toFixed(4)}
              </span>
              <span style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono }}>
                {time}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Tracked symbols panel ─────────────────────────────────────────────────
interface AddSymbolModalProps {
  onAdd: (symbol: string, exchange: string, assetType: string) => void
  onClose: () => void
}

function AddSymbolModal({ onAdd, onClose }: AddSymbolModalProps) {
  const [symbol, setSymbol] = useState('')
  const [exchange, setExchange] = useState('binanceus')
  const [assetType, setAssetType] = useState('crypto')

  const EXCHANGE_DEFAULTS: Record<string, string> = {
    crypto:        'binanceus',
    us_stock:      'yfinance_us',
    indian_stock:  'yfinance_in',
  }

  const handleAssetChange = (t: string) => {
    setAssetType(t)
    setExchange(EXCHANGE_DEFAULTS[t] || 'binanceus')
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', zIndex: 999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        background: TC.surface2, border: `1px solid ${TC.border}`, borderRadius: 8,
        padding: 24, width: 320, display: 'flex', flexDirection: 'column', gap: 14,
      }} onClick={e => e.stopPropagation()}>
        <span style={{ color: TC.text, fontFamily: TC.fontMono, fontSize: 12, fontWeight: 700 }}>
          Add to Watchlist
        </span>
        <select value={assetType} onChange={e => handleAssetChange(e.target.value)}
          style={{ padding: '6px 8px', background: TC.surface3, border: `1px solid ${TC.border}`, borderRadius: 4, color: TC.textMid, fontFamily: TC.fontMono, fontSize: 11 }}>
          <option value="crypto">Crypto</option>
          <option value="us_stock">US Stock</option>
          <option value="indian_stock">Indian Stock</option>
        </select>
        <input
          value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())}
          placeholder={assetType === 'crypto' ? 'e.g. BTC/USDT' : assetType === 'us_stock' ? 'e.g. AAPL' : 'e.g. RELIANCE'}
          style={{ padding: '6px 8px', background: TC.surface3, border: `1px solid ${TC.border}`, borderRadius: 4, color: TC.text, fontFamily: TC.fontMono, fontSize: 11, outline: 'none' }}
        />
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => { if (symbol) { onAdd(symbol.trim(), exchange, assetType); onClose() } }}
            style={{ flex: 1, padding: '6px', background: TC.accentDim, border: `1px solid ${TC.accent}`, borderRadius: 4, color: TC.accent, fontFamily: TC.fontMono, fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>
            Add
          </button>
          <button onClick={onClose}
            style={{ flex: 1, padding: '6px', background: 'transparent', border: `1px solid ${TC.border}`, borderRadius: 4, color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 11, cursor: 'pointer' }}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

function TrackedSymbolsPanel({
  symbols, selected, onSelect, onAdd, onRemove, latestPrices,
}: {
  symbols: WatchedSymbol[]
  selected: string
  onSelect: (s: WatchedSymbol) => void
  onAdd: () => void
  onRemove: (id: string) => void
  latestPrices: Record<string, number>
}) {
  const groups = ['crypto', 'us_stock', 'indian_stock']
  const labels: Record<string, string> = { crypto: 'Crypto', us_stock: 'US Stocks', indian_stock: 'Indian' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div style={{ padding: '8px 10px', borderBottom: `1px solid ${TC.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
        <span style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Watchlist</span>
        <button onClick={onAdd} style={{ background: TC.accentDim, border: `1px solid ${TC.accent}`, borderRadius: 3, color: TC.accent, fontFamily: TC.fontMono, fontSize: 10, padding: '2px 7px', cursor: 'pointer', fontWeight: 700 }}>+</button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {groups.map(g => {
          const items = symbols.filter(s => s.asset_type === g)
          if (items.length === 0) return null
          return (
            <div key={g}>
              <div style={{ padding: '6px 10px 3px', color: TC.textMuted, fontSize: 8.5, fontFamily: TC.fontMono, letterSpacing: '0.1em', textTransform: 'uppercase', background: TC.surface }}>
                {labels[g]}
              </div>
              {items.map(sym => {
                const isActive = selected === sym.symbol
                const price = latestPrices[sym.symbol]
                return (
                  <div key={sym.id} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '7px 10px', cursor: 'pointer',
                    background: isActive ? 'rgba(0,212,255,0.07)' : 'transparent',
                    borderLeft: `2px solid ${isActive ? TC.accent : 'transparent'}`,
                  }} onClick={() => onSelect(sym)}>
                    <div>
                      <div style={{ color: isActive ? TC.accent : TC.text, fontSize: 11, fontFamily: TC.fontMono, fontWeight: isActive ? 700 : 400 }}>
                        {sym.symbol}
                      </div>
                      {price != null && (
                        <div style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono }}>
                          ${price.toLocaleString()}
                        </div>
                      )}
                    </div>
                    <button onClick={e => { e.stopPropagation(); onRemove(sym.id) }}
                      style={{ background: 'transparent', border: 'none', color: TC.textMuted, cursor: 'pointer', fontSize: 14, padding: '0 2px', lineHeight: 1 }}
                      title="Remove">×</button>
                  </div>
                )
              })}
            </div>
          )
        })}
        {symbols.length === 0 && (
          <div style={{ padding: '20px 10px', color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono, textAlign: 'center' }}>
            No symbols tracked.<br/>Click + to add.
          </div>
        )}
      </div>
    </div>
  )
}

// ── Indicators ────────────────────────────────────────────────────────────
const INDICATORS = [
  { key: 'rsi',       label: 'RSI',          weight: 0.25, value: 0.55 },
  { key: 'macd',      label: 'MACD',         weight: 0.20, value: 0.42 },
  { key: 'bb',        label: 'BB Position',  weight: 0.15, value: 0.68 },
  { key: 'ema',       label: 'EMA Cross',    weight: 0.20, value: 0.60 },
  { key: 'volume',    label: 'Volume Surge', weight: 0.10, value: 0.45 },
  { key: 'sentiment', label: 'Sentiment',    weight: 0.10, value: 0.58 },
]

function IndicatorBar({ label, value, weight }: { label: string; value: number; weight: number }) {
  const col = value > 0.3 ? TC.green : value < -0.3 ? TC.red : TC.textMid
  const contrib = (value * weight).toFixed(4)
  const pctHalf = Math.min(Math.abs(value), 1) * 50
  return (
    <div style={{ padding: '9px 16px', borderRight: `1px solid ${TC.border}` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono }}>{label}</span>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ color: col, fontSize: 10, fontFamily: TC.fontMono, fontWeight: 600 }}>
            {value >= 0 ? '+' : ''}{value.toFixed(3)}
          </span>
          <span style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono }}>
            ×{weight.toFixed(2)}={Number(contrib) > 0 ? '+' : ''}{contrib}
          </span>
        </div>
      </div>
      <div style={{ position: 'relative', height: 3, background: TC.surface2, borderRadius: 2 }}>
        <div style={{
          position: 'absolute', height: '100%', width: `${pctHalf}%`,
          left: value >= 0 ? '50%' : `${50 - pctHalf}%`,
          background: col, borderRadius: 2, boxShadow: `0 0 5px ${col}55`,
        }}/>
        <div style={{ position: 'absolute', left: '50%', top: 0, width: 1, height: '100%', background: 'rgba(255,255,255,0.15)' }}/>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────
export default function ChartView() {
  const [watchlist, setWatchlist]   = useState<WatchedSymbol[]>([])
  const [selected, setSelected]     = useState<WatchedSymbol | null>(null)
  const [syncing, setSyncing]       = useState(false)
  const [syncDays, setSyncDays]     = useState(90)
  const [syncResult, setSyncResult] = useState<string | null>(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [latestPrices, setLatestPrices] = useState<Record<string, number>>({})
  const widgetRef = useRef<TVWidgetInstance | null>(null)
  const chartId   = useRef(`tv_${Math.random().toString(36).slice(2)}`).current

  // Load watchlist
  useEffect(() => {
    api.getWatchlist().then(rows => {
      setWatchlist(rows)
      if (rows.length > 0) setSelected(rows[0])
    }).catch(() => {})
  }, [])

  // Subscribe to /ws/prices for live price updates in the sidebar
  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/prices`)
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.type === 'tick') {
          setLatestPrices(prev => ({ ...prev, [data.symbol]: data.close }))
        }
      } catch { /* ignore */ }
    }
    return () => ws.close()
  }, [])

  const handleSelect = useCallback((sym: WatchedSymbol) => {
    setSelected(sym)
    // If TV widget supports setSymbol, use it; otherwise the chart re-renders via key prop
  }, [])

  const handleAdd = async (symbol: string, exchange: string, assetType: string) => {
    try {
      const row = await api.addWatchedSymbol(symbol, exchange, assetType)
      setWatchlist(prev => [...prev, row])
      setSelected(row)
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Failed to add symbol')
    }
  }

  const handleRemove = async (id: string) => {
    await api.removeWatchedSymbol(id).catch(() => {})
    setWatchlist(prev => prev.filter(s => s.id !== id))
    if (selected?.id === id) {
      const remaining = watchlist.filter(s => s.id !== id)
      setSelected(remaining[0] ?? null)
    }
  }

  const handleSync = async () => {
    if (!selected) return
    setSyncing(true)
    setSyncResult(null)
    try {
      const res = await api.syncMarket(selected.symbol, selected.exchange, '1h', syncDays)
      setSyncResult(`✓ ${res.upserted} bars stored`)
    } catch (e: unknown) {
      setSyncResult(`✗ ${e instanceof Error ? e.message : 'Sync failed'}`)
    }
    setSyncing(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

      {/* Thin top bar: sync controls only */}
      <div style={{
        padding: '6px 14px', borderBottom: `1px solid ${TC.border}`,
        display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
        background: TC.surface,
      }}>
        {selected && (
          <span style={{ color: TC.accent, fontFamily: TC.fontMono, fontSize: 12, fontWeight: 700, marginRight: 6 }}>
            {selected.symbol}
          </span>
        )}
        <select value={syncDays} onChange={e => setSyncDays(Number(e.target.value))}
          style={{ padding: '3px 6px', background: TC.surface2, border: `1px solid ${TC.border}`, borderRadius: 4, color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 11, cursor: 'pointer' }}>
          {[7, 30, 90, 180, 365].map(d => <option key={d} value={d}>{d}d</option>)}
        </select>
        <button onClick={handleSync} disabled={syncing || !selected} style={{
          padding: '3px 12px', borderRadius: 5, cursor: syncing ? 'not-allowed' : 'pointer',
          border: `1px solid ${TC.border}`, background: 'transparent',
          color: syncing ? TC.textMuted : TC.textMid, fontFamily: TC.fontMono, fontSize: 10, fontWeight: 700,
        }}>
          {syncing ? '⟳ Syncing…' : '⟳ DB Sync'}
        </button>
        {syncResult && (
          <span style={{ color: syncResult.startsWith('✓') ? TC.green : TC.red, fontSize: 10, fontFamily: TC.fontMono }}>
            {syncResult}
          </span>
        )}
        <div style={{ marginLeft: 'auto', color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono }}>
          Live data via TradingView · DB Sync feeds indicator engine
        </div>
      </div>

      {/* 3-column layout */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>

        {/* Left: Tracked symbols */}
        <div style={{ width: 175, flexShrink: 0, borderRight: `1px solid ${TC.border}`, background: TC.surface, overflow: 'hidden' }}>
          <TrackedSymbolsPanel
            symbols={watchlist}
            selected={selected?.symbol ?? ''}
            onSelect={handleSelect}
            onAdd={() => setShowAddModal(true)}
            onRemove={handleRemove}
            latestPrices={latestPrices}
          />
        </div>

        {/* Center: TradingView chart */}
        <div style={{ flex: 1, minWidth: 0, background: TC.bg }}>
          {selected ? (
            <TradingViewChart
              key={selected.symbol + selected.exchange}
              symbol={selected.symbol}
              exchange={selected.exchange}
              containerId={chartId}
              widgetRef={widgetRef}
            />
          ) : (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 12 }}>
              Add a symbol to get started
            </div>
          )}
        </div>

        {/* Right: Live public trades */}
        <div style={{ width: 240, flexShrink: 0, borderLeft: `1px solid ${TC.border}`, background: TC.surface, overflow: 'hidden' }}>
          <LiveTradesPanel symbol={selected?.symbol ?? ''} />
        </div>

      </div>

      {/* Bottom: Indicator snapshot */}
      <div style={{ flexShrink: 0, borderTop: `1px solid ${TC.border}`, background: TC.surface }}>
        <TCSectionHeader title="Indicator Snapshot" right={
          <span style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono }}>
            Last: {new Date().toTimeString().slice(0, 8)}
          </span>
        }/>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)' }}>
          {INDICATORS.map(ind => (
            <IndicatorBar key={ind.key} label={ind.label} value={ind.value} weight={ind.weight}/>
          ))}
        </div>
      </div>

      {showAddModal && (
        <AddSymbolModal onAdd={handleAdd} onClose={() => setShowAddModal(false)}/>
      )}
    </div>
  )
}
