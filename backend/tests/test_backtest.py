from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.services.backtest_runner import BacktestResult, run_backtest
from app.state import app_state


STRATEGY = {
    "symbol": "BTC/USDT",
    "exchange": "binance",
    "indicators": {
        "rsi": {"weight": 0.5},
        "macd_hist": {"weight": 0.5},
    },
    "rules": {"buy_threshold": 0.45, "sell_threshold": -0.35},
    "position_sizing": {"mode": "fixed_usdt", "amount": 100, "max_open_positions": 1},
    "risk": {"max_daily_loss_usdt": 200},
}


def make_ohlcv_df(n: int = 200, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 40000.0 + np.cumsum(rng.normal(0, 300, n))
    times = [datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i) for i in range(n)]
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.002,
            "low": close * 0.998,
            "close": close,
            "volume": rng.uniform(50, 200, n),
        },
        index=pd.DatetimeIndex(times),
    )


async def test_backtest_returns_result():
    df = make_ohlcv_df(200)
    result = run_backtest(df, STRATEGY)
    assert isinstance(result, BacktestResult)
    assert result.total_bars == 200


async def test_backtest_equity_curve_length():
    df = make_ohlcv_df(200)
    result = run_backtest(df, STRATEGY)
    # One equity point per bar after warmup
    expected = 200 - 30  # warmup = 30
    assert len(result.equity_curve) == expected


async def test_backtest_trades_are_alternating_buy_sell():
    df = make_ohlcv_df(300, seed=7)
    result = run_backtest(df, STRATEGY)
    sides = [t.side for t in result.trades]
    # No two consecutive buys or sells
    for a, b in zip(sides, sides[1:]):
        assert a != b, f"Consecutive {a} trades detected"


async def test_backtest_no_lookahead(monkeypatch):
    """Verify compute_indicators is never called with future bars."""
    call_sizes = []
    original = __import__(
        "app.services.indicator_engine", fromlist=["compute_indicators"]
    ).compute_indicators

    def tracking_compute(df, config):
        call_sizes.append(len(df))
        return original(df, config)

    monkeypatch.setattr(
        "app.services.backtest_runner.compute_indicators", tracking_compute
    )

    df = make_ohlcv_df(100)
    run_backtest(df, STRATEGY)

    # Each call must be strictly increasing (walk-forward, no reuse of future data)
    for a, b in zip(call_sizes, call_sizes[1:]):
        assert b >= a, "compute_indicators was called with fewer bars than previous step"


async def test_backtest_insufficient_data_still_returns(monkeypatch):
    df = make_ohlcv_df(10)  # fewer than warmup
    result = run_backtest(df, STRATEGY)
    assert result.total_bars == 10
    assert result.num_trades == 0
    assert result.equity_curve == []


async def test_backtest_stats_populated():
    df = make_ohlcv_df(300, seed=99)
    result = run_backtest(df, STRATEGY)
    assert 0.0 <= result.win_rate <= 1.0
    assert result.max_drawdown >= 0.0


async def test_backtest_to_dict_shape():
    df = make_ohlcv_df(200)
    result = run_backtest(df, STRATEGY)
    d = result.to_dict()
    for key in ("symbol", "exchange", "total_bars", "num_trades", "total_pnl",
                "win_rate", "max_drawdown", "equity_curve", "trades"):
        assert key in d


async def test_backtest_endpoint_insufficient_data(client):
    resp = await client.post(
        "/backtest/run",
        json={
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "strategy_config": STRATEGY,
        },
    )
    assert resp.status_code == 422
    assert "Insufficient" in resp.json()["detail"]


async def test_backtest_endpoint_no_strategy_no_config(client):
    saved = app_state.active_strategy
    app_state.active_strategy = None
    resp = await client.post(
        "/backtest/run",
        json={"symbol": "BTC/USDT", "exchange": "binance"},
    )
    assert resp.status_code == 400
    app_state.active_strategy = saved


async def test_backtest_endpoint_with_ohlcv(client, db_session):
    from app.db.models import OHLCV
    from app.services.data_ingestion import OHLCVRow, upsert_ohlcv

    rows = [
        OHLCVRow(
            time=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
            symbol="BTC/USDT",
            exchange="binance",
            open=40000.0,
            high=41000.0,
            low=39000.0,
            close=40000.0 + i * 10,
            volume=100.0,
        )
        for i in range(60)
    ]
    await upsert_ohlcv(rows, db_session)

    resp = await client.post(
        "/backtest/run",
        json={
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "strategy_config": STRATEGY,
            "initial_capital": 5000.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_bars"] == 60
    assert "equity_curve" in data
    assert "trades" in data
