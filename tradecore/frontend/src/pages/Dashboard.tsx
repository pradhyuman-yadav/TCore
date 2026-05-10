import { useEffect, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'

interface HealthData {
  status: string
  version: string
  db: string
  scheduler: string
  trading_mode: string
  kill_switch: boolean
  active_strategy: string | null
}

export default function Dashboard() {
  const { killSwitch, tradingMode, setKillSwitch, setTradingMode } = useStore()
  const [health, setHealth] = useState<HealthData | null>(null)
  const [positions, setPositions] = useState<unknown[]>([])
  const [trades, setTrades] = useState<unknown[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.health().then((h) => setHealth(h as unknown as HealthData)).catch(() => {})
    api.paperPositions().then(setPositions).catch(() => {})
    api.paperTrades(10).then(setTrades).catch(() => {})
  }, [])

  async function toggleKillSwitch() {
    setBusy(true)
    try {
      await api.setKillSwitch(!killSwitch)
      setKillSwitch(!killSwitch)
    } finally {
      setBusy(false)
    }
  }

  async function toggleMode() {
    const next = tradingMode === 'paper' ? 'live' : 'paper'
    setBusy(true)
    try {
      await api.setTradingMode(next)
      setTradingMode(next)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Dashboard</h1>

      {/* Status cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card label="Backend" value={health?.status ?? '…'} ok={health?.status === 'ok'} />
        <Card label="Database" value={health?.db ?? '…'} ok={health?.db === 'connected'} />
        <Card label="Scheduler" value={health?.scheduler ?? '…'} ok={health?.scheduler === 'running'} />
        <Card label="Strategy" value={health?.active_strategy ?? 'none'} ok={!!health?.active_strategy} />
      </div>

      {/* Controls */}
      <div className="bg-surface-raised border border-surface-border rounded-lg p-4 flex flex-wrap gap-4 items-center">
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-400">Kill Switch</span>
          <button
            onClick={toggleKillSwitch}
            disabled={busy}
            className={`px-4 py-1.5 rounded text-sm font-semibold transition-colors ${
              killSwitch
                ? 'bg-red-600 hover:bg-red-700 text-white'
                : 'bg-surface-border hover:bg-gray-600 text-gray-200'
            }`}
          >
            {killSwitch ? 'ON (HALT)' : 'OFF'}
          </button>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-400">Mode</span>
          <button
            onClick={toggleMode}
            disabled={busy}
            className={`px-4 py-1.5 rounded text-sm font-semibold transition-colors ${
              tradingMode === 'live'
                ? 'bg-yellow-500 hover:bg-yellow-600 text-black'
                : 'bg-brand hover:bg-brand-dark text-white'
            }`}
          >
            {tradingMode.toUpperCase()}
          </button>
        </div>

        <span className="text-xs text-gray-500 ml-auto">v{health?.version ?? '…'}</span>
      </div>

      {/* Open positions */}
      <Section title={`Open Positions (${positions.length})`}>
        {positions.length === 0 ? (
          <p className="text-gray-500 text-sm">No open positions</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-left border-b border-surface-border">
                <th className="pb-2">Symbol</th>
                <th className="pb-2">Side</th>
                <th className="pb-2">Qty</th>
                <th className="pb-2">Entry</th>
              </tr>
            </thead>
            <tbody>
              {(positions as any[]).map((p) => (
                <tr key={p.id} className="border-b border-surface-border/50">
                  <td className="py-1.5">{p.symbol}</td>
                  <td className={p.side === 'buy' ? 'text-green-400' : 'text-red-400'}>{p.side}</td>
                  <td>{p.quantity.toFixed(6)}</td>
                  <td>${p.avg_entry_price.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      {/* Recent trades */}
      <Section title="Recent Trades">
        {trades.length === 0 ? (
          <p className="text-gray-500 text-sm">No trades yet</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-left border-b border-surface-border">
                <th className="pb-2">Symbol</th>
                <th className="pb-2">Side</th>
                <th className="pb-2">Price</th>
                <th className="pb-2">PnL</th>
              </tr>
            </thead>
            <tbody>
              {(trades as any[]).map((t) => (
                <tr key={t.id} className="border-b border-surface-border/50">
                  <td className="py-1.5">{t.symbol}</td>
                  <td className={t.side === 'buy' ? 'text-green-400' : 'text-red-400'}>{t.side}</td>
                  <td>${t.price.toLocaleString()}</td>
                  <td className={t.pnl === null ? 'text-gray-500' : t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {t.pnl === null ? '—' : `$${t.pnl.toFixed(2)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  )
}

function Card({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="bg-surface-raised border border-surface-border rounded-lg p-4">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p className={`text-sm font-semibold truncate ${ok ? 'text-green-400' : 'text-gray-300'}`}>{value}</p>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-surface-raised border border-surface-border rounded-lg p-4">
      <h2 className="text-sm font-semibold text-gray-300 mb-3">{title}</h2>
      {children}
    </div>
  )
}
