from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Position, Trade
from app.state import app_state


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

    # Pull fee + slippage config from app_state (can be tuned via /paper/account)
    account   = app_state.paper_account
    fee_rate  = float(account.get("fee_rate", 0.001))
    slip      = float(account.get("slippage_bps", 5)) / 10_000

    if side == "buy":
        fill_price = price * (1 + slip)          # adverse slippage on entry
        quantity   = quantity_usdt / fill_price
        buy_fee    = fill_price * quantity * fee_rate

        trade = Trade(
            symbol=symbol,
            exchange=exchange,
            side="buy",
            quantity=quantity,
            price=fill_price,
            status="filled",
            mode=mode,
            strategy_id=strategy_id,
            trigger_score=trigger_score,
            fees=round(buy_fee, 8),
            pnl=None,
        )
        db.add(trade)

        position = Position(
            symbol=symbol,
            exchange=exchange,
            side="buy",
            quantity=quantity,
            avg_entry_price=fill_price,
            mode=mode,
            strategy_id=strategy_id,
            is_open=True,
        )
        db.add(position)
        await db.commit()
        return trade

    # side == "sell"
    position   = await _get_open_position(symbol, exchange, mode, db)
    quantity   = position.quantity    if position else 0.0
    entry_price = position.avg_entry_price if position else price

    fill_price = price * (1 - slip)                          # adverse slippage on exit
    sell_fee   = fill_price * quantity * fee_rate
    # entry fee was already charged on the buy trade; include it in round-trip cost
    entry_fee  = entry_price * quantity * fee_rate
    gross_pnl  = (fill_price - entry_price) * quantity
    net_pnl    = gross_pnl - sell_fee - entry_fee

    trade = Trade(
        symbol=symbol,
        exchange=exchange,
        side="sell",
        quantity=quantity,
        price=fill_price,
        status="filled",
        mode=mode,
        strategy_id=strategy_id,
        trigger_score=trigger_score,
        fees=round(sell_fee, 8),
        pnl=round(net_pnl, 8),
    )
    db.add(trade)

    if position is not None:
        position.is_open  = False
        position.closed_at = now
        position.pnl = round(net_pnl, 8)

    await db.commit()
    return trade
