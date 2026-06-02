from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EventLog
from app.db.session import get_db
from app.services.event_log import VALID_CATEGORIES, VALID_LEVELS

router = APIRouter(prefix="/events")


@router.get("")
async def list_events(
    limit: int = Query(200, ge=1, le=2000),
    category: str | None = None,
    level: str | None = None,
    symbol: str | None = None,
    since: str | None = Query(None, description="ISO timestamp — only events at/after this time"),
    db: AsyncSession = Depends(get_db),
):
    """Query the system event log, newest first, with optional filters."""
    filters = []
    if category and category in VALID_CATEGORIES:
        filters.append(EventLog.category == category)
    if level and level in VALID_LEVELS:
        filters.append(EventLog.level == level)
    if symbol:
        filters.append(EventLog.symbol == symbol)
    if since:
        try:
            filters.append(EventLog.ts >= datetime.fromisoformat(since).replace(tzinfo=timezone.utc))
        except ValueError:
            pass

    rows = (
        await db.execute(
            select(EventLog).where(*filters).order_by(EventLog.ts.desc()).limit(limit)
        )
    ).scalars().all()

    return [
        {
            "ts": r.ts.isoformat() if r.ts else None,
            "id": str(r.id),
            "category": r.category,
            "level": r.level,
            "symbol": r.symbol,
            "message": r.message,
            "payload": r.payload or {},
        }
        for r in rows
    ]


@router.get("/categories")
async def list_categories():
    """Expose the valid categories/levels so the UI can build filter chips."""
    return {"categories": sorted(VALID_CATEGORIES), "levels": sorted(VALID_LEVELS)}
