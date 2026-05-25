import { useEffect, useState, useCallback } from 'react'
import { api, NewsArticle, FeedSource } from '../api'
import { useStore } from '../store'
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

function SourcesPanel({ onClose }: { onClose: () => void }) {
  const [sources, setSources] = useState<FeedSource[]>([])
  const [name, setName]       = useState('')
  const [url, setUrl]         = useState('')
  const [adding, setAdding]   = useState(false)
  const [err, setErr]         = useState<string | null>(null)

  const load = () => api.getNewsSources().then(setSources).catch(() => {})
  useEffect(() => { load() }, [])

  const add = async () => {
    if (!name.trim() || !url.trim()) return
    setAdding(true); setErr(null)
    try {
      await api.addNewsSource(name.trim(), url.trim())
      setName(''); setUrl('')
      await load()
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Failed')
    }
    setAdding(false)
  }

  const remove = async (id: string) => {
    await api.removeNewsSource(id).catch(() => {})
    await load()
  }

  const inp: React.CSSProperties = {
    padding: '5px 8px', background: TC.surface2, border: `1px solid ${TC.border}`,
    borderRadius: 4, color: TC.text, fontFamily: TC.fontMono, fontSize: 11,
    outline: 'none', width: '100%', boxSizing: 'border-box',
  }

  return (
    <div style={{
      width: 280, borderLeft: `1px solid ${TC.border}`, background: TC.surface,
      display: 'flex', flexDirection: 'column', flexShrink: 0,
    }}>
      <div style={{
        padding: '10px 14px', borderBottom: `1px solid ${TC.border}`,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <span style={{ color: TC.text, fontFamily: TC.fontMono, fontSize: 12, fontWeight: 700 }}>
          RSS Sources
        </span>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', color: TC.textMuted,
          cursor: 'pointer', fontFamily: TC.fontMono, fontSize: 14, padding: 0,
        }}>✕</button>
      </div>

      {/* Current sources */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {sources.length === 0 && (
          <div style={{ color: TC.textMuted, fontSize: 11, fontFamily: TC.fontMono, padding: '8px 14px' }}>
            No sources yet
          </div>
        )}
        {sources.map(s => (
          <div key={s.id} style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '6px 14px', borderBottom: `1px solid ${TC.border}`,
            opacity: s.is_active ? 1 : 0.4,
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ color: s.is_active ? TC.text : TC.textMuted, fontFamily: TC.fontMono, fontSize: 11, fontWeight: 600 }}>
                {s.name}
              </div>
              <div style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {s.url}
              </div>
            </div>
            {s.is_active && (
              <button onClick={() => remove(s.id)} title="Remove" style={{
                background: 'none', border: 'none', color: TC.textMuted,
                cursor: 'pointer', fontSize: 12, padding: '0 2px', flexShrink: 0,
              }}>✕</button>
            )}
          </div>
        ))}
      </div>

      {/* Add form */}
      <div style={{ padding: '12px 14px', borderTop: `1px solid ${TC.border}` }}>
        <div style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono, letterSpacing: '0.1em', marginBottom: 8, textTransform: 'uppercase' }}>
          Add RSS Feed
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <input placeholder="Name (e.g. Bloomberg)" value={name} onChange={e => setName(e.target.value)} style={inp}/>
          <input placeholder="Feed URL" value={url} onChange={e => setUrl(e.target.value)} style={inp}/>
          {err && <div style={{ color: TC.red, fontSize: 10, fontFamily: TC.fontMono }}>{err}</div>}
          <button onClick={add} disabled={adding || !name.trim() || !url.trim()} style={{
            padding: '5px 0', background: TC.accent, border: 'none', borderRadius: 4,
            color: TC.bg, fontFamily: TC.fontMono, fontSize: 11, fontWeight: 700,
            cursor: adding ? 'wait' : 'pointer', opacity: (!name.trim() || !url.trim()) ? 0.4 : 1,
          }}>
            {adding ? 'Adding…' : '+ Add Feed'}
          </button>
        </div>
      </div>
    </div>
  )
}

const CAT_TABS = [
  { id: '',       label: 'All'    },
  { id: 'crypto', label: 'Crypto' },
  { id: 'stock',  label: 'Stocks' },
]

export default function News() {
  const workspace = useStore(s => s.workspace)
  const [articles, setArticles]   = useState<NewsArticle[]>([])
  const [loading, setLoading]     = useState(true)
  const [category, setCategory]   = useState<string>(() => workspace === 'crypto' ? 'crypto' : 'stock')
  const [sourceFilter, setSourceFilter] = useState('All')
  const [lastRefresh, setLastRefresh]   = useState<Date | null>(null)
  const [showSources, setShowSources]   = useState(false)

  // Sync category with workspace when workspace changes
  useEffect(() => {
    setCategory(workspace === 'crypto' ? 'crypto' : 'stock')
    setSourceFilter('All')
  }, [workspace])

  // Derive unique sources from loaded articles for the source sub-filter
  const knownSources = ['All', ...Array.from(new Set(articles.map(a => a.source).filter(Boolean)))]

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getNews(100, category || undefined)
      setArticles(data)
      setLastRefresh(new Date())
    } catch { /* ignore */ }
    setLoading(false)
  }, [category])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const id = setInterval(load, REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  // Source sub-filter applied client-side on top of category
  const filtered = sourceFilter === 'All'
    ? articles
    : articles.filter(a => a.source?.toLowerCase().includes(sourceFilter.toLowerCase()))

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
        {/* Category tabs */}
        <div style={{ display: 'flex', gap: 3 }}>
          {CAT_TABS.map(t => (
            <button key={t.id} onClick={() => { setCategory(t.id); setSourceFilter('All') }} style={{
              padding: '4px 12px', borderRadius: 5, cursor: 'pointer',
              border: `1px solid ${category === t.id ? TC.accent : TC.border}`,
              background: category === t.id ? TC.accentDim : 'transparent',
              color: category === t.id ? TC.accent : TC.textMid,
              fontFamily: TC.fontMono, fontSize: 11, fontWeight: category === t.id ? 700 : 400,
            }}>{t.label}</button>
          ))}
        </div>
        <div style={{ width: 1, height: 18, background: TC.border }}/>
        {/* Source sub-filter */}
        <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
          {knownSources.slice(0, 8).map(s => (
            <button key={s} onClick={() => setSourceFilter(s)} style={{
              padding: '3px 9px', borderRadius: 4, cursor: 'pointer', border: 'none',
              background: sourceFilter === s ? TC.surface3 : 'transparent',
              color: sourceFilter === s ? TC.text : TC.textMuted,
              fontFamily: TC.fontMono, fontSize: 10,
            }}>{s}</button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
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
          <button onClick={() => setShowSources(v => !v)} style={{
            padding: '3px 10px', background: showSources ? TC.accentDim : 'transparent',
            border: `1px solid ${showSources ? TC.accent : TC.border}`,
            borderRadius: 4, color: showSources ? TC.accent : TC.textMid,
            fontFamily: TC.fontMono, fontSize: 10, cursor: 'pointer',
          }}>
            ⚙ Sources
          </button>
        </div>
      </div>

      {/* Body: article list + optional sources panel */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
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

        {showSources && <SourcesPanel onClose={() => setShowSources(false)}/>}
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
