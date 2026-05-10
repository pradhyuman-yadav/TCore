from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OHLCV, Trade
from app.services.exchange_client import get_exchange_client
from app.services.rule_engine import TradeSignal
from app.state import app_state


async def _latest_price(symbol: str, exchange: str, db: AsyncSession) -> float | None:
    row = (
        await db.execute(
            select(OHLCV)
            .where(OHLCV.symbol == symbol, OHLCV.exchange == exchange)
            .order_by(OHLCV.time.desc())
            .limit(1)
        )
    ).scalars().first()
    return float(row.close) if row and row.close is not None else None


async def execute_signal(
    signal: TradeSignal,
    symbol: str,
    exchange: str,
    strategy_id: UUID,
    trigger_score: float | None,
    db: AsyncSession,
) -> Trade | None:
    """
    Dispatches a TradeSignal to paper or live broker.
    Returns the recorded Trade, or None for hold/error.
    """
    if signal.action == "hold":
        return None

    mode = app_state.trading_mode
    price = await _latest_price(symbol, exchange, db)
    if price is None:
        return None

    trade: Trade | None = None

    if mode == "paper":
        from app.services.paper_broker import fill_paper_order

        trade = await fill_paper_order(
            symbol=symbol,
            exchange=exchange,
            side=signal.action,
            quantity_usdt=signal.quantity_usdt,
            price=price,
            strategy_id=strategy_id,
            trigger_score=trigger_score,
            db=db,
        )
    else:
        # Live mode — call exchange
        client = get_exchange_client()
        quantity = signal.quantity_usdt / price if signal.action == "buy" else 0.0

        try:
            order = await client.create_order(
                symbol=symbol,
                type="market",
                side=signal.action,
                amount=quantity,
            )
        except Exception:
            return None

        trade = Trade(
            symbol=symbol,
            exchange=exchange,
            side=signal.action,
            quantity=quantity,
            price=price,
            status="filled",
            mode="live",
            strategy_id=strategy_id,
            trigger_score=trigger_score,
            order_id=str(order.get("id", "")),
            fees=float(order.get("fee", {}).get("cost", 0.0)),
        )
        db.add(trade)
        await db.commit()

    # Update daily PnL for sell trades
    if trade and signal.action == "sell" and trade.pnl is not None:
        app_state.daily_pnl[mode] = app_state.daily_pnl.get(mode, 0.0) + trade.pnl

    return trade
