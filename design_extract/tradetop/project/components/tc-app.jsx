// TradeCore — App root + render

const { useState: useAppState, useEffect: useAppEffect } = React;

const App = () => {
  const [page,        setPage]        = useAppState('dashboard');
  const [killSwitch,  setKillSwitch]  = useAppState(false);
  const [mode,        setMode]        = useAppState('PAPER');
  const [transitioning, setTransit]   = useAppState(false);

  // Tweaks panel
  const [tweaksOpen, setTweaksOpen]   = useAppState(false);
  const [tweakMode,  setTweakMode]    = useAppState('PAPER');

  // Register tweaks protocol
  useAppEffect(() => {
    const handler = e => {
      if (e.data?.type === '__activate_edit_mode')   setTweaksOpen(true);
      if (e.data?.type === '__deactivate_edit_mode') setTweaksOpen(false);
    };
    window.addEventListener('message', handler);
    window.parent.postMessage({ type: '__edit_mode_available' }, '*');
    return () => window.removeEventListener('message', handler);
  }, []);

  const navigate = id => {
    if (id === page) return;
    setTransit(true);
    setTimeout(() => { setPage(id); setTransit(false); }, 110);
  };

  const applyTweaks = (patch) => {
    if (patch.mode !== undefined) setMode(patch.mode);
    if (patch.kill !== undefined) setKillSwitch(patch.kill);
  };

  const pages = {
    dashboard: <DashboardPage killSwitch={killSwitch}/>,
    chart:     <ChartPage/>,
    strategy:  <StrategyPage/>,
    backtest:  <BacktestPage/>,
    signals:   <SignalPage/>,
  };

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: TC_COLORS.bg, color: TC_COLORS.text, fontFamily: TC_FONTS.ui, overflow: 'hidden' }}>

      {/* Top Navbar */}
      <TCNavbar
        mode={mode}
        killSwitch={killSwitch}
        setKillSwitch={setKillSwitch}
        wsOk={true}
        dbOk={true}
        strategyName="BTC Momentum v2"
      />

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
        <TCSidebar active={page} setActive={navigate}/>
        <main style={{
          flex: 1, overflow: 'auto', minWidth: 0,
          opacity: transitioning ? 0 : 1,
          transition: 'opacity 0.1s ease',
        }}>
          {killSwitch && <TCKillBanner/>}
          {/* Paper mode border indicator */}
          {mode === 'PAPER' && (
            <div style={{ height: 2, background: `linear-gradient(90deg, transparent, ${TC_COLORS.yellow}55, transparent)` }}/>
          )}
          {pages[page]}
        </main>
      </div>

      {/* Tweaks Panel */}
      {tweaksOpen && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 1000,
          background: TC_COLORS.surface2, border: `1px solid ${TC_COLORS.borderHi}`,
          borderRadius: 10, padding: 20, width: 260,
          boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
          fontFamily: TC_FONTS.ui,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
            <span style={{ color: TC_COLORS.text, fontSize: 13, fontWeight: 600 }}>Tweaks</span>
            <button onClick={() => {
              setTweaksOpen(false);
              window.parent.postMessage({ type: '__edit_mode_dismissed' }, '*');
            }} style={{ background: 'none', border: 'none', color: TC_COLORS.textMuted, cursor: 'pointer', fontSize: 16, padding: 0 }}>✕</button>
          </div>

          {/* Mode toggle */}
          <div style={{ marginBottom: 18 }}>
            <div style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.1em', marginBottom: 8, textTransform: 'uppercase' }}>Trading Mode</div>
            <div style={{ display: 'flex', gap: 6 }}>
              {['PAPER','LIVE'].map(m => (
                <button key={m} onClick={() => { setMode(m); window.parent.postMessage({ type: '__edit_mode_set_keys', edits: { mode: m } }, '*'); }} style={{
                  flex: 1, padding: '7px 0', borderRadius: 5, cursor: 'pointer',
                  border: `1px solid ${mode === m ? (m === 'LIVE' ? TC_COLORS.red : TC_COLORS.yellow) : TC_COLORS.border}`,
                  background: mode === m ? (m === 'LIVE' ? TC_COLORS.redDim : TC_COLORS.yellowDim) : 'transparent',
                  color: mode === m ? (m === 'LIVE' ? TC_COLORS.red : TC_COLORS.yellow) : TC_COLORS.textMid,
                  fontFamily: TC_FONTS.mono, fontSize: 11, fontWeight: 700,
                }}>{m}</button>
              ))}
            </div>
          </div>

          {/* Kill Switch */}
          <div style={{ marginBottom: 18 }}>
            <div style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.1em', marginBottom: 8, textTransform: 'uppercase' }}>Kill Switch</div>
            <button onClick={() => setKillSwitch(k => !k)} style={{
              width: '100%', padding: '8px 0', borderRadius: 5, cursor: 'pointer',
              border: `1px solid ${killSwitch ? TC_COLORS.red : TC_COLORS.border}`,
              background: killSwitch ? TC_COLORS.redDim : 'transparent',
              color: killSwitch ? TC_COLORS.red : TC_COLORS.textMid,
              fontFamily: TC_FONTS.mono, fontSize: 11, fontWeight: 700,
            }}>{killSwitch ? '⚠ HALT ACTIVE — CLICK TO RESUME' : 'Activate Kill Switch'}</button>
          </div>

          {/* Active page */}
          <div>
            <div style={{ color: TC_COLORS.textMuted, fontSize: 9.5, fontFamily: TC_FONTS.mono, letterSpacing: '0.1em', marginBottom: 8, textTransform: 'uppercase' }}>Navigate To</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {TC_NAV.map(({ id, label }) => (
                <button key={id} onClick={() => navigate(id)} style={{
                  padding: '6px 10px', borderRadius: 4, cursor: 'pointer', textAlign: 'left',
                  border: `1px solid ${page === id ? TC_COLORS.accent : TC_COLORS.border}`,
                  background: page === id ? TC_COLORS.accentDim : 'transparent',
                  color: page === id ? TC_COLORS.accent : TC_COLORS.textMid,
                  fontFamily: TC_FONTS.ui, fontSize: 12,
                }}>{label}</button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App/>);
