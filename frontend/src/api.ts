const BASE = '/api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || 'GET').toUpperCase()
  // Only send Content-Type for requests that have a body
  const hasBody = !['GET', 'HEAD', 'DELETE'].includes(method)
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
      ...(init?.headers as Record<string, string> | undefined),
    },
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

export const api = {
  // Health
  health: () => req<Record<string, unknown>>('/health'),

  // Control
  getControl: () => req<{ kill_switch: boolean; trading_mode: string }>('/control'),
  setKillSwitch: (enabled: boolean) =>
    req('/control/kill-switch', { method: 'POST', body: JSON.stringify({ enabled }) }),
  setTradingMode: (mode: string) =>
    req('/control/trading-mode', { method: 'POST', body: JSON.stringify({ mode }) }),

  // Market
  getOhlcv: (symbol: string, exchange: string, timeframe = '1h', limit = 200) =>
    req<OhlcvBar[]>(`/market/ohlcv?symbol=${encodeURIComponent(symbol)}&exchange=${exchange}&timeframe=${timeframe}&limit=${limit}`),
  getOhlcvCount: (symbol: string, exchange: string) =>
    req<{ symbol: string; exchange: string; count: number }>(`/market/ohlcv/count?symbol=${encodeURIComponent(symbol)}&exchange=${exchange}`),
  syncMarket: (symbol: string, exchange: string, timeframe = '1h', days = 90) =>
    req<{ symbol: string; exchange: string; timeframe: string; days: number; upserted: number }>(
      `/market/sync?symbol=${encodeURIComponent(symbol)}&exchange=${exchange}&timeframe=${timeframe}&days=${days}`,
      { method: 'POST' }
    ),

  // Strategy
  listStrategies: () => req<StrategyRow[]>('/strategy'),
  getActiveStrategy: () => req<Record<string, unknown>>('/strategy/active'),
  createStrategy: (name: string, config: Record<string, unknown>) =>
    req('/strategy', { method: 'POST', body: JSON.stringify({ name, config }) }),
  activateStrategy: (id: string) =>
    req(`/strategy/${id}/activate`, { method: 'POST' }),

  // Paper
  paperPositions: () => req<Position[]>('/paper/positions'),
  paperTrades: (limit = 50) => req<Trade[]>(`/paper/trades?limit=${limit}`),

  // Live
  livePositions: () => req<Position[]>('/live/positions'),
  liveTrades: (limit = 50) => req<Trade[]>(`/live/trades?limit=${limit}`),

  // Strategy detail
  getStrategy: (id: string) => req<StrategyDetail>(`/strategy/${id}`),

  // Backtest
  runBacktest: (body: BacktestRequest) =>
    req<BacktestResult>('/backtest/run', { method: 'POST', body: JSON.stringify(body) }),

  // Paper account
  getPaperAccount: () => req<PaperAccount>('/paper/account'),
  setPaperAccount: (config: PaperAccountConfig) =>
    req<PaperAccount>('/paper/account', { method: 'PUT', body: JSON.stringify(config) }),

  // Watchlist
  getWatchlist: () => req<WatchedSymbol[]>('/watchlist'),
  addWatchedSymbol: (symbol: string, exchange: string, asset_type: string) =>
    req<WatchedSymbol>('/watchlist', { method: 'POST', body: JSON.stringify({ symbol, exchange, asset_type }) }),
  removeWatchedSymbol: (id: string) =>
    req(`/watchlist/${id}`, { method: 'DELETE' }),

  // News
  getNews: (symbols?: string[], limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (symbols?.length) params.set('symbols', symbols.join(','))
    return req<NewsArticle[]>(`/news?${params}`)
  },

  // Social
  getSocial: (source: 'reddit' | 'twitter' | 'rss', category = 'crypto', query = 'bitcoin OR crypto', limit = 30) =>
    req<SocialPost[]>(`/social?source=${source}&category=${category}&query=${encodeURIComponent(query)}&limit=${limit}`),
}

// Types
export interface OhlcvBar {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  symbol: string
  exchange: string
}

export interface StrategyRow {
  id: string
  name: string
  is_active: boolean
  created_at: string | null
}

export interface Position {
  id: string
  symbol: string
  exchange: string
  side: string
  quantity: number
  avg_entry_price: number
  opened_at: string | null
}

export interface Trade {
  id: string
  symbol: string
  side: string
  quantity: number
  price: number
  pnl: number | null
  created_at: string | null
}

export interface StrategyDetail {
  id: string
  name: string
  is_active: boolean
  config: Record<string, unknown>
  created_at: string | null
}

export interface PaperAccount {
  initial_capital: number
  fee_rate: number
  slippage_bps: number
  realized_pnl: number
  open_positions: number
}

export interface PaperAccountConfig {
  initial_capital: number
  fee_rate: number
  slippage_bps: number
}

export interface BacktestRequest {
  symbol: string
  exchange: string
  timeframe?: string
  initial_capital?: number
  fee_rate?: number
  slippage_bps?: number
  date_from?: string
  date_to?: string
  strategy_config?: Record<string, unknown>
}

export interface BacktestResult {
  symbol: string
  exchange: string
  total_bars: number
  num_trades: number
  total_pnl: number
  win_rate: number
  max_drawdown: number
  sharpe_ratio: number | null
  equity_curve: number[]
  trades: BacktestTrade[]
}

export interface BacktestTrade {
  bar_index: number
  time: string
  side: string
  price: number
  quantity: number
  pnl: number | null
}

export interface WatchedSymbol {
  id: string
  symbol: string
  exchange: string
  asset_type: string
  added_at: string | null
}

export interface NewsArticle {
  title: string
  source: string
  published_at: string | null
  url: string | null
  summary: string
}

export interface SocialPost {
  title: string
  source: string
  url: string | null
  score: number
  comments: number
  published_at: string | null
  platform: string
}
