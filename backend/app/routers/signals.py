from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IndicatorSnapshot, Signal
from app.db.session import get_db

router = APIRouter(prefix="/signals")


@router.get("")
async def list_signals(
    limit: int = Query(default=200, ge=1, le=1000),
    symbol: str | None = Query(default=None),
    asset_type: str | None = Query(default=None, description="crypto | stock"),
    db: AsyncSession = Depends(get_db),
):
    """Return historical signals from DB, newest first."""
    q = select(Signal).order_by(Signal.triggered_at.desc()).limit(limit)
    if symbol:
        q = q.where(Signal.symbol == symbol)
    if asset_type == "crypto":
        q = q.where(Signal.exchange.ilike("%binance%"))
    elif asset_type == "stock":
        q = q.where(~Signal.exchange.ilike("%binance%"))
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


@router.get("/indicators")
async def get_latest_indicators(
    symbol: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recent indicator snapshot rows for a symbol (covers one full trading cycle)."""
    # Fetch last 20 rows — one cycle snapshot has ≤10 indicators so this covers it fully
    rows = (
        await db.execute(
            select(IndicatorSnapshot)
            .where(IndicatorSnapshot.symbol == symbol)
            .order_by(IndicatorSnapshot.time.desc())
            .limit(20)
        )
    ).scalars().all()

    # Deduplicate to the most recent value per indicator
    seen: set[str] = set()
    unique: list[IndicatorSnapshot] = []
    for r in rows:
        if r.indicator_name not in seen:
            seen.add(r.indicator_name)
            unique.append(r)

    return [
        {
            "indicator_name": r.indicator_name,
            "value": r.value,
            "weight": r.weight or 0.0,
            "weighted_value": r.weighted_value or 0.0,
            "time": r.time.isoformat() if r.time else None,
        }
        for r in unique
    ]
