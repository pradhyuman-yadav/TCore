from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SocialPost
from app.db.session import get_db

router = APIRouter(prefix="/social")

_CACHE_MINUTES = 15


def _content_hash(title: str, url: str | None) -> str:
    key = url if url else title
    return hashlib.md5(key.encode()).hexdigest()


def _row_to_dict(r: SocialPost) -> dict:
    return {
        "title": r.title,
        "source": r.source,
        "url": r.url,
        "score": r.upvotes or 0,
        "comments": r.comments or 0,
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "platform": r.platform,
    }


@router.get("")
async def get_social(
    source: str = Query(default="reddit", description="reddit | twitter | rss"),
    category: str = Query(default="crypto", description="crypto | us_stock | indian_stock"),
    query: str = Query(default="bitcoin OR crypto", description="Search query for twitter"),
    limit: int = Query(default=30, ge=1, le=100),
    refresh: bool = Query(default=False, description="Force re-fetch from live sources"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return social posts. Serves from DB cache (15-min TTL per platform) unless refresh=true.
    On cache miss or refresh, fetches live and upserts to DB.
    """
    if not refresh:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=_CACHE_MINUTES)
        count = await db.scalar(
            select(func.count()).select_from(SocialPost).where(
                SocialPost.platform == source,
                SocialPost.fetched_at >= cutoff,
            )
        )
        if count and count > 0:
            rows = (
                await db.execute(
                    select(SocialPost)
                    .where(SocialPost.platform == source)
                    .order_by(SocialPost.published_at.desc().nullslast())
                    .limit(limit)
                )
            ).scalars().all()
            return [_row_to_dict(r) for r in rows]

    # Fetch live and upsert
    from app.services.social_aggregator import fetch_social
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    items = await fetch_social(source=source, category=category, query=query, limit=limit)
    now = datetime.now(timezone.utc)

    for item in items:
        title = item.get("title", "").strip()
        if not title:
            continue
        url = item.get("url")
        ch = _content_hash(title, url)
        pub = None
        if item.get("published_at"):
            try:
                pub = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
            except Exception:
                pub = None
        stmt = pg_insert(SocialPost).values(
            platform=item.get("platform", source),
            source=item.get("source"),
            title=title,
            url=url,
            upvotes=item.get("score", 0),
            comments=item.get("comments", 0),
            published_at=pub,
            content_hash=ch,
            fetched_at=now,
        ).on_conflict_do_update(
            index_elements=["content_hash"],
            set_={
                "upvotes": item.get("score", 0),
                "comments": item.get("comments", 0),
                "fetched_at": now,
            },
        )
        await db.execute(stmt)

    await db.commit()

    rows = (
        await db.execute(
            select(SocialPost)
            .where(SocialPost.platform == source)
            .order_by(SocialPost.published_at.desc().nullslast())
            .limit(limit)
        )
    ).scalars().all()
    return [_row_to_dict(r) for r in rows]
