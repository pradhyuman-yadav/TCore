import { useEffect } from 'react'
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { useStore } from './store'
import Dashboard from './pages/Dashboard'
import ChartView from './pages/ChartView'
import StrategyBuilder from './pages/StrategyBuilder'
import Backtest from './pages/Backtest'
import SignalMonitor from './pages/SignalMonitor'

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/chart', label: 'Chart' },
  { to: '/strategy', label: 'Strategy' },
  { to: '/backtest', label: 'Backtest' },
  { to: '/signals', label: 'Signals' },
]

function NavBar() {
  const { killSwitch, tradingMode, wsStatus } = useStore()

  return (
    <nav className="flex items-center gap-1 px-4 h-12 bg-surface-raised border-b border-surface-border shrink-0">
      <span className="font-bold text-brand mr-4 text-sm tracking-widest">TRADECORE</span>

      {NAV.map(({ to, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            `px-3 py-1 rounded text-sm transition-colors ${
              isActive ? 'bg-brand text-white' : 'text-gray-400 hover:text-white'
            }`
          }
        >
          {label}
        </NavLink>
      ))}

      <div className="ml-auto flex items-center gap-3 text-xs">
        <span className={`px-2 py-0.5 rounded ${tradingMode === 'live' ? 'bg-yellow-900 text-yellow-300' : 'bg-surface-border text-gray-400'}`}>
          {tradingMode}
        </span>
        {killSwitch && (
          <span className="px-2 py-0.5 rounded bg-red-900 text-red-300 animate-pulse">HALTED</span>
        )}
        <span className={`w-2 h-2 rounded-full ${wsStatus === 'open' ? 'bg-green-400' : wsStatus === 'connecting' ? 'bg-yellow-400' : 'bg-red-500'}`} title={`WS ${wsStatus}`} />
      </div>
    </nav>
  )
}

export default function App() {
  const { setKillSwitch, setTradingMode, setActiveStrategy } = useStore()

  useEffect(() => {
    api.getControl().then(({ kill_switch, trading_mode }) => {
      setKillSwitch(kill_switch)
      setTradingMode(trading_mode)
    }).catch(() => {})

    api.getActiveStrategy().then(setActiveStrategy).catch(() => {})
  }, [])

  return (
    <BrowserRouter>
      <div className="flex flex-col h-screen overflow-hidden">
        <NavBar />
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chart" element={<ChartView />} />
            <Route path="/strategy" element={<StrategyBuilder />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/signals" element={<SignalMonitor />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
