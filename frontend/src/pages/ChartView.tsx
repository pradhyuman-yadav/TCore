import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { TC } from '../theme'
import { TCBadge, TCSectionHeader } from '../components/ui'

// ── TradingView helpers ─────────────────────────────────────────────────────
const EXCHANGES: Record<string, string> = {
  binanceus: 'BINANCEUS',
  binance:   'BINANCE',
  coinbase:  'COINBASE',
  kraken:    'KRAKEN',
  bybit:     'BYBIT',
}

// BTC/USDT → BTCUSDT
const toTvSymbol = (symbol: string, exchange: string): string => {
  const pair = symbol.replace('/', '')
  const ex   = EXCHANGES[exchange.toLowerCase()] ?? exchange.toUpperCase()
  return `${ex}:${pair}`
}

// 15m → 15, 1h → 60, 4h → 240, 1d → D
const toTvInterval = (tf: string): string => {
  const map: Record<string, string> = {
    '1m': '1', '3m': '3', '5m': '5', '15m': '15', '30m': '30',
    '1h': '60', '2h': '120', '4h': '240', '1d': 'D', '1w': 'W',
  }
  return map[tf] ?? '15'
}

// ── TradingView widget component ────────────────────────────────────────────
declare global {
  interface Window {
    TradingView?: {
      widget: new (config: Record<string, unknown>) => void
    }
  }
}

let tvScriptLoaded = false
let tvScriptCallbacks: Array<() => void> = []

function loadTvScript(cb: () => void) {
  if (tvScriptLoaded) { cb(); return }
  tvScriptCallbacks.push(cb)
  if (tvScriptCallbacks.length > 1) return   // already loading
  const s = document.createElement('script')
  s.src = 'https://s3.tradingview.com/tv.js'
  s.async = true
  s.onload = () => { tvScriptLoaded = true; tvScriptCallbacks.forEach(f => f()); tvScriptCallbacks = [] }
  document.head.appendChild(s)
}

interface TVChartProps {
  symbol: string
  exchange: string
  timeframe: string
  containerId: string
}

function TradingViewChart({ symbol, exchange, timeframe, containerId }: TVChartProps) {
  useEffect(() => {
    const tvSym = toTvSymbol(symbol, exchange)
    const tvItv = toTvInterval(timeframe)

    loadTvScript(() => {
      if (!window.TradingView) return
      // Clear previous widget
      const el = document.getElementById(containerId)
      if (el) el.innerHTML = ''

      new window.TradingView.widget({
        container_id:      containerId,
        autosize:          true,
        symbol:            tvSym,
        interval:          tvItv,
        timezone:          'Etc/UTC',
        theme:             'dark',
        style:             '1',          // candlestick
        locale:            'en',
        toolbar_bg:        TC.surface,
        gridLineColor:     'rgba(255,255,255,0.04)',
        backgroundColor:   TC.bg,
        enable_publishing: false,
        withdateranges:    true,
        hide_side_toolbar: false,
        allow_symbol_change: false,
        save_image:        false,
        studies: [],
        overrides: {
          'mainSeriesProperties.candleStyle.upColor':          TC.green,
          'mainSeriesProperties.candleStyle.downColor':        TC.red,
          'mainSeriesProperties.candleStyle.borderUpColor':    TC.green,
          'mainSeriesProperties.candleStyle.borderDownColor':  TC.red,
          'mainSeriesProperties.candleStyle.wickUpColor':      TC.green,
          'mainSeriesProperties.candleStyle.wickDownColor':    TC.red,
          'paneProperties.background':                         TC.bg,
          'paneProperties.backgroundType':                     'solid',
          'scalesProperties.textColor':                        TC.textMuted,
        },
      })
    })
  }, [symbol, exchange, timeframe, containerId])

  return (
    <div
      id={containerId}
      style={{ width: '100%', height: '100%', minHeight: 400 }}
    />
  )
}

// ── Indicator bar ───────────────────────────────────────────────────────────
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
          position: 'absolute', height: '100%',
          width: `${pctHalf}%`,
          left: value >= 0 ? '50%' : `${50 - pctHalf}%`,
          background: col, borderRadius: 2, boxShadow: `0 0 5px ${col}55`,
        }}/>
        <div style={{ position: 'absolute', left: '50%', top: 0, width: 1, height: '100%', background: TC.borderHi }}/>
      </div>
    </div>
  )
}

// ── ChartView page ──────────────────────────────────────────────────────────
const SYMBOLS      = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT']
const TIMEFRAMES   = ['1m', '5m', '15m', '1h', '4h', '1d']
const EXCHANGE_LIST = ['binanceus', 'binance', 'coinbase', 'kraken']

export default function ChartView() {
  const [symbol,     setSymbol]     = useState('BTC/USDT')
  const [exchange,   setExchange]   = useState('binanceus')
  const [timeframe,  setTimeframe]  = useState('15m')
  const [syncing,    setSyncing]    = useState(false)
  const [syncDays,   setSyncDays]   = useState(90)
  const [syncResult, setSyncResult] = useState<string | null>(null)
  const [score] = useState(0.67)
  const chartId = useRef(`tv_${Math.random().toString(36).slice(2)}`).current

  const zone = score > 0.3 ? 'BUY' : score < -0.3 ? 'SELL' : 'NEUTRAL'

  const handleSync = async () => {
    setSyncing(true)
    setSyncResult(null)
    try {
      const res = await api.syncMarket(symbol, exchange, timeframe, syncDays)
      setSyncResult(`✓ ${res.upserted} bars stored`)
    } catch (e: unknown) {
      setSyncResult(`✗ ${e instanceof Error ? e.message : 'Sync failed'}`)
    }
    setSyncing(false)
  }

  const pillBtn = (active: boolean): React.CSSProperties => ({
    padding: '4px 12px', borderRadius: 5, cursor: 'pointer',
    border: `1px solid ${active ? TC.accent : TC.border}`,
    background: active ? TC.accentDim : 'transparent',
    color: active ? TC.accent : TC.textMid,
    fontFamily: TC.fontMono, fontSize: 11.5, fontWeight: active ? 600 : 400,
    transition: 'all 0.12s',
  })

  const tfBtn = (active: boolean): React.CSSProperties => ({
    padding: '3px 9px', borderRadius: 4, cursor: 'pointer', border: 'none',
    background: active ? TC.surface3 : 'transparent',
    color: active ? TC.text : TC.textMuted,
    fontFamily: TC.fontMono, fontSize: 11, fontWeight: active ? 600 : 400,
    transition: 'all 0.12s',
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

      {/* Controls bar */}
      <div style={{
        padding: '10px 18px', borderBottom: `1px solid ${TC.border}`,
        display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0,
        background: TC.surface, flexWrap: 'wrap',
      }}>
        {/* Symbol pills */}
        <div style={{ display: 'flex', gap: 5 }}>
          {SYMBOLS.map(s => (
            <button key={s} onClick={() => setSymbol(s)} style={pillBtn(symbol === s)}>{s}</button>
          ))}
        </div>

        <div style={{ width: 1, height: 18, background: TC.border }}/>

        {/* Timeframe pills */}
        <div style={{ display: 'flex', gap: 3 }}>
          {TIMEFRAMES.map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)} style={tfBtn(timeframe === tf)}>{tf}</button>
          ))}
        </div>

        <div style={{ width: 1, height: 18, background: TC.border }}/>

        {/* Exchange selector */}
        <select
          value={exchange}
          onChange={e => setExchange(e.target.value)}
          style={{
            padding: '4px 8px', background: TC.surface2, border: `1px solid ${TC.border}`,
            borderRadius: 4, color: TC.textMid, fontFamily: TC.fontMono, fontSize: 11, cursor: 'pointer',
          }}
        >
          {EXCHANGE_LIST.map(ex => <option key={ex} value={ex}>{ex}</option>)}
        </select>

        <div style={{ width: 1, height: 18, background: TC.border }}/>

        {/* DB sync (for indicator calculations) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <select
            value={syncDays}
            onChange={e => setSyncDays(Number(e.target.value))}
            style={{
              padding: '4px 8px', background: TC.surface2, border: `1px solid ${TC.border}`,
              borderRadius: 4, color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 11, cursor: 'pointer',
            }}
          >
            {[7, 30, 90, 180, 365].map(d => <option key={d} value={d}>{d}d</option>)}
          </select>
          <button onClick={handleSync} disabled={syncing} style={{
            padding: '4px 14px', borderRadius: 5, cursor: syncing ? 'not-allowed' : 'pointer',
            border: `1px solid ${TC.border}`,
            background: 'transparent',
            color: syncing ? TC.textMuted : TC.textMid,
            fontFamily: TC.fontMono, fontSize: 10, fontWeight: 700, transition: 'all 0.15s',
          }} title="Sync OHLCV to local DB (used by indicator engine)">
            {syncing ? '⟳ Syncing…' : '⟳ DB Sync'}
          </button>
          {syncResult && (
            <span style={{ color: syncResult.startsWith('✓') ? TC.green : TC.red, fontSize: 10, fontFamily: TC.fontMono }}>
              {syncResult}
            </span>
          )}
        </div>

        {/* Zone + score */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
          <TCBadge variant={zone === 'BUY' ? 'buy' : zone === 'SELL' ? 'sell' : 'neutral'}>{zone} ZONE</TCBadge>
          <span style={{
            color: zone === 'BUY' ? TC.green : zone === 'SELL' ? TC.red : TC.textMid,
            fontFamily: TC.fontMono, fontSize: 18, fontWeight: 700,
          }}>
            {score > 0 ? '+' : ''}{score.toFixed(3)}
          </span>
        </div>
      </div>

      {/* TradingView chart — live data straight from exchange */}
      <div style={{ flex: 1, minHeight: 400, position: 'relative', background: TC.bg }}>
        <TradingViewChart
          symbol={symbol}
          exchange={exchange}
          timeframe={timeframe}
          containerId={chartId}
        />
      </div>

      {/* Indicator panel */}
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
    </div>
  )
}
