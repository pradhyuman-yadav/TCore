import { useEffect, useRef, useState, useCallback } from 'react'
import { api, WatchedSymbol, PaperAccount, PaperAccountConfig } from '../api'
import { TC } from '../theme'
import { TCSectionHeader } from '../components/ui'
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts'
import type { IChartApi } from 'lightweight-charts'

// ── Lightweight Charts component ───────────────────────────────────────────

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d']

interface OHLCVBar {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

// Simple bar type (avoids lightweight-charts branded UTCTimestamp complexity)
interface Bar {
  time: number
  open: number
  high: number
  low: number
  close: number
}

interface LWChartProps {
  symbol: string
  exchange: string
  timeframe: string
  onPriceUpdate?: (price: number) => void
}

function LightweightChart({ symbol, exchange, timeframe, onPriceUpdate }: LWChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<IChartApi | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesRef    = useRef<any>(null)
  const pendingRef   = useRef<Bar | null>(null)
  const [noData, setNoData] = useState(false)

  // Create chart once on mount
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: TC.bg },
        textColor: TC.textMuted,
        fontFamily: TC.fontMono,
        fontSize: 10,
      },
      grid: {
        vertLines: { color: 'rgba(255,255,255,0.03)' },
        horzLines: { color: 'rgba(255,255,255,0.03)' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: TC.border },
      timeScale: {
        borderColor: TC.border,
        timeVisible: true,
        secondsVisible: timeframe === '1m',
      },
      width:  containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    })

    const series = chart.addCandlestickSeries({
      upColor:         TC.green,
      downColor:       TC.red,
      borderUpColor:   TC.green,
      borderDownColor: TC.red,
      wickUpColor:     TC.green,
      wickDownColor:   TC.red,
    })

    chartRef.current  = chart
    seriesRef.current = series

    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      chart.applyOptions({ width, height })
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current  = null
      seriesRef.current = null
    }
  }, [])

  // Update secondsVisible when timeframe changes
  useEffect(() => {
    chartRef.current?.applyOptions({
      timeScale: { secondsVisible: timeframe === '1m' },
    })
  }, [timeframe])

  // Load history + start live WS whenever symbol / exchange / timeframe changes
  useEffect(() => {
    const series = seriesRef.current
    if (!series) return

    let dead = false
    let ws: WebSocket | null = null

    const loadHistory = async () => {
      setNoData(false)
      try {
        const params = new URLSearchParams({ symbol, exchange, timeframe, limit: '500' })
        const res    = await fetch(`/api/market/ohlcv?${params}`)
        if (!res.ok) throw new Error('fetch failed')
        const bars: OHLCVBar[] = await res.json()
        if (!bars.length) { setNoData(true); return }

        const data: Bar[] = bars
          .map(b => ({
            time:  Math.floor(new Date(b.time).getTime() / 1000),
            open:  Number(b.open),
            high:  Number(b.high),
            low:   Number(b.low),
            close: Number(b.close),
          }))
          .sort((a, b) => a.time - b.time)

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        series.setData(data as any)
        chartRef.current?.timeScale().fitContent()
        if (data.length && onPriceUpdate) {
          onPriceUpdate(data[data.length - 1].close)
        }
      } catch {
        setNoData(true)
      }
    }

    loadHistory()

    // Connect backend WS for live kline ticks from Binance US
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'

    function connectWs() {
      if (dead) return
      try {
        ws = new WebSocket(`${proto}://${window.location.host}/ws/prices`)
        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data)
            if (msg.type === 'tick' && msg.symbol === symbol) {
              pendingRef.current = {
                time:  Number(msg.time),
                open:  Number(msg.open),
                high:  Number(msg.high),
                low:   Number(msg.low),
                close: Number(msg.close),
              }
            }
          } catch { /* ignore */ }
        }
        ws.onclose = () => { if (!dead) setTimeout(connectWs, 3000) }
        ws.onerror = () => ws?.close()
      } catch { /* ignore */ }
    }

    connectWs()

    // Sample at 100 ms — apply buffered bar without causing React re-renders
    const timer = setInterval(() => {
      const bar = pendingRef.current
      if (bar && seriesRef.current) {
        try {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          seriesRef.current.update(bar as any)
          if (onPriceUpdate) onPriceUpdate(bar.close)
        } catch { /* stale bar from previous symbol */ }
        pendingRef.current = null
      }
    }, 100)

    return () => {
      dead = true
      ws?.close()
      clearInterval(timer)
      pendingRef.current = null
    }
  }, [symbol, exchange, timeframe])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      {noData && (
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 10,
          color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 12,
          background: 'rgba(0,0,0,0.5)',
          pointerEvents: 'none',
        }}>
          <span>No data for {symbol} / {timeframe}</span>
          <span style={{ fontSize: 10, opacity: 0.6 }}>Use ⟳ DB Sync to fetch historical bars</span>
        </div>
      )}
    </div>
  )
}

// ── Live trades panel ─────────────────────────────────────────────────────
interface LiveTrade {
  price: number
  qty: number
  isBuyerMaker: boolean
  time: number
}

function useLiveTrades(symbol: string, assetType: string): LiveTrade[] {
  const [trades, setTrades] = useState<LiveTrade[]>([])

  useEffect(() => {
    // Binance US public trade stream is only available for crypto symbols
    if (!symbol || assetType !== 'crypto') return
    const base = symbol.replace('/', '').toLowerCase()
    const url  = `wss://stream.binance.us:9443/stream?streams=${base}@trade`

    let ws: WebSocket
    let dead = false

    function connect() {
      if (dead) return
      try {
        ws = new WebSocket(url)
        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data)
            const t   = msg.data || msg
            setTrades(prev => [{
              price:        parseFloat(t.p),
              qty:          parseFloat(t.q),
              isBuyerMaker: t.m,
              time:         Math.floor(t.T / 1000),
            }, ...prev].slice(0, 50))
          } catch { /* ignore */ }
        }
        ws.onclose = () => { if (!dead) setTimeout(connect, 3000) }
        ws.onerror = () => ws.close()
      } catch { /* ignore */ }
    }

    connect()
    return () => { dead = true; ws?.close() }
  }, [symbol, assetType])

  return trades
}

function LiveTradesPanel({ symbol, assetType }: { symbol: string; assetType: string }) {
  const trades = useLiveTrades(symbol, assetType)
  const isCrypto = assetType === 'crypto'

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
        {!isCrypto && (
          <div style={{ padding: '20px 10px', color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono, textAlign: 'center' }}>
            Live trades not available<br/>for stocks
          </div>
        )}
        {isCrypto && trades.length === 0 && (
          <div style={{ padding: '20px 10px', color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono, textAlign: 'center' }}>
            Waiting for trades…
          </div>
        )}
        {trades.map((t, i) => {
          const col  = t.isBuyerMaker ? TC.red : TC.green
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
  const [symbol, setSymbol]     = useState('')
  const [exchange, setExchange] = useState('binanceus')
  const [assetType, setAssetType] = useState('crypto')

  const EXCHANGE_DEFAULTS: Record<string, string> = {
    crypto:       'binanceus',
    us_stock:     'yfinance_us',
    indian_stock: 'yfinance_in',
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
                const price    = latestPrices[sym.symbol]
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
            No symbols tracked.<br />Click + to add.
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
  const col    = value > 0.3 ? TC.green : value < -0.3 ? TC.red : TC.textMid
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

// ── Paper Account Modal ───────────────────────────────────────────────────
function PaperAccountModal({ onClose }: { onClose: () => void }) {
  const [account,  setAccount]  = useState<PaperAccount | null>(null)
  const [capital,  setCapital]  = useState(10000)
  const [feeRate,  setFeeRate]  = useState(0.1)   // displayed as percent
  const [slipBps,  setSlipBps]  = useState(5)
  const [saving,   setSaving]   = useState(false)
  const [saved,    setSaved]    = useState(false)

  useEffect(() => {
    api.getPaperAccount().then(a => {
      setAccount(a)
      setCapital(a.initial_capital)
      setFeeRate(+(a.fee_rate * 100).toFixed(4))  // decimal → percent
      setSlipBps(a.slippage_bps)
    }).catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const cfg: PaperAccountConfig = {
        initial_capital: capital,
        fee_rate: feeRate / 100,   // percent → decimal
        slippage_bps: slipBps,
      }
      const updated = await api.setPaperAccount(cfg)
      setAccount(prev => prev ? { ...prev, ...updated } : updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
    } catch { /* ignore */ }
    setSaving(false)
  }

  const iStyle: React.CSSProperties = {
    padding: '7px 10px', background: 'rgba(255,255,255,0.05)',
    border: `1px solid ${TC.border}`, borderRadius: 5,
    color: TC.text, fontFamily: TC.fontMono, fontSize: 12,
    outline: 'none', width: '100%', boxSizing: 'border-box',
  }
  const lStyle: React.CSSProperties = {
    color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono,
    letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 5,
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', zIndex: 999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        background: TC.surface2, border: `1px solid ${TC.border}`, borderRadius: 10,
        padding: 24, width: 380, display: 'flex', flexDirection: 'column', gap: 16,
      }} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: TC.text, fontFamily: TC.fontMono, fontSize: 13, fontWeight: 700 }}>
            Paper Account Setup
          </span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: TC.textMuted, cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>×</button>
        </div>

        {/* Live stats */}
        {account && (
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ flex: 1, padding: '10px 12px', background: TC.surface, borderRadius: 6, border: `1px solid ${TC.border}` }}>
              <div style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 5 }}>Realized P&L</div>
              <div style={{ color: account.realized_pnl >= 0 ? TC.green : TC.red, fontFamily: TC.fontMono, fontSize: 16, fontWeight: 700 }}>
                {account.realized_pnl >= 0 ? '+' : ''}{account.realized_pnl.toFixed(2)} USDT
              </div>
            </div>
            <div style={{ flex: 1, padding: '10px 12px', background: TC.surface, borderRadius: 6, border: `1px solid ${TC.border}` }}>
              <div style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 5 }}>Open Positions</div>
              <div style={{ color: TC.accent, fontFamily: TC.fontMono, fontSize: 16, fontWeight: 700 }}>{account.open_positions}</div>
            </div>
          </div>
        )}

        {/* Config fields */}
        <div>
          <div style={lStyle}>Initial Capital (USDT)</div>
          <input type="number" value={capital} min={100} step={100}
            onChange={e => setCapital(parseFloat(e.target.value) || 10000)}
            style={{ ...iStyle, color: TC.accent }}/>
          <div style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono, marginTop: 4 }}>
            Starting virtual balance for paper trades
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <div style={lStyle}>Fee Rate (%)</div>
            <input type="number" value={feeRate} min={0} max={5} step={0.01}
              onChange={e => setFeeRate(parseFloat(e.target.value) || 0)}
              style={iStyle}/>
            <div style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono, marginTop: 4 }}>
              e.g. 0.1 = 0.1% per trade
            </div>
          </div>
          <div>
            <div style={lStyle}>Slippage (bps)</div>
            <input type="number" value={slipBps} min={0} max={500} step={1}
              onChange={e => setSlipBps(parseInt(e.target.value) || 0)}
              style={iStyle}/>
            <div style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono, marginTop: 4 }}>
              1 bps = 0.01% price impact
            </div>
          </div>
        </div>

        {/* Note */}
        <div style={{ padding: '8px 10px', background: 'rgba(255,204,0,0.06)', border: `1px solid rgba(255,204,0,0.18)`, borderRadius: 5, color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono }}>
          Changes apply to new fills only. Past trades are not recalculated.
        </div>

        {/* Buttons */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '7px 18px', background: 'transparent', border: `1px solid ${TC.border}`, borderRadius: 5, color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 11, cursor: 'pointer' }}>
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving} style={{
            padding: '7px 18px', background: saved ? TC.greenDim : TC.accentDim,
            border: `1px solid ${saved ? TC.green : TC.accent}`,
            borderRadius: 5, color: saved ? TC.green : TC.accent,
            fontFamily: TC.fontMono, fontSize: 11, fontWeight: 700, cursor: saving ? 'not-allowed' : 'pointer',
          }}>
            {saved ? '✓ Saved' : saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}


// ── Main Page ─────────────────────────────────────────────────────────────
export default function ChartView() {
  const [watchlist, setWatchlist]           = useState<WatchedSymbol[]>([])
  const [selected, setSelected]             = useState<WatchedSymbol | null>(null)
  const [timeframe, setTimeframe]           = useState('1m')
  const [livePrice, setLivePrice]           = useState<number | null>(null)
  const [syncing, setSyncing]               = useState(false)
  const [syncDays, setSyncDays]             = useState(90)
  const [syncResult, setSyncResult]         = useState<string | null>(null)
  const [showAddModal, setShowAddModal]     = useState(false)
  const [showAccountModal, setShowAccountModal] = useState(false)
  const [latestPrices, setLatestPrices]     = useState<Record<string, number>>({})
  const [paperPnl, setPaperPnl]             = useState<number | null>(null)

  // Load watchlist + paper account on mount
  useEffect(() => {
    api.getWatchlist().then(rows => {
      setWatchlist(rows)
      if (rows.length > 0) setSelected(rows[0])
    }).catch(() => {})
    api.getPaperAccount().then(a => setPaperPnl(a.realized_pnl)).catch(() => {})
  }, [])

  // Subscribe to /ws/prices for sidebar price badges — auto-reconnects on drop
  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    let ws: WebSocket
    let dead = false

    function connect() {
      if (dead) return
      ws = new WebSocket(`${proto}://${window.location.host}/ws/prices`)
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          if (data.type === 'tick') {
            setLatestPrices(prev => ({ ...prev, [data.symbol]: data.close }))
          }
        } catch { /* ignore */ }
      }
      ws.onclose = () => { if (!dead) setTimeout(connect, 3000) }
      ws.onerror = () => ws.close()
    }

    connect()
    return () => { dead = true; ws?.close() }
  }, [])

  const handleSelect = useCallback((sym: WatchedSymbol) => {
    setSelected(sym)
    setLivePrice(null)
  }, [])

  const handleAdd = async (symbol: string, exchange: string, assetType: string) => {
    try {
      const row = await api.addWatchedSymbol(symbol, exchange, assetType)
      setWatchlist(prev => [...prev, row])
      setSelected(row)
      setLivePrice(null)
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
      setLivePrice(null)
    }
  }

  const handleSync = async () => {
    if (!selected) return
    setSyncing(true)
    setSyncResult(null)
    try {
      const res = await api.syncMarket(selected.symbol, selected.exchange, timeframe, syncDays)
      setSyncResult(`✓ ${res.upserted} bars stored`)
    } catch (e: unknown) {
      setSyncResult(`✗ ${e instanceof Error ? e.message : 'Sync failed'}`)
    }
    setSyncing(false)
  }

  const handlePriceUpdate = useCallback((price: number) => {
    setLivePrice(price)
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

      {/* Top bar: symbol + live price + timeframe selector + DB sync */}
      <div style={{
        padding: '5px 14px', borderBottom: `1px solid ${TC.border}`,
        display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
        background: TC.surface,
      }}>
        {/* Symbol + live price */}
        {selected && (
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginRight: 6 }}>
            <span style={{ color: TC.accent, fontFamily: TC.fontMono, fontSize: 12, fontWeight: 700 }}>
              {selected.symbol}
            </span>
            {livePrice != null && (
              <span style={{ color: TC.text, fontFamily: TC.fontMono, fontSize: 16, fontWeight: 700, letterSpacing: '-0.02em' }}>
                ${livePrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            )}
          </div>
        )}

        {/* Separator */}
        <div style={{ width: 1, height: 18, background: TC.border, marginRight: 4 }} />

        {/* Timeframe pills */}
        <div style={{ display: 'flex', gap: 3 }}>
          {TIMEFRAMES.map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)} style={{
              padding: '2px 8px', borderRadius: 4, cursor: 'pointer', fontFamily: TC.fontMono, fontSize: 10, fontWeight: 600,
              background: timeframe === tf ? TC.accentDim : 'transparent',
              border: `1px solid ${timeframe === tf ? TC.accent : TC.border}`,
              color: timeframe === tf ? TC.accent : TC.textMuted,
              transition: 'all 0.1s',
            }}>{tf}</button>
          ))}
        </div>

        {/* Separator */}
        <div style={{ width: 1, height: 18, background: TC.border, margin: '0 4px' }} />

        {/* DB Sync */}
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

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* Paper P&L quick badge */}
          {paperPnl !== null && (
            <span style={{
              fontFamily: TC.fontMono, fontSize: 10, fontWeight: 700,
              color: paperPnl >= 0 ? TC.green : TC.red,
              opacity: 0.85,
            }}>
              Paper P&L: {paperPnl >= 0 ? '+' : ''}{paperPnl.toFixed(2)} USDT
            </span>
          )}
          {/* Paper account setup button */}
          <button onClick={() => setShowAccountModal(true)} style={{
            padding: '3px 10px', borderRadius: 4, cursor: 'pointer',
            background: TC.yellowDim, border: `1px solid ${TC.yellow}44`,
            color: TC.yellow, fontFamily: TC.fontMono, fontSize: 10, fontWeight: 700,
          }} title="Configure paper trading account">
            ⚙ Paper
          </button>
          <span style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono, opacity: 0.6 }}>
            Binance US · 100ms
          </span>
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

        {/* Center: Lightweight Chart */}
        <div style={{ flex: 1, minWidth: 0, background: TC.bg, overflow: 'hidden' }}>
          {selected ? (
            <LightweightChart
              key={selected.symbol + '|' + selected.exchange}
              symbol={selected.symbol}
              exchange={selected.exchange}
              timeframe={timeframe}
              onPriceUpdate={handlePriceUpdate}
            />
          ) : (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 12 }}>
              Add a symbol to get started
            </div>
          )}
        </div>

        {/* Right: Live public trades */}
        <div style={{ width: 240, flexShrink: 0, borderLeft: `1px solid ${TC.border}`, background: TC.surface, overflow: 'hidden' }}>
          <LiveTradesPanel symbol={selected?.symbol ?? ''} assetType={selected?.asset_type ?? ''} />
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

      {showAccountModal && (
        <PaperAccountModal onClose={() => {
          setShowAccountModal(false)
          // Refresh P&L after potential config change
          api.getPaperAccount().then(a => setPaperPnl(a.realized_pnl)).catch(() => {})
        }}/>
      )}
    </div>
  )
}
