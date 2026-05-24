import { useEffect, useState, useCallback } from 'react'
import { api, NewsArticle } from '../api'
import { TC } from '../theme'
import { TCBadge, TCSectionHeader } from '../components/ui'

const REFRESH_MS = 5 * 60 * 1000  // 5 minutes

function timeAgo(isoStr: string | null): string {
  if (!isoStr) return ''
  const diff = Date.now() - new Date(isoStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function News() {
  const [articles, setArticles]   = useState<NewsArticle[]>([])
  const [loading, setLoading]     = useState(true)
  const [filter, setFilter]       = useState('All')
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const SOURCES = ['All', 'CoinDesk', 'CoinTelegraph', 'Decrypt', 'Reuters', 'ET Markets', 'OpenBB']

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getNews(80)
      setArticles(data)
      setLastRefresh(new Date())
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const id = setInterval(load, REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  const filtered = filter === 'All'
    ? articles
    : articles.filter(a => a.source.toLowerCase().includes(filter.toLowerCase()))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

      {/* Header */}
      <div style={{
        padding: '10px 18px', borderBottom: `1px solid ${TC.border}`,
        display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0,
        background: TC.surface, flexWrap: 'wrap',
      }}>
        <span style={{ color: TC.text, fontFamily: TC.fontMono, fontSize: 13, fontWeight: 700 }}>News Feed</span>
        <div style={{ width: 1, height: 18, background: TC.border }}/>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {SOURCES.map(s => (
            <button key={s} onClick={() => setFilter(s)} style={{
              padding: '3px 10px', borderRadius: 5, cursor: 'pointer',
              border: `1px solid ${filter === s ? TC.accent : TC.border}`,
              background: filter === s ? TC.accentDim : 'transparent',
              color: filter === s ? TC.accent : TC.textMid,
              fontFamily: TC.fontMono, fontSize: 10.5, fontWeight: filter === s ? 700 : 400,
            }}>{s}</button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
          {lastRefresh && (
            <span style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono }}>
              Updated {timeAgo(lastRefresh.toISOString())}
            </span>
          )}
          <button onClick={load} disabled={loading} style={{
            padding: '3px 10px', background: 'transparent', border: `1px solid ${TC.border}`,
            borderRadius: 4, color: loading ? TC.textMuted : TC.textMid, fontFamily: TC.fontMono, fontSize: 10, cursor: 'pointer',
          }}>
            {loading ? '⟳ Loading…' : '⟳ Refresh'}
          </button>
        </div>
      </div>

      {/* Article list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 18px' }}>
        {loading && articles.length === 0 && (
          <div style={{ color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 12, textAlign: 'center', marginTop: 60 }}>
            Loading news…
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <div style={{ color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 12, textAlign: 'center', marginTop: 60 }}>
            No articles found
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {filtered.map((article, i) => (
            <ArticleCard key={i} article={article}/>
          ))}
        </div>
      </div>
    </div>
  )
}

function ArticleCard({ article }: { article: NewsArticle }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '12px 16px', borderRadius: 6,
        border: `1px solid ${hovered ? TC.borderHi : TC.border}`,
        background: hovered ? TC.surface2 : TC.surface,
        transition: 'all 0.12s', cursor: article.url ? 'pointer' : 'default',
      }}
      onClick={() => article.url && window.open(article.url, '_blank')}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flex: 1 }}>
          <div style={{ color: TC.text, fontSize: 13, fontFamily: TC.fontUI, fontWeight: 500, lineHeight: 1.4, marginBottom: 6 }}>
            {article.title}
          </div>
          {article.summary && (
            <div style={{ color: TC.textMuted, fontSize: 11, fontFamily: TC.fontUI, lineHeight: 1.4, marginBottom: 8 }}>
              {article.summary}
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ color: TC.accent, fontSize: 10, fontFamily: TC.fontMono }}>{article.source}</span>
            <span style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono }}>
              {timeAgo(article.published_at)}
            </span>
            {article.url && (
              <span style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono }}>↗ Read</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
