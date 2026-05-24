import { useEffect, useState, useCallback } from 'react'
import { api, SocialPost, FeedSource } from '../api'
import { TC } from '../theme'

type Source   = 'reddit' | 'twitter' | 'rss'
type Category = 'crypto' | 'us_stock' | 'indian_stock'

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

const CATEGORIES: { id: Category; label: string }[] = [
  { id: 'crypto',       label: 'Crypto'        },
  { id: 'us_stock',     label: 'US Stocks'     },
  { id: 'indian_stock', label: 'Indian Stocks' },
]

function SourcesPanel({ onClose }: { onClose: () => void }) {
  const [sources, setSources]   = useState<FeedSource[]>([])
  const [tab, setTab]           = useState<'reddit' | 'rss_social'>('reddit')
  const [category, setCategory] = useState<Category>('crypto')
  const [name, setName]         = useState('')
  const [url, setUrl]           = useState('')
  const [adding, setAdding]     = useState(false)
  const [err, setErr]           = useState<string | null>(null)

  const load = () => api.getSocialSources().then(setSources).catch(() => {})
  useEffect(() => { load() }, [])

  const visible = sources.filter(s =>
    s.type === tab && (tab === 'rss_social' ? true : s.category === category)
  )

  const add = async () => {
    if (!name.trim()) return
    if (tab === 'rss_social' && !url.trim()) return
    setAdding(true); setErr(null)
    try {
      await api.addSocialSource({
        type: tab,
        name: name.trim(),
        url: url.trim() || undefined,
        category: tab === 'reddit' ? category : category,
      })
      setName(''); setUrl('')
      await load()
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Failed')
    }
    setAdding(false)
  }

  const remove = async (id: string) => {
    await api.removeSocialSource(id).catch(() => {})
    await load()
  }

  const inp: React.CSSProperties = {
    padding: '5px 8px', background: TC.surface2, border: `1px solid ${TC.border}`,
    borderRadius: 4, color: TC.text, fontFamily: TC.fontMono, fontSize: 11,
    outline: 'none', width: '100%', boxSizing: 'border-box',
  }

  return (
    <div style={{
      width: 290, borderLeft: `1px solid ${TC.border}`, background: TC.surface,
      display: 'flex', flexDirection: 'column', flexShrink: 0,
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 14px', borderBottom: `1px solid ${TC.border}`,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <span style={{ color: TC.text, fontFamily: TC.fontMono, fontSize: 12, fontWeight: 700 }}>Sources</span>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', color: TC.textMuted,
          cursor: 'pointer', fontFamily: TC.fontMono, fontSize: 14, padding: 0,
        }}>✕</button>
      </div>

      {/* Type tabs */}
      <div style={{ display: 'flex', borderBottom: `1px solid ${TC.border}` }}>
        {(['reddit', 'rss_social'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            flex: 1, padding: '7px 0', background: tab === t ? TC.surface2 : 'transparent',
            border: 'none', borderBottom: tab === t ? `2px solid ${TC.accent}` : '2px solid transparent',
            color: tab === t ? TC.accent : TC.textMid, fontFamily: TC.fontMono, fontSize: 11,
            cursor: 'pointer', fontWeight: tab === t ? 700 : 400,
          }}>
            {t === 'reddit' ? 'Reddit' : 'RSS'}
          </button>
        ))}
      </div>

      {/* Category filter (reddit only) */}
      {tab === 'reddit' && (
        <div style={{ display: 'flex', padding: '6px 8px', gap: 4, borderBottom: `1px solid ${TC.border}` }}>
          {CATEGORIES.map(c => (
            <button key={c.id} onClick={() => setCategory(c.id)} style={{
              padding: '2px 8px', borderRadius: 3, border: 'none', cursor: 'pointer',
              background: category === c.id ? TC.accentDim : 'transparent',
              color: category === c.id ? TC.accent : TC.textMuted,
              fontFamily: TC.fontMono, fontSize: 10,
            }}>{c.label}</button>
          ))}
        </div>
      )}

      {/* Source list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
        {visible.length === 0 && (
          <div style={{ color: TC.textMuted, fontSize: 11, fontFamily: TC.fontMono, padding: '8px 14px' }}>
            None configured
          </div>
        )}
        {visible.map(s => (
          <div key={s.id} style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '6px 14px', borderBottom: `1px solid ${TC.border}`,
            opacity: s.is_active ? 1 : 0.4,
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ color: TC.text, fontFamily: TC.fontMono, fontSize: 11, fontWeight: 600 }}>
                {tab === 'reddit' ? `r/${s.name}` : s.name}
              </div>
              {s.url && (
                <div style={{ color: TC.textMuted, fontSize: 9.5, fontFamily: TC.fontMono, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.url}
                </div>
              )}
              {s.category && tab === 'rss_social' && (
                <div style={{ color: TC.textMuted, fontSize: 9, fontFamily: TC.fontMono }}>
                  {s.category}
                </div>
              )}
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
          {tab === 'reddit' ? 'Add Subreddit' : 'Add RSS Feed'}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {tab === 'reddit' ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 11 }}>r/</span>
              <input placeholder="subredditName" value={name} onChange={e => setName(e.target.value)} style={{ ...inp, flex: 1 }}/>
            </div>
          ) : (
            <>
              <input placeholder="Name (e.g. Bloomberg)" value={name} onChange={e => setName(e.target.value)} style={inp}/>
              <input placeholder="Feed URL" value={url} onChange={e => setUrl(e.target.value)} style={inp}/>
              <select value={category} onChange={e => setCategory(e.target.value as Category)} style={{ ...inp }}>
                {CATEGORIES.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
              </select>
            </>
          )}
          {err && <div style={{ color: TC.red, fontSize: 10, fontFamily: TC.fontMono }}>{err}</div>}
          <button onClick={add} disabled={adding || !name.trim()} style={{
            padding: '5px 0', background: TC.accent, border: 'none', borderRadius: 4,
            color: TC.bg, fontFamily: TC.fontMono, fontSize: 11, fontWeight: 700,
            cursor: adding ? 'wait' : 'pointer', opacity: !name.trim() ? 0.4 : 1,
          }}>
            {adding ? 'Adding…' : '+ Add'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Social() {
  const [source, setSource]         = useState<Source>('reddit')
  const [posts, setPosts]           = useState<SocialPost[]>([])
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const [showSources, setShowSources] = useState(false)

  const SOURCES: { id: Source; label: string }[] = [
    { id: 'reddit',  label: 'Reddit'  },
    { id: 'rss',     label: 'RSS'     },
    { id: 'twitter', label: 'Twitter' },
  ]

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getSocial(source, 40)
      setPosts(data)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to load'
      if (source === 'twitter' && (msg.includes('503') || msg.includes('404'))) {
        setError('Twitter/Nitter unavailable. Try Reddit or RSS.')
      } else {
        setError(msg)
      }
      setPosts([])
    }
    setLoading(false)
  }, [source])

  useEffect(() => { load() }, [load])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

      {/* Header */}
      <div style={{
        padding: '10px 18px', borderBottom: `1px solid ${TC.border}`,
        display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0,
        background: TC.surface, flexWrap: 'wrap',
      }}>
        <span style={{ color: TC.text, fontFamily: TC.fontMono, fontSize: 13, fontWeight: 700 }}>Social</span>
        <div style={{ width: 1, height: 18, background: TC.border }}/>

        {/* Source tabs */}
        <div style={{ display: 'flex', gap: 3 }}>
          {SOURCES.map(s => (
            <button key={s.id} onClick={() => setSource(s.id)} style={{
              padding: '4px 12px', borderRadius: 5, cursor: 'pointer',
              border: `1px solid ${source === s.id ? TC.accent : TC.border}`,
              background: source === s.id ? TC.accentDim : 'transparent',
              color: source === s.id ? TC.accent : TC.textMid,
              fontFamily: TC.fontMono, fontSize: 11, fontWeight: source === s.id ? 700 : 400,
            }}>{s.label}</button>
          ))}
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button onClick={load} disabled={loading} style={{
            padding: '3px 10px', background: 'transparent',
            border: `1px solid ${TC.border}`, borderRadius: 4,
            color: loading ? TC.textMuted : TC.textMid, fontFamily: TC.fontMono, fontSize: 10, cursor: 'pointer',
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

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 18px' }}>
          {loading && posts.length === 0 && (
            <div style={{ color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 12, textAlign: 'center', marginTop: 60 }}>
              Loading…
            </div>
          )}
          {error && (
            <div style={{
              padding: '12px 16px', borderRadius: 6, border: `1px solid rgba(255,68,68,0.3)`,
              background: 'rgba(255,68,68,0.06)', color: TC.red, fontFamily: TC.fontMono, fontSize: 11,
              marginBottom: 12,
            }}>
              ⚠ {error}
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {posts.map((post, i) => (
              <PostCard key={i} post={post} source={source}/>
            ))}
          </div>
          {!loading && !error && posts.length === 0 && (
            <div style={{ color: TC.textMuted, fontFamily: TC.fontMono, fontSize: 12, textAlign: 'center', marginTop: 60 }}>
              No posts found
            </div>
          )}
        </div>

        {showSources && <SourcesPanel onClose={() => setShowSources(false)}/>}
      </div>
    </div>
  )
}

function PostCard({ post, source }: { post: SocialPost; source: Source }) {
  const [hovered, setHovered] = useState(false)
  const platformCol: Record<string, string> = {
    reddit:  '#ff4500',
    twitter: '#1d9bf0',
    rss:     TC.accent,
  }
  const col = platformCol[post.platform] ?? TC.accent

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => post.url && window.open(post.url, '_blank')}
      style={{
        padding: '12px 16px', borderRadius: 6, cursor: post.url ? 'pointer' : 'default',
        border: `1px solid ${hovered ? TC.borderHi : TC.border}`,
        background: hovered ? TC.surface2 : TC.surface,
        transition: 'all 0.12s',
      }}
    >
      <div style={{ color: TC.text, fontSize: 13, fontFamily: TC.fontUI, fontWeight: 500, lineHeight: 1.4, marginBottom: 8 }}>
        {post.title}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ color: col, fontSize: 10, fontFamily: TC.fontMono, fontWeight: 600 }}>{post.source}</span>
        {source === 'reddit' && post.score > 0 && (
          <>
            <span style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono }}>▲ {post.score.toLocaleString()}</span>
            {post.comments > 0 && (
              <span style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono }}>💬 {post.comments}</span>
            )}
          </>
        )}
        <span style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono, marginLeft: 'auto' }}>
          {timeAgo(post.published_at)}
        </span>
        {post.url && <span style={{ color: TC.textMuted, fontSize: 10, fontFamily: TC.fontMono }}>↗</span>}
      </div>
    </div>
  )
}
