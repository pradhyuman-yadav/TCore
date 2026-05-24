from __future__ import annotations

import asyncio
import structlog
from datetime import datetime, timezone

log = structlog.get_logger()

# Simple in-memory cache for Reddit results (avoids 429 on repeat page loads)
_reddit_cache: dict[str, tuple[list, float]] = {}
_REDDIT_CACHE_TTL = 300  # 5 minutes

NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
]

# Fallbacks used if DB is unavailable
_DEFAULT_REDDIT: dict[str, list[str]] = {
    "crypto":       ["Bitcoin", "CryptoCurrency", "ethtrader", "solana", "binance"],
    "us_stock":     ["wallstreetbets", "stocks", "investing"],
    "indian_stock": ["IndianStockMarket", "IndiaInvestments"],
}
_DEFAULT_CRYPTO_RSS = [
    ("CoinDesk",      "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt",       "https://decrypt.co/feed"),
    ("The Block",     "https://www.theblock.co/rss.xml"),
]
_DEFAULT_STOCK_RSS = [
    ("ET Markets",    "https://economictimes.indiatimes.com/markets/rss.cms"),
    ("Moneycontrol",  "https://www.moneycontrol.com/rss/MCtopnews.xml"),
    ("Reuters Biz",   "https://feeds.reuters.com/reuters/businessNews"),
]


async def _get_reddit_subs(category: str) -> list[str]:
    try:
        from sqlalchemy import select
        from app.db.models import FeedSource
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(FeedSource).where(
                    FeedSource.type == "reddit",
                    FeedSource.category == category,
                    FeedSource.is_active == True,
                )
            )).scalars().all()
        if rows:
            return [r.name for r in rows]
    except Exception:
        pass
    return _DEFAULT_REDDIT.get(category, [])


async def _get_rss_social(category: str) -> list[tuple[str, str]]:
    try:
        from sqlalchemy import select
        from app.db.models import FeedSource
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(FeedSource).where(
                    FeedSource.type == "rss_social",
                    FeedSource.category == category,
                    FeedSource.is_active == True,
                )
            )).scalars().all()
        if rows:
            return [(r.name, r.url) for r in rows if r.url]
    except Exception:
        pass
    return _DEFAULT_CRYPTO_RSS if category == "crypto" else _DEFAULT_STOCK_RSS


def _fetch_reddit_sync(subreddit: str, limit: int = 25) -> list[dict]:
    """Fetch hot posts from a subreddit using the public JSON API."""
    try:
        import urllib.request
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "TradeCore/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            import json
            data = json.loads(resp.read())
        posts = []
        for child in data.get("data", {}).get("children", []):
            p = child.get("data", {})
            created = p.get("created_utc", 0)
            posts.append({
                "title": p.get("title", ""),
                "source": f"r/{subreddit}",
                "url": f"https://reddit.com{p.get('permalink', '')}",
                "score": p.get("score", 0),
                "comments": p.get("num_comments", 0),
                "published_at": datetime.fromtimestamp(created, tz=timezone.utc) if created else datetime.now(timezone.utc),
                "platform": "reddit",
            })
        return posts
    except Exception as exc:
        log.warning("social.reddit_error", subreddit=subreddit, error=str(exc))
        return []


def _fetch_nitter_rss_sync(query: str, instance: str, limit: int = 20) -> list[dict]:
    """Fetch tweets via Nitter RSS (best-effort, may be unavailable)."""
    try:
        import feedparser  # type: ignore
        import urllib.parse
        q = urllib.parse.quote(query)
        url = f"{instance}/search/rss?q={q}&f=tweets"
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:limit]:
            pub = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                import time as _t
                pub = datetime.fromtimestamp(_t.mktime(entry.published_parsed), tz=timezone.utc)
            else:
                pub = datetime.now(timezone.utc)
            items.append({
                "title": getattr(entry, "title", ""),
                "source": "Twitter/X",
                "url": getattr(entry, "link", None),
                "score": 0,
                "comments": 0,
                "published_at": pub,
                "platform": "twitter",
            })
        return items
    except Exception as exc:
        log.debug("social.nitter_error", instance=instance, error=str(exc))
        return []


def _fetch_rss_sync(url: str, source_name: str, platform: str, limit: int = 20) -> list[dict]:
    """Fetch an RSS feed."""
    try:
        import feedparser  # type: ignore
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:limit]:
            pub = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                import time as _t
                pub = datetime.fromtimestamp(_t.mktime(entry.published_parsed), tz=timezone.utc)
            else:
                pub = datetime.now(timezone.utc)
            items.append({
                "title": getattr(entry, "title", ""),
                "source": source_name,
                "url": getattr(entry, "link", None),
                "score": 0,
                "comments": 0,
                "published_at": pub,
                "platform": platform,
            })
        return items
    except Exception as exc:
        log.warning("social.rss_error", source=source_name, error=str(exc))
        return []


async def fetch_reddit_posts(category: str = "crypto", limit_per_sub: int = 15) -> list[dict]:
    """Fetch Reddit posts for a given category — cached for 5 minutes."""
    import time
    now = time.monotonic()
    cached = _reddit_cache.get(category)
    if cached is not None:
        posts, ts = cached
        if now - ts < _REDDIT_CACHE_TTL:
            return posts

    subs = await _get_reddit_subs(category)
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, _fetch_reddit_sync, sub, limit_per_sub) for sub in subs]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items = []
    for r in results:
        if isinstance(r, list):
            items.extend(r)
    items.sort(key=lambda x: x.get("score", 0), reverse=True)
    _reddit_cache[category] = (items, now)
    return items


async def fetch_twitter_posts(query: str = "bitcoin OR crypto", limit: int = 20) -> list[dict]:
    """Fetch tweets via Nitter RSS (best-effort)."""
    loop = asyncio.get_event_loop()
    for instance in NITTER_INSTANCES:
        try:
            result = await loop.run_in_executor(
                None, _fetch_nitter_rss_sync, query, instance, limit
            )
            if result:
                return result
        except Exception:
            continue
    return []


async def fetch_rss_posts(category: str = "crypto") -> list[dict]:
    """Fetch from RSS feeds for the given category (loaded from DB)."""
    feeds = await _get_rss_social(category)
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, _fetch_rss_sync, url, name, "rss", 15) for name, url in feeds]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items = []
    for r in results:
        if isinstance(r, list):
            items.extend(r)
    items.sort(key=lambda x: x.get("published_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items


async def fetch_social(
    source: str = "reddit",
    category: str = "crypto",
    query: str = "bitcoin",
    limit: int = 30,
) -> list[dict]:
    """Main entry point. source: reddit | twitter | rss"""
    if source == "reddit":
        items = await fetch_reddit_posts(category=category)
    elif source == "twitter":
        items = await fetch_twitter_posts(query=query, limit=limit)
    elif source == "rss":
        items = await fetch_rss_posts(category=category)
    else:
        items = []
    return [
        {
            "title": item["title"],
            "source": item["source"],
            "url": item.get("url"),
            "score": item.get("score", 0),
            "comments": item.get("comments", 0),
            "published_at": item["published_at"].isoformat() if item.get("published_at") else None,
            "platform": item.get("platform", source),
        }
        for item in items[:limit]
    ]
