import { useRef, useState } from 'react'
import { createChart } from 'lightweight-charts'
import { api, BacktestResult } from '../api'
import { useStore } from '../store'

export default function Backtest() {
  const { activeStrategy } = useStore()
  const [symbol, setSymbol] = useState((activeStrategy?.symbol as string) ?? 'BTC/USDT')
  const [exchange, setExchange] = useState((activeStrategy?.exchange as string) ?? 'binance')
  const [capital, setCapital] = useState('10000')
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const chartRef = useRef<HTMLDivElement>(null)

  async function run() {
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await api.runBacktest({
        symbol,
        exchange,
        initial_capital: parseFloat(capital) || 10000,
        strategy_config: activeStrategy ?? undefined,
      })
      setResult(res)
      setTimeout(() => renderEquityCurve(res), 50)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function renderEquityCurve(res: BacktestResult) {
    if (!chartRef.current || res.equity_curve.length === 0) return
    chartRef.current.innerHTML = ''
    const chart = createChart(chartRef.current, {
      layout: { background: { color: '#1e1e2e' }, textColor: '#9ca3af' },
      grid: { vertLines: { color: '#383852' }, horzLines: { color: '#383852' } },
      width: chartRef.current.clientWidth,
      height: 260,
    })
    const series = chart.addLineSeries({ color: '#6366f1', lineWidth: 2 })
    const data = res.equity_curve.map((v, i) => ({ time: (i + 1) as any, value: v }))
    series.setData(data)
    chart.timeScale().fitContent()
  }

  const pct = (v: number) => `${(v * 100).toFixed(2)}%`

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Backtest</h1>

      <div className="bg-surface-raised border border-surface-border rounded-lg p-4 flex flex-wrap gap-4 items-end">
        <label className="flex flex-col gap-1 text-xs text-gray-400">
          Symbol
          <input value={symbol} onChange={(e) => setSymbol(e.target.value)}
            className="bg-surface border border-surface-border rounded px-3 py-1.5 text-sm text-white w-36" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-400">
          Exchange
          <input value={exchange} onChange={(e) => setExchange(e.target.value)}
            className="bg-surface border border-surface-border rounded px-3 py-1.5 text-sm text-white w-28" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-400">
          Initial Capital ($)
          <input value={capital} onChange={(e) => setCapital(e.target.value)} type="number"
            className="bg-surface border border-surface-border rounded px-3 py-1.5 text-sm text-white w-32" />
        </label>
        <button onClick={run} disabled={loading}
          className="px-5 py-2 bg-brand hover:bg-brand-dark text-white rounded text-sm font-semibold disabled:opacity-50">
          {loading ? 'Running…' : 'Run Backtest'}
        </button>
      </div>

      {!activeStrategy && (
        <p className="text-yellow-400 text-sm">No active strategy — activate one in Strategy Builder first.</p>
      )}

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {result && (
        <div className="space-y-4">
          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Total Bars" value={String(result.total_bars)} />
            <Stat label="Trades" value={String(result.num_trades)} />
            <Stat label="Total PnL" value={`$${result.total_pnl.toFixed(2)}`} positive={result.total_pnl >= 0} />
            <Stat label="Win Rate" value={pct(result.win_rate)} positive={result.win_rate >= 0.5} />
            <Stat label="Max Drawdown" value={pct(result.max_drawdown)} positive={false} />
            <Stat label="Sharpe" value={result.sharpe_ratio !== null ? result.sharpe_ratio.toFixed(2) : '—'} positive={(result.sharpe_ratio ?? 0) > 1} />
          </div>

          {/* Equity curve */}
          <div className="bg-surface-raised border border-surface-border rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-300 mb-3">Equity Curve</h2>
            <div ref={chartRef} className="w-full" />
          </div>

          {/* Trade log */}
          <div className="bg-surface-raised border border-surface-border rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-300 mb-3">Trade Log ({result.trades.length})</h2>
            <div className="overflow-x-auto max-h-64 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-surface-raised">
                  <tr className="text-gray-400 text-left border-b border-surface-border">
                    <th className="pb-2">Bar</th>
                    <th className="pb-2">Side</th>
                    <th className="pb-2">Price</th>
                    <th className="pb-2">Qty</th>
                    <th className="pb-2">PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, i) => (
                    <tr key={i} className="border-b border-surface-border/30">
                      <td className="py-1">{t.bar_index}</td>
                      <td className={t.side === 'buy' ? 'text-green-400' : 'text-red-400'}>{t.side}</td>
                      <td>${t.price.toLocaleString()}</td>
                      <td>{t.quantity.toFixed(6)}</td>
                      <td className={t.pnl === null ? 'text-gray-500' : t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                        {t.pnl === null ? '—' : `$${t.pnl.toFixed(2)}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  return (
    <div className="bg-surface-raised border border-surface-border rounded-lg p-3">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p className={`text-sm font-semibold ${positive === undefined ? 'text-white' : positive ? 'text-green-400' : 'text-red-400'}`}>{value}</p>
    </div>
  )
}
