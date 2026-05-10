import { useEffect, useRef, useState } from 'react'
import { createChart, IChartApi } from 'lightweight-charts'
import { api, OhlcvBar } from '../api'

export default function ChartView() {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const [symbol, setSymbol] = useState('BTC/USDT')
  const [exchange, setExchange] = useState('binance')
  const [timeframe, setTimeframe] = useState('1h')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: { background: { color: '#1e1e2e' }, textColor: '#9ca3af' },
      grid: { vertLines: { color: '#383852' }, horzLines: { color: '#383852' } },
      width: containerRef.current.clientWidth,
      height: 480,
      timeScale: { timeVisible: true },
    })
    chartRef.current = chart

    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
    }
  }, [])

  async function load() {
    if (!chartRef.current) return
    setLoading(true)
    setError('')
    try {
      const bars = await api.getOhlcv(symbol, exchange, timeframe, 300)
      const data = bars
        .map((b: OhlcvBar) => ({
          time: Math.floor(new Date(b.time).getTime() / 1000) as any,
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        }))
        .sort((a: any, b: any) => a.time - b.time)

      const series = chartRef.current.addCandlestickSeries({
        upColor: '#4ade80',
        downColor: '#f87171',
        borderVisible: false,
        wickUpColor: '#4ade80',
        wickDownColor: '#f87171',
      })
      series.setData(data)
      chartRef.current.timeScale().fitContent()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function sync() {
    setLoading(true)
    try {
      await api.syncMarket(symbol, exchange)
      await load()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-white">Chart</h1>

      <div className="flex flex-wrap gap-3 items-end">
        <label className="flex flex-col gap-1 text-xs text-gray-400">
          Symbol
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="bg-surface-raised border border-surface-border rounded px-3 py-1.5 text-sm text-white w-36"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-400">
          Exchange
          <input
            value={exchange}
            onChange={(e) => setExchange(e.target.value)}
            className="bg-surface-raised border border-surface-border rounded px-3 py-1.5 text-sm text-white w-28"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-400">
          Timeframe
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="bg-surface-raised border border-surface-border rounded px-3 py-1.5 text-sm text-white"
          >
            {['1m', '5m', '15m', '1h', '4h', '1d'].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <button
          onClick={load}
          disabled={loading}
          className="px-4 py-1.5 bg-brand hover:bg-brand-dark text-white rounded text-sm font-semibold disabled:opacity-50"
        >
          Load
        </button>
        <button
          onClick={sync}
          disabled={loading}
          className="px-4 py-1.5 bg-surface-border hover:bg-gray-600 text-white rounded text-sm font-semibold disabled:opacity-50"
        >
          Sync 30d
        </button>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div
        ref={containerRef}
        className="w-full rounded-lg border border-surface-border overflow-hidden"
      />
    </div>
  )
}
