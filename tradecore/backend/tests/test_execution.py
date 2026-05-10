from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models import OHLCV, Position, Trade
from app.services.execution import execute_signal
from app.services.paper_broker import fill_paper_order
from app.services.rule_engine import TradeSignal
from app.state import app_state


SYMBOL = "BTC/USDT"
EXCHANGE = "binance"
PRICE = 50000.0


@pytest.fixture
async def db_with_price(db_session):
    db_session.add(
        OHLCV(
            time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            symbol=SYMBOL,
            exchange=EXCHANGE,
            open=PRICE,
            high=PRICE,
            low=PRICE,
            close=PRICE,
            volume=100.0,
        )
    )
    await db_session.commit()
    return db_session


async def test_paper_buy_creates_trade_and_position(db_with_price):
    strategy_id = uuid4()
    trade = await fill_paper_order(
        symbol=SYMBOL,
        exchange=EXCHANGE,
        side="buy",
        quantity_usdt=100.0,
        price=PRICE,
        strategy_id=strategy_id,
        trigger_score=0.6,
        db=db_with_price,
    )

    assert trade.side == "buy"
    assert abs(trade.quantity - 100.0 / PRICE) < 1e-9
    assert trade.price == PRICE
    assert trade.status == "filled"
    assert trade.mode == "paper"

    position = (
        await db_with_price.execute(
            select(Position).where(Position.symbol == SYMBOL, Position.is_open == True)
        )
    ).scalars().first()
    assert position is not None
    assert position.avg_entry_price == PRICE


async def test_paper_sell_closes_position_and_records_pnl(db_with_price):
    strategy_id = uuid4()
    entry_price = 45000.0

    # Seed an open position
    db_with_price.add(
        Position(
            symbol=SYMBOL,
            exchange=EXCHANGE,
            side="buy",
            quantity=0.002,
            avg_entry_price=entry_price,
            mode="paper",
            strategy_id=strategy_id,
            is_open=True,
        )
    )
    await db_with_price.commit()

    sell_trade = await fill_paper_order(
        symbol=SYMBOL,
        exchange=EXCHANGE,
        side="sell",
        quantity_usdt=0.0,
        price=PRICE,
        strategy_id=strategy_id,
        trigger_score=-0.5,
        db=db_with_price,
    )

    expected_pnl = (PRICE - entry_price) * 0.002
    assert sell_trade.side == "sell"
    assert abs(sell_trade.pnl - expected_pnl) < 1e-6

    position = (
        await db_with_price.execute(
            select(Position).where(Position.symbol == SYMBOL)
        )
    ).scalars().first()
    assert position.is_open == False
    assert abs(position.pnl - expected_pnl) < 1e-6


async def test_execute_hold_returns_none(db_with_price):
    signal = TradeSignal(action="hold", quantity_usdt=0.0, reason="neutral zone")
    result = await execute_signal(
        signal=signal,
        symbol=SYMBOL,
        exchange=EXCHANGE,
        strategy_id=uuid4(),
        trigger_score=None,
        db=db_with_price,
    )
    assert result is None


async def test_execute_paper_buy_creates_trade(db_with_price):
    app_state.trading_mode = "paper"
    signal = TradeSignal(action="buy", quantity_usdt=100.0, reason="buy zone signal")
    trade = await execute_signal(
        signal=signal,
        symbol=SYMBOL,
        exchange=EXCHANGE,
        strategy_id=uuid4(),
        trigger_score=0.5,
        db=db_with_price,
    )
    assert trade is not None
    assert trade.side == "buy"
    assert trade.mode == "paper"


async def test_execute_no_price_data_returns_none(db_session):
    app_state.trading_mode = "paper"
    signal = TradeSignal(action="buy", quantity_usdt=100.0, reason="buy zone signal")
    result = await execute_signal(
        signal=signal,
        symbol="UNKNOWN/USDT",
        exchange=EXCHANGE,
        strategy_id=uuid4(),
        trigger_score=None,
        db=db_session,
    )
    assert result is None


async def test_execute_sell_updates_daily_pnl(db_with_price):
    app_state.trading_mode = "paper"
    app_state.daily_pnl["paper"] = 0.0
    strategy_id = uuid4()

    # Open a position at a lower price first
    db_with_price.add(
        Position(
            symbol=SYMBOL,
            exchange=EXCHANGE,
            side="buy",
            quantity=0.001,
            avg_entry_price=40000.0,
            mode="paper",
            strategy_id=strategy_id,
            is_open=True,
        )
    )
    await db_with_price.commit()

    signal = TradeSignal(action="sell", quantity_usdt=0.0, reason="sell zone signal")
    trade = await execute_signal(
        signal=signal,
        symbol=SYMBOL,
        exchange=EXCHANGE,
        strategy_id=strategy_id,
        trigger_score=-0.5,
        db=db_with_price,
    )

    assert trade is not None
    expected_pnl = (PRICE - 40000.0) * 0.001
    assert abs(app_state.daily_pnl["paper"] - expected_pnl) < 1e-6


async def test_live_mode_calls_exchange_create_order(mocker, db_with_price):
    app_state.trading_mode = "live"
    mock_client = mocker.MagicMock()
    mock_client.create_order = mocker.AsyncMock(
        return_value={"id": "order123", "fee": {"cost": 0.5}}
    )
    mocker.patch(
        "app.services.execution.get_exchange_client",
        return_value=mock_client,
    )

    signal = TradeSignal(action="buy", quantity_usdt=100.0, reason="buy zone signal")
    trade = await execute_signal(
        signal=signal,
        symbol=SYMBOL,
        exchange=EXCHANGE,
        strategy_id=uuid4(),
        trigger_score=0.6,
        db=db_with_price,
    )

    assert mock_client.create_order.called
    assert trade is not None
    assert trade.mode == "live"
    assert trade.order_id == "order123"

    # Reset trading mode
    app_state.trading_mode = "paper"
