from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Position, Trade


async def _get_open_position(
    symbol: str,
    exchange: str,
    mode: str,
    db: AsyncSession,
) -> Position | None:
    return (
        await db.execute(
            select(Position).where(
                Position.symbol == symbol,
                Position.exchange == exchange,
                Position.mode == mode,
                Position.is_open == True,
            )
        )
    ).scalars().first()


async def fill_paper_order(
    symbol: str,
    exchange: str,
    side: str,
    quantity_usdt: float,
    price: float,
    strategy_id: UUID,
    trigger_score: float | None,
    db: AsyncSession,
) -> Trade:
    """
    Simulates an order fill at the given price.
    side="buy"  → opens a new Position (quantity = quantity_usdt / price)
    side="sell" → closes the open Position and computes PnL
    """
    mode = "paper"
    now = datetime.now(timezone.utc)

    if side == "buy":
        quantity = quantity_usdt / price
        trade = Trade(
            symbol=symbol,
            exchange=exchange,
            side="buy",
            quantity=quantity,
            price=price,
            status="filled",
            mode=mode,
            strategy_id=strategy_id,
            trigger_score=trigger_score,
            fees=0.0,
            pnl=None,
        )
        db.add(trade)

        position = Position(
            symbol=symbol,
            exchange=exchange,
            side="buy",
            quantity=quantity,
            avg_entry_price=price,
            mode=mode,
            strategy_id=strategy_id,
            is_open=True,
        )
        db.add(position)
        await db.commit()
        return trade

    # side == "sell"
    position = await _get_open_position(symbol, exchange, mode, db)
    quantity = position.quantity if position else 0.0
    entry_price = position.avg_entry_price if position else price
    pnl = (price - entry_price) * quantity

    trade = Trade(
        symbol=symbol,
        exchange=exchange,
        side="sell",
        quantity=quantity,
        price=price,
        status="filled",
        mode=mode,
        strategy_id=strategy_id,
        trigger_score=trigger_score,
        fees=0.0,
        pnl=pnl,
    )
    db.add(trade)

    if position is not None:
        position.is_open = False
        position.closed_at = now
        position.pnl = pnl

    await db.commit()
    return trade
