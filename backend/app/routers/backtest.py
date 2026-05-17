from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
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
    fee_rate: float = 0.001       # maker/taker fee, e.g. 0.001 = 0.1%
    slippage_bps: float = 0.0    # slippage in basis points
    date_from: str | None = None  # ISO date string, e.g. "2024-01-01"
    date_to:   str | None = None  # ISO date string, e.g. "2024-06-01"
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
            select(func.count()).where(
                OHLCV.symbol == symbol,
                OHLCV.exchange == exchange,
                OHLCV.timeframe == timeframe,
            )
        )
    ).scalar_one()

    if count >= min_bars:
        return count

    log.info("backtest.prefetch_start", symbol=symbol, exchange=exchange, timeframe=timeframe, have=count)

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
            # Map our timeframe to yfinance interval; fall back to "1d" for unsupported
            _tf_map = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "4h": "1h", "1d": "1d"}
            yf_interval = _tf_map.get(timeframe, "1d")
            bars = await fetch_yfinance_history(symbol, asset_type, period="1y", interval=yf_interval)
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

    return count


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

    filters = [
        OHLCV.symbol == body.symbol,
        OHLCV.exchange == body.exchange,
        OHLCV.timeframe == body.timeframe,
    ]
    if body.date_from:
        from datetime import datetime
        filters.append(OHLCV.time >= datetime.fromisoformat(body.date_from).replace(tzinfo=timezone.utc))
    if body.date_to:
        from datetime import datetime
        filters.append(OHLCV.time <= datetime.fromisoformat(body.date_to).replace(tzinfo=timezone.utc))

    rows = (
        await db.execute(
            select(OHLCV).where(*filters).order_by(OHLCV.time.asc())
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

    result = run_backtest(
        df,
        strategy_config,
        initial_capital=body.initial_capital,
        fee_rate=body.fee_rate,
        slippage_bps=body.slippage_bps,
    )
    return result.to_dict()
