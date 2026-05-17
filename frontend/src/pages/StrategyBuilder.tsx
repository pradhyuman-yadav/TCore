import { useEffect, useState } from 'react'
import { api, StrategyRow } from '../api'
import { TC } from '../theme'
import { TCCard, TCBadge, TCSlider, TCInput, TCSelect } from '../components/ui'

const INDICATOR_LABELS: Record<string, string> = {
  rsi: 'RSI', macd: 'MACD', bb: 'BB Position',
  ema: 'EMA Cross', volume: 'Volume Surge', sentiment: 'Sentiment',
}

const DEFAULT_CONFIG = {
  symbol: 'BTC/USDT', exchange: 'binanceus', timeframe: '15m',
  weights: { rsi: 0.25, macd: 0.20, bb: 0.15, ema: 0.20, volume: 0.10, sentiment: 0.10 },
  buy_threshold: 0.30, sell_threshold: 0.30,
  usdt_amount: 500, max_positions: 3, max_daily_loss: 150,
}

type StratConfig = typeof DEFAULT_CONFIG

export default function StrategyBuilder() {
  const [strategies, setStrategies] = useState<StrategyRow[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [config, setConfig]         = useState<StratConfig>(DEFAULT_CONFIG)
  const [name, setName]             = useState('')
  const [saved, setSaved]           = useState(false)
  const [activating, setActivating] = useState(false)

  useEffect(() => {
    api.listStrategies().then(rows => {
      setStrategies(rows)
      const active = rows.find(r => r.is_active)
      if (active) setSelectedId(active.id)
    }).catch(() => {})
  }, [])

  const handleSave = async () => {
    try {
      await api.createStrategy(name || 'My Strategy', config)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      api.listStrategies().then(setStrategies).catch(() => {})
    } catch { /* ignore */ }
  }

  const handleActivate = async () => {
    if (!selectedId) return
    setActivating(true)
    try {
      await api.activateStrategy(selectedId)
      setStrategies(prev => prev.map(s => ({ ...s, is_active: s.id === selectedId })))
    } catch { /* ignore */ }
    setActivating(false)
  }

  const updateWeight = (key: string, val: number) =>
    setConfig(c => ({ ...c, weights: { ...c.weights, [key]: val } }))

  const sectionLabel: React.CSSProperties = {
    color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono, letterSpacing: '0.12em',
    textTransform: 'uppercase', marginBottom: 14, paddingBottom: 8, borderBottom: `1px solid ${TC.border}`,
  }

  const weightSum = Object.values(config.weights).reduce((a, b) => a + b, 0)

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Left: strategy list */}
      <div style={{ width: 215, flexShrink: 0, borderRight: `1px solid ${TC.border}`, display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${TC.border}` }}>
          <span style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Saved Strategies</span>
        </div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {strategies.length === 0 && (
            <div style={{ padding: '20px 16px', color: TC.textMuted, fontSize: 11, fontFamily: TC.fontMono }}>No strategies yet</div>
          )}
          {strategies.map(s => {
            const sel = selectedId === s.id
            return (
              <button key={s.id} onClick={() => setSelectedId(s.id)} style={{
                width: '100%', textAlign: 'left', padding: '12px 16px', border: 'none', cursor: 'pointer',
                background: sel ? 'rgba(255,255,255,0.03)' : 'transparent',
                borderLeft: `2px solid ${s.is_active ? TC.green : sel ? TC.accent : 'transparent'}`,
                transition: 'all 0.12s',
              }}>
                <div style={{ color: sel ? TC.text : TC.textMid, fontSize: 12.5, fontFamily: TC.fontUI, fontWeight: sel ? 500 : 400 }}>{s.name}</div>
                <div style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono, marginTop: 4 }}>Created {s.created_at ? new Date(s.created_at).toLocaleDateString() : '—'}</div>
                {s.is_active && <div style={{ marginTop: 6 }}><TCBadge variant="buy">ACTIVE</TCBadge></div>}
              </button>
            )
          })}
        </div>
      </div>

      {/* Right: config form */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px 80px' }}>

        {/* Strategy name */}
        <div style={{ marginBottom: 28 }}>
          <div style={sectionLabel}>Strategy Name</div>
          <TCInput label="Name" value={name} onChange={v => setName(String(v))}/>
        </div>

        {/* Basic config */}
        <div style={{ marginBottom: 28 }}>
          <div style={sectionLabel}>Basic Configuration</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
            <TCInput label="Symbol"     value={config.symbol}    onChange={v => setConfig(c => ({ ...c, symbol: String(v) }))}/>
            <TCSelect label="Exchange"  value={config.exchange}  onChange={v => setConfig(c => ({ ...c, exchange: v }))} options={['binanceus','binance','coinbase','kraken','bybit']}/>
            <TCSelect label="Timeframe" value={config.timeframe} onChange={v => setConfig(c => ({ ...c, timeframe: v }))} options={['1m','5m','15m','30m','1h','4h','1d']}/>
          </div>
        </div>

        {/* Indicator Weights */}
        <div style={{ marginBottom: 28 }}>
          <div style={sectionLabel}>Indicator Weights</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 40px' }}>
            {Object.entries(config.weights).map(([key, val]) => (
              <TCSlider key={key} label={INDICATOR_LABELS[key] ?? key} value={val} onChange={v => updateWeight(key, v)}/>
            ))}
          </div>
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono }}>Total weight:</span>
            <span style={{ fontFamily: TC.fontMono, fontSize: 10, fontWeight: 700, color: Math.abs(weightSum - 1) < 0.01 ? TC.green : TC.yellow }}>
              {weightSum.toFixed(2)}
            </span>
            <span style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono, opacity: 0.6 }}>(should sum to 1.00)</span>
          </div>
        </div>

        {/* Thresholds */}
        <div style={{ marginBottom: 28 }}>
          <div style={sectionLabel}>Signal Thresholds</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 40px' }}>
            <TCSlider label="BUY Threshold  (score > X)"  value={config.buy_threshold}  onChange={v => setConfig(c => ({ ...c, buy_threshold: v }))}/>
            <TCSlider label="SELL Threshold (score < -X)" value={config.sell_threshold} onChange={v => setConfig(c => ({ ...c, sell_threshold: v }))}/>
          </div>
        </div>

        {/* Position Sizing & Risk */}
        <div style={{ marginBottom: 32 }}>
          <div style={sectionLabel}>Position Sizing &amp; Risk</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
            <TCInput label="USDT Amount"        value={config.usdt_amount}    onChange={v => setConfig(c => ({ ...c, usdt_amount: Number(v) }))}    type="number" suffix="USDT"/>
            <TCInput label="Max Open Positions" value={config.max_positions}  onChange={v => setConfig(c => ({ ...c, max_positions: Number(v) }))}  type="number"/>
            <TCInput label="Max Daily Loss"     value={config.max_daily_loss} onChange={v => setConfig(c => ({ ...c, max_daily_loss: Number(v) }))} type="number" suffix="USDT"/>
          </div>
        </div>

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', paddingTop: 8, borderTop: `1px solid ${TC.border}` }}>
          <button onClick={handleSave} style={{
            padding: '8px 22px', borderRadius: 5, cursor: 'pointer', fontFamily: TC.fontMono, fontSize: 11, fontWeight: 700, letterSpacing: '0.05em',
            background: saved ? TC.greenDim : TC.accentDim,
            border: `1px solid ${saved ? TC.green : TC.accent}`,
            color: saved ? TC.green : TC.accent, transition: 'all 0.2s',
          }}>{saved ? '✓ SAVED' : 'SAVE'}</button>

          <button onClick={handleActivate} disabled={!selectedId || activating} style={{
            padding: '8px 22px', borderRadius: 5, cursor: selectedId ? 'pointer' : 'not-allowed', fontFamily: TC.fontMono, fontSize: 11, fontWeight: 700, letterSpacing: '0.05em',
            background: strategies.find(s => s.id === selectedId)?.is_active ? TC.greenDim : 'transparent',
            border: `1px solid ${strategies.find(s => s.id === selectedId)?.is_active ? TC.green : TC.border}`,
            color: strategies.find(s => s.id === selectedId)?.is_active ? TC.green : TC.textMid,
          }}>{strategies.find(s => s.id === selectedId)?.is_active ? '✓ ACTIVE' : activating ? 'ACTIVATING…' : 'ACTIVATE'}</button>
        </div>
      </div>
    </div>
  )
}
