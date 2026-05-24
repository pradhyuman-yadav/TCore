from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SocialPost
from app.db.session import get_db

router = APIRouter(prefix="/social")


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
    limit: int = Query(default=30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Return social posts from DB for the given platform. Populated by the 15-min scheduler job."""
    rows = (
        await db.execute(
            select(SocialPost)
            .where(SocialPost.platform == source)
            .order_by(SocialPost.published_at.desc().nullslast())
            .limit(limit)
        )
    ).scalars().all()
    return [_row_to_dict(r) for r in rows]


@router.post("/refresh")
async def refresh_social(background_tasks: BackgroundTasks):
    """Trigger an immediate social fetch in the background."""
    from app.scheduler.jobs import refresh_social_job
    background_tasks.add_task(refresh_social_job)
    return {"status": "refresh queued"}
