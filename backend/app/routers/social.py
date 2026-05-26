from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SocialPost
from app.db.session import get_db

router = APIRouter(prefix="/social")

_CATEGORY_SYMBOL = {
    "crypto":       "BTC/USDT",
    "us_stock":     "AAPL",
    "indian_stock": "RELIANCE.NS",
}
_IMPACT_LIMIT = 20


def _row_to_dict(r: SocialPost) -> dict:
    return {
        "title": r.title,
        "source": r.source,
        "url": r.url,
        "score": r.upvotes or 0,
        "comments": r.comments or 0,
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "platform": r.platform,
        "category": r.category,
        "impact_score": None,
    }


async def _add_impact(item: dict, db: AsyncSession) -> dict:
    """Attach price-impact score to a social post (cache-first)."""
    try:
        from app.services.sentiment_agent import get_source_reach, _get_symbol_volume, score_price_impact
        symbol  = _CATEGORY_SYMBOL.get(item.get("category") or "", "BTC/USDT")
        reach   = await get_source_reach(item["source"], item["platform"])
        volume  = await _get_symbol_volume(symbol, db)
        item["impact_score"] = await score_price_impact(
            item["title"], symbol, reach, volume, db=db
        )
    except Exception:
        pass
    return item


@router.get("")
async def get_social(
    source: str = Query(default="reddit", description="reddit | twitter | rss"),
    category: str | None = Query(default=None, description="crypto | us_stock | indian_stock"),
    limit: int = Query(default=30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Return social posts from DB with price-impact scores. Populated by the 15-min scheduler job."""
    q = (
        select(SocialPost)
        .where(SocialPost.platform == source)
        .order_by(SocialPost.published_at.desc().nullslast())
        .limit(limit)
    )
    if category:
        q = q.where(SocialPost.category == category)
    rows = (await db.execute(q)).scalars().all()
    items = [_row_to_dict(r) for r in rows]

    if items:
        scored = await asyncio.gather(*[_add_impact(i, db) for i in items[:_IMPACT_LIMIT]])
        items = list(scored) + items[_IMPACT_LIMIT:]

    return items


@router.post("/refresh")
async def refresh_social(background_tasks: BackgroundTasks):
    """Trigger an immediate social fetch in the background."""
    from app.scheduler.jobs import refresh_social_job
    background_tasks.add_task(refresh_social_job)
    return {"status": "refresh queued"}
