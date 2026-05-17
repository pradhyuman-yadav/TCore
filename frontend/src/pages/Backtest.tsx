import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { createChart, IChartApi, Time } from 'lightweight-charts'
import { api, BacktestResult, BacktestTrade, StrategyDetail, StrategyRow } from '../api'
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
  width: '100%', boxSizing: 'border-box',
}

const labelStyle: React.CSSProperties = {
  color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono,
  letterSpacing: '0.08em', marginBottom: 5, textTransform: 'uppercase',
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={labelStyle}>{label}</div>
      {children}
    </div>
  )
}

export default function Backtest() {
  const location = useLocation()

  // Strategy picker
  const [strategies,      setStrategies]      = useState<StrategyRow[]>([])
  const [selectedStrat,   setSelectedStrat]   = useState<string>('')
  const [stratDetail,     setStratDetail]     = useState<StrategyDetail | null>(null)
  const [loadingStrat,    setLoadingStrat]    = useState(false)

  // Run params
  const [symbol,    setSymbol]    = useState('BTC/USDT')
  const [exchange,  setExchange]  = useState('binanceus')
  const [timeframe, setTimeframe] = useState('1h')
  const [dateFrom,  setDateFrom]  = useState('')
  const [dateTo,    setDateTo]    = useState('')
  const [capital,   setCapital]   = useState(10000)
  const [feeRate,   setFeeRate]   = useState(0.1)        // percent, e.g. 0.1 = 0.1%
  const [slipBps,   setSlipBps]   = useState(5)

  // Results
  const [running, setRunning] = useState(false)
  const [result,  setResult]  = useState<BacktestResult | null>(null)
  const [error,   setError]   = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)

  // Load strategies on mount
  useEffect(() => {
    api.listStrategies().then(rows => {
      setStrategies(rows)
      // Check if navigated from StrategyBuilder with a strategy ID
      const params = new URLSearchParams(location.search)
      const preselect = params.get('strategy') ?? rows.find(r => r.is_active)?.id ?? ''
      if (preselect) setSelectedStrat(preselect)
    }).catch(() => {})
  }, [location.search])

  // Fetch full config when strategy changes
  useEffect(() => {
    if (!selectedStrat) { setStratDetail(null); return }
    setLoadingStrat(true)
    api.getStrategy(selectedStrat)
      .then(d => {
        setStratDetail(d)
        // Auto-fill symbol / exchange / timeframe from strategy config
        const cfg = d.config
        if (cfg.symbol)    setSymbol(String(cfg.symbol))
        if (cfg.exchange)  setExchange(String(cfg.exchange))
        if (cfg.timeframe) setTimeframe(String(cfg.timeframe))
      })
      .catch(() => setStratDetail(null))
      .finally(() => setLoadingStrat(false))
  }, [selectedStrat])

  const run = async () => {
    setRunning(true)
    setError(null)
    setWarning(null)
    try {
      const body = {
        symbol,
        exchange,
        timeframe,
        initial_capital: capital,
        fee_rate: feeRate / 100,     // convert percent → decimal
        slippage_bps: slipBps,
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo   ? { date_to:   dateTo   } : {}),
        ...(stratDetail ? { strategy_config: stratDetail.config } : {}),
      }
      const res = await api.runBacktest(body)
      setResult(res)
      if (res.bars_capped) {
        setWarning(`Dataset capped at ${res.bars_used} bars (most recent). Use a smaller date range or larger timeframe to backtest more history.`)
      }
    } catch (e: unknown) {
      const raw = e instanceof Error ? e.message : 'Run failed'
      // api.ts already stripped HTML and extracted JSON detail — just relay it
      if (raw.startsWith('504')) {
        setError('Timed out (504). The server took too long. Sync data first: ChartView → select symbol → ⟳ DB Sync.')
      } else {
        setError(raw.replace(/^\d{3} /, ''))  // strip leading "422 " etc.
      }
    }
    setRunning(false)
  }

  const pnlColor = result && result.total_pnl >= 0 ? TC.green : TC.red

  const tradeColumns: ColDef<BacktestTrade>[] = [
    { key: 'time',     label: 'Time',    render: v => <span style={{ fontFamily: TC.fontMono, color: TC.textMuted, fontSize: 11 }}>{v ? new Date(String(v)).toLocaleString() : '—'}</span> },
    { key: 'side',     label: 'Side',    render: v => <TCBadge variant={String(v).toUpperCase() === 'BUY' ? 'buy' : 'sell'}>{String(v)}</TCBadge> },
    { key: 'price',    label: 'Price',   right: true, render: v => <span style={{ fontFamily: TC.fontMono }}>${Number(v).toLocaleString()}</span> },
    { key: 'quantity', label: 'Qty',     right: true, render: v => <span style={{ fontFamily: TC.fontMono }}>{Number(v).toFixed(4)}</span> },
    { key: 'pnl',      label: 'P&L',     right: true, render: v => (
      v == null ? <span style={{ color: TC.textMuted, fontFamily: TC.fontMono }}>—</span> : (
        <span style={{ fontFamily: TC.fontMono, color: Number(v) >= 0 ? TC.green : TC.red, fontWeight: 600 }}>
          {Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}
        </span>
      )
    )},
  ]

  return (
    <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* ── Controls card ── */}
      <TCCard style={{ padding: 16 }}>

        {/* Row 1: Strategy picker */}
        <div style={{ marginBottom: 14, display: 'flex', alignItems: 'flex-end', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={labelStyle}>Strategy</div>
            <select
              value={selectedStrat}
              onChange={e => setSelectedStrat(e.target.value)}
              style={{ ...inputStyle, color: selectedStrat ? TC.accent : TC.textMuted }}
            >
              <option value="">— select a strategy (or fill manually) —</option>
              {strategies.map(s => (
                <option key={s.id} value={s.id}>
                  {s.name}{s.is_active ? '  ★ active' : ''}
                </option>
              ))}
            </select>
          </div>
          {loadingStrat && (
            <span style={{ color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 10, paddingBottom: 10 }}>loading…</span>
          )}
          {stratDetail && (
            <TCBadge variant="accent" >{stratDetail.name}</TCBadge>
          )}
        </div>

        {/* Row 2: Symbol / Exchange / Timeframe / Dates */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
          <div style={{ flex: '1 1 120px' }}>
            <Field label="Symbol">
              <input value={symbol} onChange={e => setSymbol(e.target.value)} style={inputStyle}/>
            </Field>
          </div>
          <div style={{ flex: '1 1 120px' }}>
            <Field label="Exchange">
              <input value={exchange} onChange={e => setExchange(e.target.value)} style={inputStyle}/>
            </Field>
          </div>
          <div style={{ flex: '0 1 90px' }}>
            <Field label="Timeframe">
              <select value={timeframe} onChange={e => setTimeframe(e.target.value)} style={inputStyle}>
                {['1m','5m','15m','30m','1h','4h','1d'].map(t => <option key={t}>{t}</option>)}
              </select>
            </Field>
          </div>
          <div style={{ flex: '0 1 140px' }}>
            <Field label="From (optional)">
              <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                style={{ ...inputStyle, colorScheme: 'dark' }}/>
            </Field>
          </div>
          <div style={{ flex: '0 1 140px' }}>
            <Field label="To (optional)">
              <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                style={{ ...inputStyle, colorScheme: 'dark' }}/>
            </Field>
          </div>
        </div>

        {/* Row 3: Capital / Fees / Slippage / Run */}
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap', borderTop: `1px solid ${TC.border}`, paddingTop: 14 }}>
          <div style={{ flex: '0 1 160px' }}>
            <Field label="Initial Capital (USDT)">
              <input type="number" value={capital}
                onChange={e => setCapital(parseFloat(e.target.value) || 10000)}
                style={{ ...inputStyle, color: TC.accent }}/>
            </Field>
          </div>
          <div style={{ flex: '0 1 130px' }}>
            <Field label="Fee Rate (%)">
              <input type="number" value={feeRate} step={0.01} min={0} max={5}
                onChange={e => setFeeRate(parseFloat(e.target.value) || 0)}
                style={{ ...inputStyle, color: TC.textMid }}
                placeholder="0.1"/>
            </Field>
          </div>
          <div style={{ flex: '0 1 130px' }}>
            <Field label="Slippage (bps)">
              <input type="number" value={slipBps} step={1} min={0} max={500}
                onChange={e => setSlipBps(parseInt(e.target.value) || 0)}
                style={{ ...inputStyle, color: TC.textMid }}
                placeholder="5"/>
            </Field>
          </div>
          <div style={{ flex: 1 }}/>
          <button onClick={run} disabled={running} style={{
            padding: '8px 26px', borderRadius: 5, cursor: running ? 'not-allowed' : 'pointer',
            background: running ? TC.surface2 : TC.accent,
            border: `1px solid ${running ? TC.border : TC.accent}`,
            color: running ? TC.textMid : TC.bg,
            fontFamily: TC.fontMono, fontSize: 11, fontWeight: 700, letterSpacing: '0.06em',
            transition: 'all 0.2s', whiteSpace: 'nowrap',
          }}>
            {running ? 'RUNNING…' : '▶ RUN BACKTEST'}
          </button>
        </div>

        {error && (
          <div style={{ marginTop: 10, color: TC.red, fontFamily: TC.fontMono, fontSize: 11 }}>
            ✗ {error}
          </div>
        )}
      </TCCard>

      {warning && (
        <div style={{ padding: '8px 14px', background: 'rgba(255,204,0,0.07)', border: `1px solid rgba(255,204,0,0.2)`, borderRadius: 5, color: TC.yellow, fontFamily: TC.fontMono, fontSize: 11 }}>
          ⚠ {warning}
        </div>
      )}

      {result && (
        <>
          <div style={{ display: 'flex', gap: 10 }}>
            <StatCard label="Total Return"  value={`${result.total_pnl >= 0 ? '+' : ''}$${result.total_pnl.toFixed(2)}`} color={pnlColor}/>
            <StatCard label="Sharpe Ratio"  value={result.sharpe_ratio?.toFixed(2) ?? '—'}   color={TC.accent}/>
            <StatCard label="Win Rate"      value={`${(result.win_rate * 100).toFixed(1)}%`}  color={TC.green}/>
            <StatCard label="Max Drawdown"  value={`${(result.max_drawdown * 100).toFixed(1)}%`} color={TC.red}/>
            <StatCard label="Total Trades"  value={String(result.num_trades)}/>
          </div>

          <TCCard>
            <TCSectionHeader title="Equity Curve" right={
              <span style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono }}>
                {result.bars_used} bars · Initial: ${capital.toLocaleString()}
              </span>
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
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, gap: 10, color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 12, padding: 40 }}>
          <span style={{ fontSize: 28, opacity: 0.2 }}>◈</span>
          <span>Pick a strategy above or fill params manually, then click ▶ Run Backtest</span>
          <span style={{ fontSize: 10, opacity: 0.6 }}>Historical data will be auto-fetched if not in DB</span>
        </div>
      )}
    </div>
  )
}
