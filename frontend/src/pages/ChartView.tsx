import { useEffect, useRef, useState } from 'react'
import { createChart, IChartApi, ISeriesApi, CandlestickData, Time } from 'lightweight-charts'
import { api, OhlcvBar } from '../api'
import { TC } from '../theme'
import { TCCard, TCBadge, TCSectionHeader } from '../components/ui'

const SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d']

const INDICATORS = [
  { key: 'rsi',       label: 'RSI',          weight: 0.25 },
  { key: 'macd',      label: 'MACD',         weight: 0.20 },
  { key: 'bb',        label: 'BB Position',  weight: 0.15 },
  { key: 'ema',       label: 'EMA Cross',    weight: 0.20 },
  { key: 'volume',    label: 'Volume Surge', weight: 0.10 },
  { key: 'sentiment', label: 'Sentiment',    weight: 0.10 },
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
            x{weight.toFixed(2)}={Number(contrib) > 0 ? '+' : ''}{contrib}
          </span>
        </div>
      </div>
      <div style={{ position: 'relative', height: 3, background: TC.surface2, borderRadius: 2 }}>
        <div style={{
          position: 'absolute', height: '100%',
          width: `${pctHalf}%`,
          left: value >= 0 ? '50%' : `${50 - pctHalf}%`,
          background: col, borderRadius: 2,
          boxShadow: `0 0 5px ${col}55`,
        }}/>
        <div style={{ position: 'absolute', left: '50%', top: 0, width: 1, height: '100%', background: TC.borderHi }}/>
      </div>
    </div>
  )
}

export default function ChartView() {
  const [symbol, setSymbol]       = useState('BTC/USDT')
  const [timeframe, setTimeframe] = useState('15m')
  const [score] = useState(0.67)
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<IChartApi | null>(null)
  const seriesRef    = useRef<ISeriesApi<'Candlestick'> | null>(null)

  const zone = score > 0.3 ? 'BUY' : score < -0.3 ? 'SELL' : 'NEUTRAL'

  useEffect(() => {
    if (!containerRef.current) return
    if (chartRef.current) { chartRef.current.remove(); chartRef.current = null }

    const chart = createChart(containerRef.current, {
      layout: { background: { color: TC.bg }, textColor: TC.textMuted, fontFamily: TC.fontMono, fontSize: 11 },
      grid: {
        vertLines: { color: 'rgba(255,255,255,0.04)' },
        horzLines: { color: 'rgba(255,255,255,0.04)' },
      },
      crosshair: {
        vertLine: { color: TC.accent + '66', labelBackgroundColor: TC.surface2 },
        horzLine: { color: TC.accent + '66', labelBackgroundColor: TC.surface2 },
      },
      rightPriceScale: { borderColor: TC.border },
      timeScale: { borderColor: TC.border, timeVisible: true },
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

    api.getOhlcv(symbol, 'binance', timeframe, 200).then((bars: OhlcvBar[]) => {
      const data: CandlestickData[] = bars.map(b => ({
        time:  (new Date(b.time).getTime() / 1000) as Time,
        open:  b.open, high: b.high, low: b.low, close: b.close,
      }))
      series.setData(data)
      chart.timeScale().fitContent()
    }).catch(() => {})

    const ro = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight })
      }
    })
    ro.observe(containerRef.current)
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null }
  }, [symbol, timeframe])

  const pillBtn = (active: boolean) => ({
    padding: '4px 12px', borderRadius: 5, cursor: 'pointer',
    border: `1px solid ${active ? TC.accent : TC.border}`,
    background: active ? TC.accentDim : 'transparent',
    color: active ? TC.accent : TC.textMid,
    fontFamily: TC.fontMono, fontSize: 11.5, fontWeight: active ? 600 : 400,
    transition: 'all 0.12s',
  } as React.CSSProperties)

  const tfBtn = (active: boolean) => ({
    padding: '3px 9px', borderRadius: 4, cursor: 'pointer', border: 'none',
    background: active ? TC.surface3 : 'transparent',
    color: active ? TC.text : TC.textMuted,
    fontFamily: TC.fontMono, fontSize: 11, fontWeight: active ? 600 : 400,
    transition: 'all 0.12s',
  } as React.CSSProperties)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Controls */}
      <div style={{
        padding: '10px 18px', borderBottom: `1px solid ${TC.border}`,
        display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0,
        background: TC.surface,
      }}>
        <div style={{ display: 'flex', gap: 5 }}>
          {SYMBOLS.map(s => <button key={s} onClick={() => setSymbol(s)} style={pillBtn(symbol === s)}>{s}</button>)}
        </div>
        <div style={{ width: 1, height: 18, background: TC.border }}/>
        <div style={{ display: 'flex', gap: 3 }}>
          {TIMEFRAMES.map(tf => <button key={tf} onClick={() => setTimeframe(tf)} style={tfBtn(timeframe === tf)}>{tf}</button>)}
        </div>
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

      {/* Chart */}
      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        <div ref={containerRef} style={{ width: '100%', height: '100%' }}/>
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
            <IndicatorBar key={ind.key} label={ind.label} value={0.55} weight={ind.weight}/>
          ))}
        </div>
      </div>
    </div>
  )
}
