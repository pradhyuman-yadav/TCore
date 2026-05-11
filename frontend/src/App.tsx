import { useEffect, useState } from 'react'
import { useNavigate, useLocation, Routes, Route, BrowserRouter } from 'react-router-dom'
import { api } from './api'
import { useStore } from './store'
import { TC } from './theme'
import { TCNavbar, TCSidebar, TCKillBanner } from './components/ui'
import Dashboard from './pages/Dashboard'
import ChartView from './pages/ChartView'
import StrategyBuilder from './pages/StrategyBuilder'
import Backtest from './pages/Backtest'
import SignalMonitor from './pages/SignalMonitor'

function AppShell() {
  const { killSwitch, tradingMode, wsStatus, setKillSwitch, setTradingMode, setActiveStrategy, activeStrategy } = useStore()
  const [transitioning, setTransitioning] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    api.getControl().then(({ kill_switch, trading_mode }) => {
      setKillSwitch(kill_switch)
      setTradingMode(trading_mode)
    }).catch(() => {})
    api.getActiveStrategy().then(setActiveStrategy).catch(() => {})
  }, [])

  const handleNavigate = (path: string) => {
    if (path === location.pathname) return
    setTransitioning(true)
    setTimeout(() => {
      navigate(path)
      setTransitioning(false)
    }, 110)
  }

  const handleKillSwitch = (enabled: boolean) => {
    setKillSwitch(enabled)
    api.setKillSwitch(enabled).catch(() => {})
  }

  const strategyName = (activeStrategy?.name as string) ?? ''

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: TC.bg, color: TC.text, fontFamily: TC.fontUI, overflow: 'hidden' }}>
      <TCNavbar
        mode={tradingMode}
        killSwitch={killSwitch}
        setKillSwitch={handleKillSwitch}
        wsOk={wsStatus === 'open'}
        dbOk={true}
        strategyName={strategyName}
      />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
        <TCSidebar activePath={location.pathname} navigate={handleNavigate}/>

        <main style={{ flex: 1, overflow: 'auto', minWidth: 0, opacity: transitioning ? 0 : 1, transition: 'opacity 0.1s ease' }}>
          {killSwitch && <TCKillBanner/>}
          {tradingMode === 'paper' && (
            <div style={{ height: 2, background: 'linear-gradient(90deg, transparent, rgba(255,204,0,0.4), transparent)' }}/>
          )}
          {tradingMode === 'live' && (
            <div style={{ height: 2, background: 'linear-gradient(90deg, transparent, rgba(255,68,68,0.4), transparent)' }}/>
          )}

          <Routes>
            <Route path="/"         element={<Dashboard/>}/>
            <Route path="/chart"    element={<ChartView/>}/>
            <Route path="/strategy" element={<StrategyBuilder/>}/>
            <Route path="/backtest" element={<Backtest/>}/>
            <Route path="/signals"  element={<SignalMonitor/>}/>
          </Routes>
        </main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell/>
    </BrowserRouter>
  )
}
