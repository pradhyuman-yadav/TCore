import { create } from 'zustand'

interface Signal {
  symbol: string
  zone: string
  score: number
  action: string
  ts: string
  reason?: string
}

export interface PriceTick {
  type: 'tick'
  symbol: string
  exchange: string
  time: number   // unix seconds
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface AppStore {
  killSwitch: boolean
  tradingMode: string
  activeStrategy: Record<string, unknown> | null
  signals: Signal[]
  wsStatus: 'connecting' | 'open' | 'closed'
  latestTick: PriceTick | null
  workspace: 'crypto' | 'stock'

  setKillSwitch: (v: boolean) => void
  setTradingMode: (v: string) => void
  setActiveStrategy: (s: Record<string, unknown> | null) => void
  pushSignal: (s: Signal) => void
  clearSignals: () => void
  setWsStatus: (s: AppStore['wsStatus']) => void
  setLatestTick: (t: PriceTick) => void
  setWorkspace: (w: 'crypto' | 'stock') => void
}

export const useStore = create<AppStore>((set) => ({
  killSwitch: false,
  tradingMode: 'paper',
  activeStrategy: null,
  signals: [],
  wsStatus: 'closed',
  latestTick: null,
  workspace: 'crypto',

  setKillSwitch: (v) => set({ killSwitch: v }),
  setTradingMode: (v) => set({ tradingMode: v }),
  setActiveStrategy: (s) => set({ activeStrategy: s }),
  pushSignal: (s) =>
    set((state) => {
      const key = `${s.symbol}|${s.ts}`
      if (state.signals.some(x => `${x.symbol}|${x.ts}` === key)) return state
      return { signals: [s, ...state.signals].slice(0, 500) }
    }),
  clearSignals: () => set({ signals: [] }),
  setWsStatus: (s) => set({ wsStatus: s }),
  setLatestTick: (t) => set({ latestTick: t }),
  setWorkspace: (w) => set({ workspace: w }),
}))
