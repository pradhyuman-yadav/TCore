from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models import CompositeScore
from app.services.aggregator import (
    classify_zone,
    compute_composite_score,
    snapshot_composite,
)


async def test_compute_composite_weighted_average():
    values = {"rsi": 0.4, "macd_hist": 0.8}
    weights = {"rsi": 0.5, "macd_hist": 0.5}
    score = compute_composite_score(values, weights)
    assert score is not None
    assert abs(score - 0.6) < 1e-9


async def test_compute_composite_skips_none_and_renormalizes():
    # rsi=None excluded; macd weight renormalized to 1.0
    values = {"rsi": None, "macd_hist": 0.6}
    weights = {"rsi": 0.5, "macd_hist": 0.5}
    score = compute_composite_score(values, weights)
    assert score is not None
    assert abs(score - 0.6) < 1e-9


async def test_compute_composite_all_none_returns_none():
    values = {"rsi": None, "macd_hist": None}
    weights = {"rsi": 0.5, "macd_hist": 0.5}
    score = compute_composite_score(values, weights)
    assert score is None


async def test_compute_composite_unequal_weights():
    values = {"a": 1.0, "b": 0.0}
    weights = {"a": 0.8, "b": 0.2}
    score = compute_composite_score(values, weights)
    assert score is not None
    # (1.0 * 0.8 + 0.0 * 0.2) / (0.8 + 0.2) = 0.8
    assert abs(score - 0.8) < 1e-9


async def test_classify_zone_buy():
    assert classify_zone(0.5, buy_threshold=0.45, sell_threshold=-0.35) == "buy"


async def test_classify_zone_sell():
    assert classify_zone(-0.5, buy_threshold=0.45, sell_threshold=-0.35) == "sell"


async def test_classify_zone_neutral():
    assert classify_zone(0.1, buy_threshold=0.45, sell_threshold=-0.35) == "neutral"


async def test_classify_zone_boundary_buy():
    assert classify_zone(0.45, buy_threshold=0.45, sell_threshold=-0.35) == "buy"


async def test_classify_zone_boundary_sell():
    assert classify_zone(-0.35, buy_threshold=0.45, sell_threshold=-0.35) == "sell"


async def test_snapshot_composite_writes_to_db(db_session):
    from app.state import app_state

    symbol = "BTC/USDT"
    strategy_id = uuid4()

    await snapshot_composite(symbol, strategy_id, score=0.6, zone="buy", db=db_session)

    rows = (
        await db_session.execute(
            select(CompositeScore).where(CompositeScore.symbol == symbol)
        )
    ).scalars().all()

    assert len(rows) == 1
    assert rows[0].score == 0.6
    assert rows[0].zone == "buy"

    assert app_state.composite_scores[symbol]["score"] == 0.6
    assert app_state.composite_scores[symbol]["zone"] == "buy"
