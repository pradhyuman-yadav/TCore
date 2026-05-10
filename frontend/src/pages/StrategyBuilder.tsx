import { useEffect, useState } from 'react'
import { api, StrategyRow } from '../api'
import { useStore } from '../store'

const TEMPLATE = {
  symbol: 'BTC/USDT',
  exchange: 'binance',
  timeframe: '1h',
  refresh_cadence_seconds: 300,
  indicators: {
    rsi: { weight: 0.2 },
    macd_hist: { weight: 0.15 },
    bb_position: { weight: 0.1 },
    ema_cross: { weight: 0.1, params: { fast: 12, slow: 26 } },
    news_sentiment: { weight: 0.25, cache_ttl_minutes: 15 },
    social_sentiment: { weight: 0.2, cache_ttl_minutes: 5 },
  },
  rules: { buy_threshold: 0.45, sell_threshold: -0.35 },
  position_sizing: { mode: 'fixed_usdt', amount: 100, max_open_positions: 1 },
  risk: { max_daily_loss_usdt: 200 },
}

export default function StrategyBuilder() {
  const { setActiveStrategy } = useStore()
  const [strategies, setStrategies] = useState<StrategyRow[]>([])
  const [name, setName] = useState('')
  const [configJson, setConfigJson] = useState(JSON.stringify(TEMPLATE, null, 2))
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  async function refresh() {
    const rows = await api.listStrategies().catch(() => [])
    setStrategies(rows)
  }

  useEffect(() => { refresh() }, [])

  async function create() {
    setError('')
    setMsg('')
    try {
      const config = JSON.parse(configJson)
      await api.createStrategy(name, config)
      setMsg('Strategy created.')
      setName('')
      refresh()
    } catch (e: any) {
      setError(e.message)
    }
  }

  async function activate(id: string) {
    try {
      await api.activateStrategy(id)
      const active = await api.getActiveStrategy()
      setActiveStrategy(active)
      setMsg('Strategy activated.')
      refresh()
    } catch (e: any) {
      setError(e.message)
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Strategy Builder</h1>

      {/* Existing strategies */}
      <div className="bg-surface-raised border border-surface-border rounded-lg p-4">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">Strategies</h2>
        {strategies.length === 0 ? (
          <p className="text-gray-500 text-sm">No strategies yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-left border-b border-surface-border">
                <th className="pb-2">Name</th>
                <th className="pb-2">Status</th>
                <th className="pb-2"></th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((s) => (
                <tr key={s.id} className="border-b border-surface-border/50">
                  <td className="py-2">{s.name}</td>
                  <td>
                    <span className={`text-xs px-2 py-0.5 rounded ${s.is_active ? 'bg-green-900 text-green-300' : 'bg-surface-border text-gray-400'}`}>
                      {s.is_active ? 'active' : 'inactive'}
                    </span>
                  </td>
                  <td className="text-right">
                    {!s.is_active && (
                      <button
                        onClick={() => activate(s.id)}
                        className="text-xs px-3 py-1 bg-brand hover:bg-brand-dark rounded text-white"
                      >
                        Activate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Create new */}
      <div className="bg-surface-raised border border-surface-border rounded-lg p-4 space-y-3">
        <h2 className="text-sm font-semibold text-gray-300">Create Strategy</h2>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Strategy name"
          className="w-full bg-surface border border-surface-border rounded px-3 py-2 text-sm text-white"
        />
        <textarea
          value={configJson}
          onChange={(e) => setConfigJson(e.target.value)}
          rows={18}
          className="w-full bg-surface border border-surface-border rounded px-3 py-2 text-sm text-white font-mono resize-y"
        />
        {error && <p className="text-red-400 text-sm">{error}</p>}
        {msg && <p className="text-green-400 text-sm">{msg}</p>}
        <button
          onClick={create}
          disabled={!name.trim()}
          className="px-5 py-2 bg-brand hover:bg-brand-dark text-white rounded text-sm font-semibold disabled:opacity-50"
        >
          Create
        </button>
      </div>
    </div>
  )
}
