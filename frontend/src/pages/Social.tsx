import { useEffect, useState, useCallback } from 'react'
import { api, SocialPost } from '../api'
import { TC } from '../theme'

type Source = 'reddit' | 'twitter' | 'rss'
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

export default function Social() {
  const [source, setSource]     = useState<Source>('reddit')
  const [category, setCategory] = useState<Category>('crypto')
  const [posts, setPosts]       = useState<SocialPost[]>([])
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)

  const SOURCES: { id: Source; label: string }[] = [
    { id: 'reddit',  label: 'Reddit'  },
    { id: 'rss',     label: 'RSS'     },
    { id: 'twitter', label: 'Twitter' },
  ]

  const CATEGORIES: { id: Category; label: string }[] = [
    { id: 'crypto',       label: 'Crypto'       },
    { id: 'us_stock',     label: 'US Stocks'    },
    { id: 'indian_stock', label: 'Indian Stocks' },
  ]

  const TWITTER_QUERIES: Record<Category, string> = {
    crypto:       'bitcoin OR ethereum OR crypto',
    us_stock:     'stocks OR wallstreetbets OR investing',
    indian_stock: 'nifty50 OR sensex OR IndianStocks',
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getSocial(source, category, TWITTER_QUERIES[category], 40)
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
  }, [source, category])

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

        <div style={{ width: 1, height: 18, background: TC.border }}/>

        {/* Category filter */}
        <div style={{ display: 'flex', gap: 3 }}>
          {CATEGORIES.map(c => (
            <button key={c.id} onClick={() => setCategory(c.id)} style={{
              padding: '3px 9px', borderRadius: 4, cursor: 'pointer', border: 'none',
              background: category === c.id ? TC.surface3 : 'transparent',
              color: category === c.id ? TC.text : TC.textMuted,
              fontFamily: TC.fontMono, fontSize: 11,
            }}>{c.label}</button>
          ))}
        </div>

        <button onClick={load} disabled={loading} style={{
          marginLeft: 'auto', padding: '3px 10px', background: 'transparent',
          border: `1px solid ${TC.border}`, borderRadius: 4,
          color: loading ? TC.textMuted : TC.textMid, fontFamily: TC.fontMono, fontSize: 10, cursor: 'pointer',
        }}>
          {loading ? '⟳ Loading…' : '⟳ Refresh'}
        </button>
      </div>

      {/* Content */}
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
