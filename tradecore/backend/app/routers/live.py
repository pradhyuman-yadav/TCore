from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Position, Trade
from app.db.session import get_db

router = APIRouter(prefix="/live")


@router.get("/positions")
async def get_live_positions(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(Position)
            .where(Position.mode == "live", Position.is_open == True)
            .order_by(Position.opened_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "symbol": r.symbol,
            "exchange": r.exchange,
            "side": r.side,
            "quantity": r.quantity,
            "avg_entry_price": r.avg_entry_price,
            "opened_at": r.opened_at.isoformat() if r.opened_at else None,
        }
        for r in rows
    ]


@router.get("/trades")
async def get_live_trades(limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(Trade)
            .where(Trade.mode == "live")
            .order_by(Trade.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "symbol": r.symbol,
            "side": r.side,
            "quantity": r.quantity,
            "price": r.price,
            "pnl": r.pnl,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
