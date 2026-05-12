import { create } from 'zustand'

interface Signal {
  symbol: string
  zone: string
  score: number
  action: string
  ts: string
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

  setKillSwitch: (v: boolean) => void
  setTradingMode: (v: string) => void
  setActiveStrategy: (s: Record<string, unknown> | null) => void
  pushSignal: (s: Signal) => void
  setWsStatus: (s: AppStore['wsStatus']) => void
  setLatestTick: (t: PriceTick) => void
}

export const useStore = create<AppStore>((set) => ({
  killSwitch: false,
  tradingMode: 'paper',
  activeStrategy: null,
  signals: [],
  wsStatus: 'closed',
  latestTick: null,

  setKillSwitch: (v) => set({ killSwitch: v }),
  setTradingMode: (v) => set({ tradingMode: v }),
  setActiveStrategy: (s) => set({ activeStrategy: s }),
  pushSignal: (s) =>
    set((state) => ({ signals: [s, ...state.signals].slice(0, 100) })),
  setWsStatus: (s) => set({ wsStatus: s }),
  setLatestTick: (t) => set({ latestTick: t }),
}))
