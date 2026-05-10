"""Stage 14 — end-to-end trading cycle: OHLCV seed → composite → rule → paper fill."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OHLCV, Position, Trade
from app.scheduler.jobs import run_trading_cycle
from app.state import app_state

SYMBOL = "BTC/USDT"
EXCHANGE = "binance"
_STRATEGY_ID = str(uuid.uuid4())

_STRATEGY = {
    "id": _STRATEGY_ID,
    "name": "e2e_test_strategy",
    "symbol": SYMBOL,
    "exchange": EXCHANGE,
    "timeframe": "1h",
    "refresh_cadence_seconds": 300,
    # Only news_sentiment (weight=1.0) so composite score == sentiment score exactly
    "indicators": {
        "news_sentiment": {"weight": 1.0, "cache_ttl_minutes": 0},
    },
    "rules": {"buy_threshold": 0.45, "sell_threshold": -0.35},
    "position_sizing": {"mode": "fixed_usdt", "amount": 100, "max_open_positions": 1},
    "risk": {"max_daily_loss_usdt": 200},
}


@dataclass
class _Headline:
    title: str


def _make_ohlcv_rows(n: int = 60, price: float = 50_000.0) -> list[OHLCV]:
    now = datetime.now(timezone.utc)
    return [
        OHLCV(
            time=now - timedelta(hours=(n - i)),
            symbol=SYMBOL,
            exchange=EXCHANGE,
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            volume=100.0,
        )
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def _reset_app_state():
    saved = (
        app_state.active_strategy,
        app_state.trading_mode,
        app_state.kill_switch,
        dict(app_state.daily_pnl),
    )
    app_state.active_strategy = dict(_STRATEGY)
    app_state.trading_mode = "paper"
    app_state.kill_switch = False
    app_state.daily_pnl = {}
    yield
    (
        app_state.active_strategy,
        app_state.trading_mode,
        app_state.kill_switch,
        app_state.daily_pnl,
    ) = saved


# ── helpers ──────────────────────────────────────────────────────────────────

def _mock_sentiment(mocker, score: float):
    mocker.patch(
        "app.scheduler.jobs.fetch_news_headlines",
        new_callable=AsyncMock,
        return_value=[_Headline("BTC headline 1"), _Headline("BTC headline 2")],
    )
    mocker.patch(
        "app.scheduler.jobs.score_sentiment",
        new_callable=AsyncMock,
        return_value=score,
    )


# ── tests ─────────────────────────────────────────────────────────────────────

async def test_buy_cycle_creates_trade_and_position(db_session: AsyncSession, mocker):
    """Bullish sentiment → composite 0.8 (> buy_threshold 0.45) → paper buy trade + open position."""
    for row in _make_ohlcv_rows():
        db_session.add(row)
    await db_session.commit()

    _mock_sentiment(mocker, score=0.8)

    await run_trading_cycle()

    trades = (
        await db_session.execute(
            select(Trade).where(Trade.symbol == SYMBOL, Trade.mode == "paper")
        )
    ).scalars().all()
    assert len(trades) == 1, f"expected 1 trade, got {len(trades)}"
    assert trades[0].side == "buy"
    assert trades[0].status == "filled"
    assert trades[0].price == pytest.approx(50_000.0)
    assert trades[0].quantity == pytest.approx(100.0 / 50_000.0)

    positions = (
        await db_session.execute(
            select(Position).where(Position.symbol == SYMBOL, Position.is_open == True)
        )
    ).scalars().all()
    assert len(positions) == 1
    assert positions[0].avg_entry_price == pytest.approx(50_000.0)


async def test_sell_cycle_closes_position_with_pnl(db_session: AsyncSession, mocker):
    """Buy at 50k → price stays flat → bearish sentiment → sell → PnL ≈ 0, position closed."""
    for row in _make_ohlcv_rows(price=50_000.0):
        db_session.add(row)
    await db_session.commit()

    # Cycle 1: buy
    _mock_sentiment(mocker, score=0.9)
    await run_trading_cycle()

    # Cycle 2: sell (sentiment flips bearish)
    _mock_sentiment(mocker, score=-0.9)
    await run_trading_cycle()

    trades = (
        await db_session.execute(
            select(Trade)
            .where(Trade.symbol == SYMBOL, Trade.mode == "paper")
            .order_by(Trade.created_at)
        )
    ).scalars().all()
    assert len(trades) == 2
    assert trades[0].side == "buy"
    assert trades[1].side == "sell"
    assert trades[1].pnl is not None
    # flat price → pnl ≈ 0
    assert trades[1].pnl == pytest.approx(0.0, abs=1e-6)

    positions = (
        await db_session.execute(
            select(Position).where(Position.symbol == SYMBOL)
        )
    ).scalars().all()
    assert len(positions) == 1
    assert positions[0].is_open == False
    assert positions[0].closed_at is not None


async def test_kill_switch_blocks_all_trades(db_session: AsyncSession, mocker):
    """Kill switch ON → cycle exits before rule evaluation → zero trades."""
    for row in _make_ohlcv_rows():
        db_session.add(row)
    await db_session.commit()

    app_state.kill_switch = True
    _mock_sentiment(mocker, score=0.9)

    await run_trading_cycle()

    count = len(
        (await db_session.execute(select(Trade).where(Trade.symbol == SYMBOL))).scalars().all()
    )
    assert count == 0


async def test_daily_loss_guard_blocks_trades(db_session: AsyncSession, mocker):
    """Daily PnL below max_daily_loss_usdt (−200) → rule engine holds → no trade."""
    for row in _make_ohlcv_rows():
        db_session.add(row)
    await db_session.commit()

    app_state.daily_pnl["paper"] = -300.0
    _mock_sentiment(mocker, score=0.9)

    await run_trading_cycle()

    count = len(
        (await db_session.execute(select(Trade).where(Trade.symbol == SYMBOL))).scalars().all()
    )
    assert count == 0


async def test_max_positions_guard_prevents_second_buy(db_session: AsyncSession, mocker):
    """Already have 1 open position (max=1) → second cycle holds even if still bullish."""
    for row in _make_ohlcv_rows():
        db_session.add(row)
    await db_session.commit()

    # Cycle 1: buy (opens position)
    _mock_sentiment(mocker, score=0.9)
    await run_trading_cycle()

    # Cycle 2: still bullish, but max_open_positions already reached
    _mock_sentiment(mocker, score=0.9)
    await run_trading_cycle()

    trades = (
        await db_session.execute(
            select(Trade).where(Trade.symbol == SYMBOL, Trade.mode == "paper")
        )
    ).scalars().all()
    assert len(trades) == 1, "second buy must be blocked by max_open_positions guard"


async def test_insufficient_ohlcv_skips_cycle(db_session: AsyncSession, mocker):
    """< 30 OHLCV bars → cycle returns early without computing anything."""
    for row in _make_ohlcv_rows(n=10):
        db_session.add(row)
    await db_session.commit()

    _mock_sentiment(mocker, score=0.9)

    await run_trading_cycle()

    count = len(
        (await db_session.execute(select(Trade).where(Trade.symbol == SYMBOL))).scalars().all()
    )
    assert count == 0


async def test_no_active_strategy_skips_cycle(db_session: AsyncSession, mocker):
    """No active strategy → cycle returns immediately."""
    app_state.active_strategy = None
    _mock_sentiment(mocker, score=0.9)

    await run_trading_cycle()

    count = len(
        (await db_session.execute(select(Trade).where(Trade.symbol == SYMBOL))).scalars().all()
    )
    assert count == 0
