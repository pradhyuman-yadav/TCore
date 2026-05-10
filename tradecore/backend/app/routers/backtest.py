from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OHLCV
from app.db.session import get_db
from app.services.backtest_runner import run_backtest
from app.state import app_state

router = APIRouter(prefix="/backtest")


class BacktestRequest(BaseModel):
    symbol: str
    exchange: str
    timeframe: str = "1h"
    initial_capital: float = 10_000.0
    strategy_config: dict | None = None  # uses active strategy if None


@router.post("/run")
async def run_backtest_endpoint(
    body: BacktestRequest,
    db: AsyncSession = Depends(get_db),
):
    strategy_config = body.strategy_config
    if strategy_config is None:
        if app_state.active_strategy is None:
            raise HTTPException(status_code=400, detail="No active strategy and no strategy_config provided")
        strategy_config = app_state.active_strategy

    rows = (
        await db.execute(
            select(OHLCV)
            .where(OHLCV.symbol == body.symbol, OHLCV.exchange == body.exchange)
            .order_by(OHLCV.time.asc())
        )
    ).scalars().all()

    if len(rows) < 31:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient OHLCV data: need at least 31 bars, got {len(rows)}",
        )

    df = pd.DataFrame(
        [
            {
                "time": r.time,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ]
    ).set_index("time")

    result = run_backtest(df, strategy_config, initial_capital=body.initial_capital)
    return result.to_dict()
