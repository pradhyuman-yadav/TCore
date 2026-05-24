from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Signal
from app.db.session import get_db

router = APIRouter(prefix="/signals")


@router.get("")
async def list_signals(
    limit: int = Query(default=200, ge=1, le=1000),
    symbol: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return historical signals from DB, newest first."""
    q = select(Signal).order_by(Signal.triggered_at.desc()).limit(limit)
    if symbol:
        q = q.where(Signal.symbol == symbol)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": str(r.id),
            "symbol": r.symbol,
            "exchange": r.exchange,
            "zone": r.zone,
            "score": r.score,
            "action": r.action,
            "reason": r.reason,
            "strategy_id": str(r.strategy_id) if r.strategy_id else None,
            "triggered_at": r.triggered_at.isoformat() if r.triggered_at else None,
        }
        for r in rows
    ]
