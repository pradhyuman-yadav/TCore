from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Position, Trade
from app.db.session import get_db
from app.state import app_state

router = APIRouter(prefix="/paper")


class PaperAccountConfig(BaseModel):
    initial_capital: float = Field(10_000.0, gt=0)
    fee_rate: float = Field(0.001, ge=0, le=0.05)   # max 5% sanity cap
    slippage_bps: float = Field(5.0, ge=0, le=500)  # max 5% sanity cap


@router.get("/account")
async def get_paper_account(db: AsyncSession = Depends(get_db)):
    """Return paper account config + live PnL summary."""
    # Realized PnL = sum of all paper sell trade PnLs
    realized_pnl = (
        await db.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0))
            .where(Trade.mode == "paper", Trade.side == "sell", Trade.pnl.isnot(None))
        )
    ).scalar_one()

    open_count = (
        await db.execute(
            select(func.count()).where(Position.mode == "paper", Position.is_open == True)
        )
    ).scalar_one()

    return {
        **app_state.paper_account,
        "realized_pnl": float(realized_pnl),
        "open_positions": int(open_count),
    }


@router.put("/account")
async def set_paper_account(config: PaperAccountConfig):
    """Update paper account configuration."""
    app_state.paper_account.update(config.model_dump())
    return app_state.paper_account


@router.get("/positions")
async def get_paper_positions(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(Position)
            .where(Position.mode == "paper", Position.is_open == True)
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
async def get_paper_trades(limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(Trade)
            .where(Trade.mode == "paper")
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
