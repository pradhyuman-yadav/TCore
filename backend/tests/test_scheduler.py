from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.scheduler.jobs import run_trading_cycle, setup_scheduler
from app.state import app_state


STRATEGY = {
    "id": str(uuid4()),
    "name": "btc_momentum_v1",
    "symbol": "BTC/USDT",
    "exchange": "binance",
    "timeframe": "1h",
    "refresh_cadence_seconds": 300,
    "indicators": {
        "rsi": {"weight": 0.5},
        "macd_hist": {"weight": 0.5},
    },
    "rules": {"buy_threshold": 0.45, "sell_threshold": -0.35},
    "position_sizing": {"mode": "fixed_usdt", "amount": 100, "max_open_positions": 1},
    "risk": {"max_daily_loss_usdt": 200},
}


def test_setup_scheduler_registers_job():
    scheduler = AsyncIOScheduler()
    app_state.active_strategy = STRATEGY
    setup_scheduler(scheduler)
    jobs = scheduler.get_jobs()
    assert len(jobs) >= 1
    assert any(j.id == "trading_cycle" for j in jobs)


async def test_trading_cycle_skips_when_kill_switch():
    app_state.kill_switch = True
    app_state.active_strategy = STRATEGY
    # Should return immediately without any errors
    await run_trading_cycle()
    app_state.kill_switch = False


async def test_trading_cycle_skips_when_no_strategy():
    app_state.kill_switch = False
    app_state.active_strategy = None
    await run_trading_cycle()
    app_state.active_strategy = STRATEGY


async def test_trading_cycle_skips_insufficient_ohlcv(mocker):
    app_state.kill_switch = False
    app_state.active_strategy = STRATEGY

    mocker.patch(
        "app.scheduler.jobs._load_ohlcv_df",
        new=AsyncMock(return_value=None),
    )
    # Should return without raising
    await run_trading_cycle()


async def test_trading_cycle_runs_full_pipeline(mocker):
    import pandas as pd
    import numpy as np

    app_state.kill_switch = False
    app_state.active_strategy = STRATEGY
    app_state.trading_mode = "paper"

    # Build a realistic OHLCV DataFrame
    rng = np.random.default_rng(1)
    close = 40000.0 + np.cumsum(rng.normal(0, 200, 100))
    df = pd.DataFrame({
        "open": close,
        "high": close * 1.001,
        "low": close * 0.999,
        "close": close,
        "volume": rng.uniform(50, 200, 100),
    })

    mocker.patch("app.scheduler.jobs._load_ohlcv_df", new=AsyncMock(return_value=df))
    mocker.patch("app.scheduler.jobs._count_open_positions", new=AsyncMock(return_value=0))
    mock_snapshot_ind = mocker.patch(
        "app.scheduler.jobs.snapshot_indicators", new=AsyncMock()
    )
    mock_snapshot_comp = mocker.patch(
        "app.scheduler.jobs.snapshot_composite", new=AsyncMock()
    )
    mock_execute = mocker.patch(
        "app.scheduler.jobs.execute_signal", new=AsyncMock(return_value=None)
    )
    mocker.patch(
        "app.scheduler.jobs.fetch_news_headlines", new=AsyncMock(return_value=[])
    )
    mocker.patch(
        "app.scheduler.jobs.score_sentiment", new=AsyncMock(return_value=None)
    )

    await run_trading_cycle()

    # Pipeline ran — snapshot and execute were called
    assert mock_snapshot_ind.called
    assert mock_snapshot_comp.called
    assert mock_execute.called
