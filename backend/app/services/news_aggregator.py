from __future__ import annotations

import asyncio
import hashlib
import structlog
from datetime import datetime, timezone
from typing import Any

log = structlog.get_logger()

RSS_FEEDS = [
    ("CoinDesk",      "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt",       "https://decrypt.co/feed"),
    ("Reuters",       "https://feeds.reuters.com/reuters/businessNews"),
    ("ET Markets",    "https://economictimes.indiatimes.com/markets/rss.cms"),
]


def _parse_rss_feed_sync(url: str, source_name: str, limit: int = 20) -> list[dict]:
    """Parse RSS feed synchronously (run in thread pool)."""
    try:
        import feedparser  # type: ignore

        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:limit]:
            # Parse published date
            pub = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                import time as _time
                pub = datetime.fromtimestamp(
                    _time.mktime(entry.published_parsed), tz=timezone.utc
                )
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                import time as _time
                pub = datetime.fromtimestamp(
                    _time.mktime(entry.updated_parsed), tz=timezone.utc
                )
            else:
                pub = datetime.now(timezone.utc)

            items.append({
                "title": getattr(entry, "title", ""),
                "source": source_name,
                "published_at": pub,
                "url": getattr(entry, "link", None),
                "summary": getattr(entry, "summary", "")[:300],
            })
        return items
    except Exception as exc:
        log.warning("news.rss_error", source=source_name, url=url, error=str(exc))
        return []


async def fetch_rss_news(limit_per_feed: int = 15) -> list[dict]:
    """Fetch from all RSS feeds concurrently (in thread pools)."""
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, _parse_rss_feed_sync, url, name, limit_per_feed)
        for name, url in RSS_FEEDS
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items = []
    for r in results:
        if isinstance(r, list):
            items.extend(r)
    return items


async def fetch_openbb_news(symbols: list[str], limit: int = 20) -> list[dict]:
    """Fetch news from OpenBB for specified symbols."""
    items = []
    loop = asyncio.get_event_loop()

    def _fetch_sync(sym: str) -> list[dict]:
        try:
            from openbb import obb  # type: ignore
            result = obb.news.world(symbols=sym.split("/")[0], limit=limit)
            fetched = []
            for item in result.results:
                fetched.append({
                    "title": item.title,
                    "source": item.source or "OpenBB",
                    "published_at": item.date if isinstance(item.date, datetime) else datetime.now(timezone.utc),
                    "url": getattr(item, "url", None),
                    "summary": "",
                })
            return fetched
        except Exception as exc:
            log.warning("news.openbb_error", symbol=sym, error=str(exc))
            return []

    tasks = [loop.run_in_executor(None, _fetch_sync, sym) for sym in symbols[:5]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            items.extend(r)
    return items


def _dedup(items: list[dict]) -> list[dict]:
    """Deduplicate by URL (keep first seen) or by title hash."""
    seen: set[str] = set()
    out = []
    for item in items:
        key = item.get("url") or hashlib.md5(item["title"].encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


async def fetch_combined_news(
    symbols: list[str] | None = None,
    limit: int = 60,
) -> list[dict]:
    """
    Fetch news from OpenBB + RSS feeds, merge, dedup, sort by date.
    Returns list of dicts: {title, source, published_at, url, summary}
    """
    rss_task = fetch_rss_news(limit_per_feed=15)
    openbb_task = fetch_openbb_news(symbols or [], limit=15) if symbols else asyncio.sleep(0, result=[])

    rss_items, openbb_items = await asyncio.gather(rss_task, openbb_task, return_exceptions=True)

    all_items: list[dict] = []
    if isinstance(rss_items, list):
        all_items.extend(rss_items)
    if isinstance(openbb_items, list):
        all_items.extend(openbb_items)

    deduped = _dedup(all_items)
    deduped.sort(key=lambda x: x.get("published_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return deduped[:limit]
