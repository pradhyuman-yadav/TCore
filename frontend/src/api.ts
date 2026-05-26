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
  if (!res.ok) {
    const text = await res.text()
    // Try to extract a human-readable detail from JSON error bodies
    let detail = text
    try {
      const json = JSON.parse(text)
      detail = json.detail ?? json.message ?? text
    } catch { /* not JSON — use raw text */ }
    // Strip nginx/proxy HTML for non-200 gateway errors
    if (detail.trimStart().startsWith('<')) {
      detail = `Server error (${res.status}). Check network or try again.`
    }
    throw new Error(`${res.status} ${detail}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  // Health
  health: () => req<HealthStatus>('/health'),

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
  listStrategies: (assetType?: string) => {
    const p = assetType ? `?asset_type=${assetType}` : ''
    return req<StrategyRow[]>(`/strategy${p}`)
  },
  getActiveStrategy: () => req<Record<string, unknown>>('/strategy/active'),
  createStrategy: (name: string, config: Record<string, unknown>, assetType?: string) =>
    req('/strategy', { method: 'POST', body: JSON.stringify({ name, config, asset_type: assetType }) }),
  activateStrategy: (id: string) =>
    req(`/strategy/${id}/activate`, { method: 'POST' }),
  deleteStrategy: (id: string) =>
    req(`/strategy/${id}`, { method: 'DELETE' }),

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

  // Claude health
  getClaudeHealth: () => req<ClaudeHealth>('/health/claude'),

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

  // Feed sources
  getNewsSources:    () => req<FeedSource[]>('/sources/news'),
  addNewsSource:     (name: string, url: string) =>
    req<FeedSource>('/sources/news', { method: 'POST', body: JSON.stringify({ name, url }) }),
  removeNewsSource:  (id: string) => req(`/sources/news/${id}`, { method: 'DELETE' }),

  getSocialSources:  () => req<FeedSource[]>('/sources/social'),
  addSocialSource:   (body: { type: string; name: string; url?: string; category?: string }) =>
    req<FeedSource>('/sources/social', { method: 'POST', body: JSON.stringify(body) }),
  removeSocialSource:(id: string) => req(`/sources/social/${id}`, { method: 'DELETE' }),

  // Indicators
  getLatestIndicators: (symbol: string) =>
    req<IndicatorRow[]>(`/signals/indicators?symbol=${encodeURIComponent(symbol)}`),

  // Signals history
  getSignals: (params?: { limit?: number; symbol?: string; asset_type?: string }) => {
    const p = new URLSearchParams({ limit: String(params?.limit ?? 200) })
    if (params?.symbol) p.set('symbol', params.symbol)
    if (params?.asset_type) p.set('asset_type', params.asset_type)
    return req<StoredSignal[]>(`/signals?${p}`)
  },

  // News
  getNews: (limit = 50, category?: string) => {
    const p = new URLSearchParams({ limit: String(limit) })
    if (category) p.set('category', category)
    return req<NewsArticle[]>(`/news?${p}`)
  },
  refreshNews: () => req<{ status: string }>('/news/refresh', { method: 'POST' }),

  // Social
  getSocial: (source: 'reddit' | 'twitter' | 'rss', limit = 30, category?: string) => {
    const p = new URLSearchParams({ source, limit: String(limit) })
    if (category) p.set('category', category)
    return req<SocialPost[]>(`/social?${p}`)
  },
  refreshSocial: () => req<{ status: string }>('/social/refresh', { method: 'POST' }),
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
  asset_type: string | null
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
  bars_used: number
  bars_capped: boolean
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
  category: string | null
}

export interface ClaudeHealth {
  status: 'ok' | 'error'
  model: string | null
  test_score: number | null
  reasoning?: string
  latency_ms: number | null
  detail?: string
  proxy?: {
    status: string
    uptime_seconds: number
    requests: number
    errors: number
    auth_configured: boolean
  } | null
}

export interface SocialPost {
  title: string
  source: string
  url: string | null
  score: number
  comments: number
  published_at: string | null
  platform: string
  category: string | null
}

export interface FeedSource {
  id: string
  type: string        // rss_news | reddit | rss_social
  name: string
  url: string | null
  category: string | null
  is_active: boolean
  added_at: string | null
}

export interface IndicatorRow {
  indicator_name: string
  value: number
  weight: number
  weighted_value: number
  time: string | null
}

export interface HealthStatus {
  status: string
  version: string
  db: 'connected' | 'disconnected'
  scheduler: 'running' | 'stopped'
  trading_mode: string
  kill_switch: boolean
  active_strategy: string | null
  ws_connections: Record<string, number>
}

export interface StoredSignal {
  id: string
  symbol: string
  exchange: string
  zone: string
  score: number
  action: string
  reason: string | null
  strategy_id: string | null
  triggered_at: string
}
