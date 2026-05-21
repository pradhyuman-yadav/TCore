// TradeCore — Strategy Builder Page

const { useState: useStratState } = React;

const INDICATOR_LABELS = { rsi: 'RSI', macd: 'MACD', bb: 'BB Position', ema: 'EMA Cross', volume: 'Volume Surge', sentiment: 'Sentiment' };

// ─── Text / Number Input ──────────────────────────────────────────────────
const TCInput = ({ label, value, onChange, type = 'text', suffix }) => (
  <div>
    <div style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.08em', marginBottom: 5, textTransform: 'uppercase' }}>{label}</div>
    <div style={{ position: 'relative' }}>
      <input
        type={type} value={value}
        onChange={e => onChange(type === 'number' ? parseFloat(e.target.value) || 0 : e.target.value)}
        style={{
          width: '100%', padding: '7px 10px', boxSizing: 'border-box',
          background: TC_COLORS.surface2, border: `1px solid ${TC_COLORS.border}`,
          borderRadius: 5, color: type === 'number' ? TC_COLORS.accent : TC_COLORS.text,
          fontFamily: TC_FONTS.mono, fontSize: 12, outline: 'none',
          transition: 'border-color 0.15s',
        }}
        onFocus={e => e.target.style.borderColor = TC_COLORS.accent + '66'}
        onBlur={e  => e.target.style.borderColor = TC_COLORS.border}
      />
      {suffix && <span style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', color: TC_COLORS.textMuted, fontSize: 10, fontFamily: TC_FONTS.mono, pointerEvents: 'none' }}>{suffix}</span>}
    </div>
  </div>
);

// ─── Select Input ─────────────────────────────────────────────────────────
const TCSelect = ({ label, value, onChange, options }) => (
  <div>
    <div style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.08em', marginBottom: 5, textTransform: 'uppercase' }}>{label}</div>
    <select
      value={value} onChange={e => onChange(e.target.value)}
      style={{
        width: '100%', padding: '7px 10px', boxSizing: 'border-box',
        background: TC_COLORS.surface2, border: `1px solid ${TC_COLORS.border}`,
        borderRadius: 5, color: TC_COLORS.text, fontFamily: TC_FONTS.mono, fontSize: 12,
        outline: 'none', cursor: 'pointer', appearance: 'none',
      }}
    >
      {options.map(o => <option key={o} value={o} style={{ background: TC_COLORS.surface2 }}>{o}</option>)}
    </select>
  </div>
);

// ─── Threshold Slider (center-zero visual) ────────────────────────────────
const ThresholdSlider = ({ label, value, onChange, color }) => (
  <TCSlider label={label} value={value} onChange={onChange} min={0} max={1} step={0.01}/>
);

// ─── Strategy Page ────────────────────────────────────────────────────────
const StrategyPage = () => {
  const [strategies, setStrategies] = useStratState(TC_STRATEGIES);
  const [selectedId,  setSelectedId]  = useStratState(1);
  const [saved,       setSaved]       = useStratState(false);

  const selected = strategies.find(s => s.id === selectedId) || strategies[0];

  const update = (field, value) =>
    setStrategies(prev => prev.map(s => s.id === selectedId ? { ...s, [field]: value } : s));

  const updateWeight = (key, value) =>
    setStrategies(prev => prev.map(s => s.id === selectedId ? { ...s, weights: { ...s.weights, [key]: value } } : s));

  const handleSave = () => { setSaved(true); setTimeout(() => setSaved(false), 2000); };

  const handleActivate = () =>
    setStrategies(prev => prev.map(s => ({ ...s, active: s.id === selectedId })));

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>

      {/* Left: strategy list */}
      <div style={{ width: 215, flexShrink: 0, borderRight: `1px solid ${TC_COLORS.border}`, display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${TC_COLORS.border}` }}>
          <span style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Saved Strategies</span>
        </div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {strategies.map(s => {
            const sel = selectedId === s.id;
            return (
              <button key={s.id} onClick={() => setSelectedId(s.id)} style={{
                width: '100%', textAlign: 'left', padding: '12px 16px', border: 'none', cursor: 'pointer',
                background: sel ? 'rgba(255,255,255,0.03)' : 'transparent',
                borderLeft: `2px solid ${s.active ? TC_COLORS.green : sel ? TC_COLORS.accent : 'transparent'}`,
                transition: 'all 0.12s',
              }}>
                <div style={{ color: sel ? TC_COLORS.text : TC_COLORS.textMid, fontSize: 12.5, fontFamily: TC_FONTS.ui, fontWeight: sel ? 500 : 400 }}>{s.name}</div>
                <div style={{ color: TC_COLORS.textMuted, fontSize: 10, fontFamily: TC_FONTS.mono, marginTop: 4 }}>{s.symbol} · {s.timeframe}</div>
                {s.active && <div style={{ marginTop: 6 }}><TCBadge variant="buy">ACTIVE</TCBadge></div>}
              </button>
            );
          })}
        </div>
      </div>

      {/* Right: config form */}
      {selected && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px 80px' }}>

          {/* Section: Basic */}
          <div style={{ marginBottom: 28 }}>
            <div style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 14, paddingBottom: 8, borderBottom: `1px solid ${TC_COLORS.border}` }}>
              Basic Configuration
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
              <TCInput label="Symbol"   value={selected.symbol}    onChange={v => update('symbol', v)}/>
              <TCSelect label="Exchange" value={selected.exchange}  onChange={v => update('exchange', v)} options={['Binance','Coinbase','Kraken','Bybit']}/>
              <TCSelect label="Timeframe" value={selected.timeframe} onChange={v => update('timeframe', v)} options={['1m','5m','15m','30m','1h','4h','1d']}/>
            </div>
          </div>

          {/* Section: Indicator Weights */}
          <div style={{ marginBottom: 28 }}>
            <div style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 14, paddingBottom: 8, borderBottom: `1px solid ${TC_COLORS.border}` }}>
              Indicator Weights
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 40px' }}>
              {Object.entries(selected.weights).map(([key, val]) => (
                <TCSlider
                  key={key}
                  label={INDICATOR_LABELS[key] || key.toUpperCase()}
                  value={val}
                  onChange={v => updateWeight(key, v)}
                />
              ))}
            </div>
            {/* Weight sum indicator */}
            <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ color: TC_COLORS.textMuted, fontSize: 10, fontFamily: TC_FONTS.mono }}>Total weight:</span>
              <span style={{
                fontFamily: TC_FONTS.mono, fontSize: 10, fontWeight: 700,
                color: Math.abs(Object.values(selected.weights).reduce((a, b) => a + b, 0) - 1) < 0.01
                  ? TC_COLORS.green : TC_COLORS.yellow,
              }}>
                {Object.values(selected.weights).reduce((a, b) => a + b, 0).toFixed(2)}
              </span>
              <span style={{ color: TC_COLORS.textMuted, fontSize: 10, fontFamily: TC_FONTS.mono, opacity: 0.6 }}>(should sum to 1.00)</span>
            </div>
          </div>

          {/* Section: Signal Thresholds */}
          <div style={{ marginBottom: 28 }}>
            <div style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 14, paddingBottom: 8, borderBottom: `1px solid ${TC_COLORS.border}` }}>
              Signal Thresholds
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 40px' }}>
              <TCSlider label="BUY  Threshold  (score &gt; X → buy)"  value={selected.buyThreshold}  onChange={v => update('buyThreshold',  v)}/>
              <TCSlider label="SELL Threshold  (score &lt; −X → sell)" value={selected.sellThreshold} onChange={v => update('sellThreshold', v)}/>
            </div>
          </div>

          {/* Section: Position Sizing & Risk */}
          <div style={{ marginBottom: 32 }}>
            <div style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 14, paddingBottom: 8, borderBottom: `1px solid ${TC_COLORS.border}` }}>
              Position Sizing &amp; Risk
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
              <TCInput label="USDT Amount"       value={selected.usdtAmount}    onChange={v => update('usdtAmount', v)}    type="number" suffix="USDT"/>
              <TCInput label="Max Open Positions" value={selected.maxPositions}  onChange={v => update('maxPositions', v)}  type="number"/>
              <TCInput label="Max Daily Loss"     value={selected.maxDailyLoss}  onChange={v => update('maxDailyLoss', v)}  type="number" suffix="USDT"/>
            </div>
          </div>

          {/* Action buttons */}
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', paddingTop: 8, borderTop: `1px solid ${TC_COLORS.border}` }}>
            <button onClick={handleSave} style={{
              padding: '8px 22px', borderRadius: 5, cursor: 'pointer', fontFamily: TC_FONTS.mono, fontSize: 11, fontWeight: 700, letterSpacing: '0.05em',
              background: saved ? TC_COLORS.greenDim : TC_COLORS.accentDim,
              border: `1px solid ${saved ? TC_COLORS.green : TC_COLORS.accent}`,
              color: saved ? TC_COLORS.green : TC_COLORS.accent,
              transition: 'all 0.2s',
            }}>{saved ? '✓ SAVED' : 'SAVE'}</button>

            <button onClick={handleActivate} style={{
              padding: '8px 22px', borderRadius: 5, cursor: 'pointer', fontFamily: TC_FONTS.mono, fontSize: 11, fontWeight: 700, letterSpacing: '0.05em',
              background: selected.active ? TC_COLORS.greenDim : 'transparent',
              border: `1px solid ${selected.active ? TC_COLORS.green : TC_COLORS.border}`,
              color: selected.active ? TC_COLORS.green : TC_COLORS.textMid,
            }}>{selected.active ? '✓ ACTIVE' : 'ACTIVATE'}</button>

            <button style={{
              marginLeft: 'auto', padding: '8px 22px', borderRadius: 5, cursor: 'pointer',
              fontFamily: TC_FONTS.mono, fontSize: 11, fontWeight: 700, letterSpacing: '0.05em',
              background: 'transparent', border: `1px solid rgba(255,68,68,0.25)`, color: TC_COLORS.red,
            }}>DELETE</button>
          </div>
        </div>
      )}
    </div>
  );
};

Object.assign(window, { StrategyPage });
