from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NewsItem
from app.db.session import get_db

router = APIRouter(prefix="/news")


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
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Return news articles from DB. Populated by the 30-min scheduler job."""
    rows = (
        await db.execute(
            select(NewsItem)
            .order_by(NewsItem.published_at.desc().nullslast())
            .limit(limit)
        )
    ).scalars().all()
    return [_row_to_dict(r) for r in rows]


@router.post("/refresh")
async def refresh_news(background_tasks: BackgroundTasks):
    """Trigger an immediate news fetch in the background."""
    from app.scheduler.jobs import refresh_news_job
    background_tasks.add_task(refresh_news_job)
    return {"status": "refresh queued"}
