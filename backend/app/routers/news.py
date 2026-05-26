from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NewsItem
from app.db.session import get_db

router = APIRouter(prefix="/news")

# Symbol to use for volume/impact lookup per category
_CATEGORY_SYMBOL = {
    "crypto": "BTC/USDT",
    "stock":  "AAPL",
}
_IMPACT_LIMIT = 20   # max items to score per request (cache handles repeats)


def _row_to_dict(r: NewsItem) -> dict:
    return {
        "title": r.title,
        "source": r.source,
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "url": r.url,
        "summary": r.summary or "",
        "category": r.category,
        "impact_score": None,
    }


async def _add_impact(item: dict, db: AsyncSession) -> dict:
    """Attach price-impact score to a news item (cache-first, no Claude call if cached)."""
    try:
        from app.services.sentiment_agent import get_source_reach, _get_symbol_volume, score_price_impact
        symbol = _CATEGORY_SYMBOL.get(item.get("category") or "", "BTC/USDT")
        reach  = await get_source_reach(item["source"], "rss")
        volume = await _get_symbol_volume(symbol, db)
        item["impact_score"] = await score_price_impact(
            item["title"], symbol, reach, volume, db=db
        )
    except Exception:
        pass
    return item


@router.get("")
async def get_news(
    limit: int = Query(default=50, ge=1, le=200),
    category: str | None = Query(default=None, description="crypto | stock"),
    db: AsyncSession = Depends(get_db),
):
    """Return news articles from DB with price-impact scores. Populated by the 30-min scheduler job."""
    q = select(NewsItem).order_by(NewsItem.published_at.desc().nullslast()).limit(limit)
    if category:
        q = q.where(NewsItem.category == category)
    rows = (await db.execute(q)).scalars().all()
    items = [_row_to_dict(r) for r in rows]

    # Score top N items concurrently; remainder keep impact_score=None
    if items:
        scored = await asyncio.gather(*[_add_impact(i, db) for i in items[:_IMPACT_LIMIT]])
        items = list(scored) + items[_IMPACT_LIMIT:]

    return items


@router.post("/refresh")
async def refresh_news(background_tasks: BackgroundTasks):
    """Trigger an immediate news fetch in the background."""
    from app.scheduler.jobs import refresh_news_job
    background_tasks.add_task(refresh_news_job)
    return {"status": "refresh queued"}
