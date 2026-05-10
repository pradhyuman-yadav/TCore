import random
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from app.db.models import IndicatorSnapshot
from app.services.indicator_engine import (
    IndicatorConfig,
    IndicatorDef,
    compute_indicators,
    snapshot_indicators,
)


def make_ohlcv_df(n: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 40000.0 + np.cumsum(rng.normal(0, 200, n))
    return pd.DataFrame(
        {
            "open": close * (1 + rng.uniform(-0.002, 0.002, n)),
            "high": close * (1 + rng.uniform(0, 0.005, n)),
            "low": close * (1 - rng.uniform(0, 0.005, n)),
            "close": close,
            "volume": rng.uniform(50, 200, n),
        }
    )


def config_with(*names: str) -> IndicatorConfig:
    return IndicatorConfig(
        indicators=[IndicatorDef(name=n, weight=1.0 / len(names)) for n in names]
    )


ALL_INDICATORS = ["rsi", "macd_hist", "bb_position", "volume_surge", "ema_cross"]


async def test_rsi_normalized_range():
    df = make_ohlcv_df(200)
    cfg = config_with("rsi")
    result = compute_indicators(df, cfg)
    val = result["rsi"]
    assert val is not None
    assert -1.0 <= val <= 1.0


async def test_all_indicators_return_float_or_none():
    df = make_ohlcv_df(200)
    cfg = config_with(*ALL_INDICATORS)
    result = compute_indicators(df, cfg)
    for name in ALL_INDICATORS:
        assert name in result
        v = result[name]
        assert v is None or isinstance(v, float)
        if v is not None:
            assert -1.0 <= v <= 1.0


async def test_all_non_none_values_in_range():
    rng = np.random.default_rng(0)
    cfg = config_with(*ALL_INDICATORS)
    for i in range(500):
        n = rng.integers(30, 300)
        seed = int(rng.integers(0, 10_000))
        df = make_ohlcv_df(int(n), seed=seed)
        result = compute_indicators(df, cfg)
        for name, val in result.items():
            if val is not None:
                assert -1.0 <= val <= 1.0, f"{name}={val} out of range (iteration {i})"


async def test_insufficient_data_returns_none_not_exception():
    df = make_ohlcv_df(5)
    cfg = config_with(*ALL_INDICATORS)
    result = compute_indicators(df, cfg)
    # Should not raise; some or all may be None with only 5 bars
    for val in result.values():
        assert val is None or isinstance(val, float)


async def test_snapshot_writes_to_db_and_updates_state(db_session):
    from app.state import app_state

    symbol = "BTC/USDT"
    strategy_id = uuid4()
    values = {"rsi": 0.5, "macd_hist": -0.3}
    weights = {"rsi": 0.6, "macd_hist": 0.4}

    await snapshot_indicators(symbol, strategy_id, values, weights, db_session)

    rows = (
        await db_session.execute(
            select(IndicatorSnapshot).where(IndicatorSnapshot.symbol == symbol)
        )
    ).scalars().all()

    assert len(rows) == 2
    names = {r.indicator_name for r in rows}
    assert names == {"rsi", "macd_hist"}

    assert app_state.indicator_values[symbol]["rsi"] == 0.5
    assert app_state.indicator_values[symbol]["macd_hist"] == -0.3


async def test_snapshot_skips_none_values(db_session):
    symbol = "ETH/USDT"
    strategy_id = uuid4()
    values = {"rsi": 0.2, "volume_surge": None}
    weights = {"rsi": 1.0, "volume_surge": 0.5}

    await snapshot_indicators(symbol, strategy_id, values, weights, db_session)

    rows = (
        await db_session.execute(
            select(IndicatorSnapshot).where(IndicatorSnapshot.symbol == symbol)
        )
    ).scalars().all()

    assert len(rows) == 1
    assert rows[0].indicator_name == "rsi"
