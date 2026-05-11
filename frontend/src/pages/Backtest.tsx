import { useEffect, useRef, useState } from 'react'
import { createChart, IChartApi, Time } from 'lightweight-charts'
import { api, BacktestResult, BacktestTrade } from '../api'
import { TC } from '../theme'
import { TCCard, TCBadge, TCSectionHeader, TCTable, ColDef } from '../components/ui'

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <TCCard style={{ flex: 1, padding: '14px 16px', textAlign: 'center' }}>
      <div style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 10 }}>{label}</div>
      <div style={{ color: color ?? TC.text, fontFamily: TC.fontMono, fontSize: 21, fontWeight: 700 }}>{value}</div>
    </TCCard>
  )
}

function EquityChart({ curve, capital }: { curve: number[]; capital: number }) {
  const ref  = useRef<HTMLDivElement>(null)
  const inst = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!ref.current || curve.length === 0) return
    if (inst.current) { inst.current.remove(); inst.current = null }

    const chart = createChart(ref.current, {
      layout: { background: { color: TC.bg }, textColor: TC.textMuted, fontFamily: TC.fontMono, fontSize: 11 },
      grid: { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
      crosshair: {
        vertLine: { color: TC.accent + '66', labelBackgroundColor: TC.surface2 },
        horzLine: { color: TC.accent + '66', labelBackgroundColor: TC.surface2 },
      },
      rightPriceScale: { borderColor: TC.border },
      timeScale: { borderColor: TC.border, timeVisible: false },
      width: ref.current.clientWidth,
      height: 210,
    })

    const series = chart.addLineSeries({ color: TC.accent, lineWidth: 2, priceLineVisible: false })
    const baseline = chart.addLineSeries({ color: TC.border, lineWidth: 1, lineStyle: 2, priceLineVisible: false, crosshairMarkerVisible: false })

    const now = Math.floor(Date.now() / 1000)
    const step = 86400
    const data = curve.map((v, i) => ({ time: (now - (curve.length - i) * step) as Time, value: v }))
    series.setData(data)
    baseline.setData([{ time: data[0].time, value: capital }, { time: data[data.length - 1].time, value: capital }])
    chart.timeScale().fitContent()
    inst.current = chart

    const ro = new ResizeObserver(() => { inst.current?.applyOptions({ width: ref.current!.clientWidth }) })
    ro.observe(ref.current)
    return () => { ro.disconnect(); inst.current?.remove(); inst.current = null }
  }, [curve, capital])

  return <div ref={ref} style={{ width: '100%' }}/>
}

const inputStyle: React.CSSProperties = {
  padding: '7px 10px', background: TC.surface2, border: `1px solid ${TC.border}`,
  borderRadius: 5, color: TC.text, fontFamily: TC.fontMono, fontSize: 12, outline: 'none',
}

export default function Backtest() {
  const [symbol,     setSymbol]     = useState('BTC/USDT')
  const [exchange,   setExchange]   = useState('binance')
  const [dateFrom,   setDateFrom]   = useState('2025-01-01')
  const [dateTo,     setDateTo]     = useState('2025-04-01')
  const [capital,    setCapital]    = useState(10000)
  const [running,    setRunning]    = useState(false)
  const [result,     setResult]     = useState<BacktestResult | null>(null)

  const run = async () => {
    setRunning(true)
    try {
      const res = await api.runBacktest({ symbol, exchange, initial_capital: capital })
      setResult(res)
    } catch { /* ignore */ }
    setRunning(false)
  }

  const tradeColumns: ColDef<BacktestTrade>[] = [
    { key: 'time',     label: 'Time',    render: v => <span style={{ fontFamily: TC.fontMono, color: TC.textMuted, fontSize: 11 }}>{v ? new Date(String(v)).toLocaleString() : '—'}</span> },
    { key: 'side',     label: 'Side',    render: v => <TCBadge variant={String(v).toUpperCase() === 'BUY' ? 'buy' : 'sell'}>{String(v)}</TCBadge> },
    { key: 'price',    label: 'Price',   right: true, render: v => <span style={{ fontFamily: TC.fontMono }}>${Number(v).toLocaleString()}</span> },
    { key: 'quantity', label: 'Qty',     right: true, render: v => <span style={{ fontFamily: TC.fontMono }}>{Number(v).toFixed(4)}</span> },
    { key: 'pnl',      label: 'P&L',     right: true, render: v => (
      <span style={{ fontFamily: TC.fontMono, color: Number(v) >= 0 ? TC.green : TC.red, fontWeight: 600 }}>
        {Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}
      </span>
    )},
  ]

  return (
    <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Controls */}
      <TCCard style={{ padding: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, flexWrap: 'wrap' }}>
          <div>
            <div style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono, letterSpacing: '0.08em', marginBottom: 5, textTransform: 'uppercase' }}>Symbol</div>
            <input value={symbol} onChange={e => setSymbol(e.target.value)} style={inputStyle}/>
          </div>
          <div>
            <div style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono, letterSpacing: '0.08em', marginBottom: 5, textTransform: 'uppercase' }}>From</div>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ ...inputStyle, colorScheme: 'dark' }}/>
          </div>
          <div>
            <div style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono, letterSpacing: '0.08em', marginBottom: 5, textTransform: 'uppercase' }}>To</div>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ ...inputStyle, colorScheme: 'dark' }}/>
          </div>
          <div>
            <div style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono, letterSpacing: '0.08em', marginBottom: 5, textTransform: 'uppercase' }}>Initial Capital (USDT)</div>
            <input type="number" value={capital} onChange={e => setCapital(parseFloat(e.target.value) || 10000)}
              style={{ ...inputStyle, color: TC.accent, width: 150 }}/>
          </div>
          <button onClick={run} disabled={running} style={{
            marginLeft: 'auto', padding: '8px 22px', borderRadius: 5, cursor: running ? 'not-allowed' : 'pointer',
            background: running ? TC.surface2 : TC.accent,
            border: `1px solid ${running ? TC.border : TC.accent}`,
            color: running ? TC.textMid : TC.bg,
            fontFamily: TC.fontMono, fontSize: 11, fontWeight: 700, letterSpacing: '0.06em',
            transition: 'all 0.2s',
          }}>
            {running ? 'RUNNING…' : '▶ RUN BACKTEST'}
          </button>
        </div>
      </TCCard>

      {result && (
        <>
          <div style={{ display: 'flex', gap: 10 }}>
            <StatCard label="Total Return"  value={`+${result.total_pnl.toFixed(2)}`}        color={TC.green}/>
            <StatCard label="Sharpe Ratio"  value={result.sharpe_ratio?.toFixed(2) ?? '—'}   color={TC.accent}/>
            <StatCard label="Win Rate"      value={`${(result.win_rate * 100).toFixed(1)}%`}  color={TC.green}/>
            <StatCard label="Max Drawdown"  value={`${(result.max_drawdown * 100).toFixed(1)}%`} color={TC.red}/>
            <StatCard label="Total Trades"  value={String(result.num_trades)}/>
          </div>

          <TCCard>
            <TCSectionHeader title="Equity Curve" right={
              <span style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono }}>Initial: ${capital.toLocaleString()}</span>
            }/>
            <EquityChart curve={result.equity_curve} capital={capital}/>
          </TCCard>

          <TCCard>
            <TCSectionHeader title="Trade Log" right={<TCBadge>{result.trades.length} trades</TCBadge>}/>
            <TCTable columns={tradeColumns} rows={result.trades} emptyMsg="No trades"/>
          </TCCard>
        </>
      )}

      {!result && !running && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 13 }}>
          Configure parameters and click Run Backtest
        </div>
      )}
    </div>
  )
}
