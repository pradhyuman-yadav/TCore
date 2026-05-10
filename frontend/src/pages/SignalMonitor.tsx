import { useWebSocket } from '../hooks/useWebSocket'
import { useStore } from '../store'

const ZONE_COLOR: Record<string, string> = {
  buy: 'text-green-400',
  sell: 'text-red-400',
  neutral: 'text-gray-400',
}

const ACTION_BG: Record<string, string> = {
  buy: 'bg-green-900 text-green-300',
  sell: 'bg-red-900 text-red-300',
  hold: 'bg-surface-border text-gray-400',
}

export default function SignalMonitor() {
  useWebSocket('signals')
  const { signals, wsStatus } = useStore()

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold text-white">Signal Monitor</h1>
        <span className={`text-xs px-2 py-0.5 rounded ${
          wsStatus === 'open' ? 'bg-green-900 text-green-300' :
          wsStatus === 'connecting' ? 'bg-yellow-900 text-yellow-300' :
          'bg-red-900 text-red-300'
        }`}>
          WS {wsStatus}
        </span>
      </div>

      {signals.length === 0 ? (
        <div className="bg-surface-raised border border-surface-border rounded-lg p-8 text-center">
          <p className="text-gray-500">Waiting for signals…</p>
          <p className="text-xs text-gray-600 mt-2">Signals are broadcast here when the trading cycle runs.</p>
        </div>
      ) : (
        <div className="bg-surface-raised border border-surface-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-left border-b border-surface-border bg-surface">
                <th className="px-4 py-2">Time</th>
                <th className="px-4 py-2">Symbol</th>
                <th className="px-4 py-2">Score</th>
                <th className="px-4 py-2">Zone</th>
                <th className="px-4 py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s, i) => (
                <tr key={i} className="border-b border-surface-border/50 hover:bg-surface-border/20">
                  <td className="px-4 py-2 text-gray-400 text-xs">{new Date(s.ts).toLocaleTimeString()}</td>
                  <td className="px-4 py-2 font-mono">{s.symbol}</td>
                  <td className="px-4 py-2 font-mono">{s.score.toFixed(4)}</td>
                  <td className={`px-4 py-2 font-semibold ${ZONE_COLOR[s.zone] ?? 'text-white'}`}>{s.zone}</td>
                  <td className="px-4 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded ${ACTION_BG[s.action] ?? 'bg-surface-border text-gray-300'}`}>
                      {s.action}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
