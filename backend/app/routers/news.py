from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NewsItem
from app.db.session import get_db

router = APIRouter(prefix="/news")

_CACHE_MINUTES = 30


def _content_hash(title: str) -> str:
    return hashlib.md5(title.encode()).hexdigest()


def _row_to_dict(r: NewsItem) -> dict:
    return {
        "title": r.title,
        "source": r.source,
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "url": r.url,
        "summary": r.summary or "",
    }


@router.get("")
async def get_news(
    symbols: str | None = Query(default=None, description="Comma-separated symbols e.g. BTC/USDT,ETH/USDT"),
    limit: int = Query(default=50, ge=1, le=200),
    refresh: bool = Query(default=False, description="Force re-fetch from live sources"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return news articles. Serves from DB cache (30-min TTL) unless refresh=true.
    On cache miss or refresh, fetches live from OpenBB + RSS and upserts to DB.
    """
    if not refresh:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=_CACHE_MINUTES)
        count = await db.scalar(
            select(func.count()).select_from(NewsItem).where(NewsItem.fetched_at >= cutoff)
        )
        if count and count > 0:
            rows = (
                await db.execute(
                    select(NewsItem)
                    .order_by(NewsItem.published_at.desc().nullslast())
                    .limit(limit)
                )
            ).scalars().all()
            return [_row_to_dict(r) for r in rows]

    # Fetch live and upsert
    from app.services.news_aggregator import fetch_combined_news
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    sym_list = [s.strip() for s in symbols.split(",")] if symbols else []
    items = await fetch_combined_news(symbols=sym_list or None, limit=limit)
    now = datetime.now(timezone.utc)

    for item in items:
        title = item.get("title", "").strip()
        if not title:
            continue
        ch = _content_hash(title)
        stmt = pg_insert(NewsItem).values(
            title=title,
            source=item.get("source"),
            published_at=item.get("published_at"),
            url=item.get("url"),
            summary=(item.get("summary") or "")[:500],
            content_hash=ch,
            fetched_at=now,
        ).on_conflict_do_update(
            index_elements=["content_hash"],
            set_={"fetched_at": now, "url": item.get("url"), "summary": (item.get("summary") or "")[:500]},
        )
        await db.execute(stmt)

    await db.commit()

    rows = (
        await db.execute(
            select(NewsItem)
            .order_by(NewsItem.published_at.desc().nullslast())
            .limit(limit)
        )
    ).scalars().all()
    return [_row_to_dict(r) for r in rows]
