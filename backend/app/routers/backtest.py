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


async def _prefetch_if_needed(
    symbol: str,
    exchange: str,
    timeframe: str,
    db: AsyncSession,
    min_bars: int = 31,
) -> int:
    """
    Check if we have enough data. If not, fetch from exchange/yfinance and store.
    Returns the count of available rows after potential prefetch.
    """
    import structlog
    log = structlog.get_logger()

    count = (
        await db.execute(
            select(OHLCV).where(OHLCV.symbol == symbol, OHLCV.exchange == exchange)
        )
    ).scalars().all()

    if len(count) >= min_bars:
        return len(count)

    log.info("backtest.prefetch_start", symbol=symbol, exchange=exchange, have=len(count))

    # Determine asset type from watched symbols
    watched = {s["symbol"]: s for s in app_state.watched_symbols}
    sym_info = watched.get(symbol, {})
    asset_type = sym_info.get("asset_type", "crypto")

    if asset_type == "crypto":
        # Use CCXT / Binance history
        try:
            from datetime import timedelta
            from app.services.data_ingestion import fetch_ohlcv, upsert_ohlcv
            since = datetime.now(timezone.utc) - timedelta(days=365)
            rows = await fetch_ohlcv(symbol, exchange, timeframe, since=since)
            if rows:
                await upsert_ohlcv(rows, db)
                log.info("backtest.prefetch_done", symbol=symbol, upserted=len(rows))
                return len(rows)
        except Exception as exc:
            log.warning("backtest.prefetch_crypto_error", error=str(exc))
    else:
        # Use yfinance
        try:
            from app.services.stock_feed import fetch_yfinance_history
            from app.services.data_ingestion import OHLCVRow, upsert_ohlcv
            bars = await fetch_yfinance_history(symbol, asset_type, period="1y", interval="1d")
            if bars:
                ohlcv_rows = [
                    OHLCVRow(
                        time=b["time"], symbol=symbol, exchange=exchange,
                        open=b["open"], high=b["high"], low=b["low"],
                        close=b["close"], volume=b["volume"],
                    )
                    for b in bars
                ]
                await upsert_ohlcv(ohlcv_rows, db)
                log.info("backtest.prefetch_done", symbol=symbol, upserted=len(ohlcv_rows))
                return len(ohlcv_rows)
        except Exception as exc:
            log.warning("backtest.prefetch_stock_error", error=str(exc))

    return len(count)


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

    # Auto-fetch historical data if insufficient
    await _prefetch_if_needed(body.symbol, body.exchange, body.timeframe, db)

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
            detail=f"Insufficient OHLCV data: need at least 31 bars, got {len(rows)}. "
                   f"Try syncing data first via /market/sync.",
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
