import asyncio
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OHLCV
from app.db.session import get_db
from app.services.backtest_runner import run_backtest
from app.state import app_state

router = APIRouter(prefix="/backtest")

MAX_BARS = 2_000          # hard cap — prevents O(n²) timeout
_PREFETCH_DAYS = 90       # how far back to auto-fetch (enough for any meaningful test)
_PREFETCH_TIMEOUT = 20.0  # seconds before we give up and return a clear error


class BacktestRequest(BaseModel):
    symbol: str
    exchange: str
    timeframe: str = "1h"
    initial_capital: float = Field(10_000.0, gt=0)
    fee_rate: float = Field(0.001, ge=0, le=0.05)
    slippage_bps: float = Field(0.0, ge=0, le=500)
    date_from: str | None = None  # ISO date string, e.g. "2024-01-01"
    date_to:   str | None = None  # ISO date string, e.g. "2024-06-01"
    strategy_config: dict | None = None  # uses active strategy if None


async def _do_prefetch(
    symbol: str,
    exchange: str,
    timeframe: str,
    asset_type: str,
    db: AsyncSession,
) -> int:
    """Inner prefetch — called with a timeout wrapper. Returns rows upserted."""
    import structlog
    log = structlog.get_logger()
    since = datetime.now(timezone.utc) - timedelta(days=_PREFETCH_DAYS)

    if asset_type == "crypto":
        from app.services.data_ingestion import fetch_ohlcv, upsert_ohlcv
        rows = await fetch_ohlcv(symbol, exchange, timeframe, since=since)
        if rows:
            await upsert_ohlcv(rows, db)
            log.info("backtest.prefetch_done", symbol=symbol, upserted=len(rows))
            return len(rows)
    else:
        from app.services.stock_feed import fetch_yfinance_history
        from app.services.data_ingestion import OHLCVRow, upsert_ohlcv
        _tf_map = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                   "1h": "1h", "4h": "1h", "1d": "1d"}
        yf_interval = _tf_map.get(timeframe, "1d")
        bars = await fetch_yfinance_history(symbol, asset_type, period="3mo", interval=yf_interval)
        if bars:
            ohlcv_rows = [
                OHLCVRow(
                    time=b["time"], symbol=symbol, exchange=exchange, timeframe=timeframe,
                    open=b["open"], high=b["high"], low=b["low"],
                    close=b["close"], volume=b["volume"],
                )
                for b in bars
            ]
            await upsert_ohlcv(ohlcv_rows, db)
            log.info("backtest.prefetch_done", symbol=symbol, upserted=len(ohlcv_rows))
            return len(ohlcv_rows)
    return 0


async def _prefetch_if_needed(
    symbol: str,
    exchange: str,
    timeframe: str,
    db: AsyncSession,
    min_bars: int = 31,
) -> int:
    """
    If DB has fewer than min_bars, attempt a quick prefetch (capped at
    _PREFETCH_DAYS days, _PREFETCH_TIMEOUT seconds). Returns updated count.
    On timeout or error, logs a warning and returns the original count —
    the caller will raise a friendly 422.
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

    log.info("backtest.prefetch_start", symbol=symbol, exchange=exchange,
             timeframe=timeframe, have=count, fetching_days=_PREFETCH_DAYS)

    watched   = {s["symbol"]: s for s in app_state.watched_symbols}
    sym_info  = watched.get(symbol, {})
    asset_type = sym_info.get("asset_type", "crypto")

    try:
        upserted = await asyncio.wait_for(
            _do_prefetch(symbol, exchange, timeframe, asset_type, db),
            timeout=_PREFETCH_TIMEOUT,
        )
        return count + upserted
    except asyncio.TimeoutError:
        log.warning("backtest.prefetch_timeout", symbol=symbol,
                    timeout=_PREFETCH_TIMEOUT)
    except Exception as exc:
        log.warning("backtest.prefetch_error", symbol=symbol, error=str(exc))

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
        date_hint = ""
        if body.date_from or body.date_to:
            date_hint = f" in range {body.date_from or '…'} – {body.date_to or '…'}"
        raise HTTPException(
            status_code=422,
            detail=(
                f"No data for {body.symbol} / {body.timeframe}{date_hint}. "
                f"Go to ChartView → select {body.symbol} → click ⟳ DB Sync to load historical bars first."
            ),
        )

    # Cap to most recent MAX_BARS to prevent O(n²) timeout
    if len(rows) > MAX_BARS:
        rows = rows[-MAX_BARS:]

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
    out = result.to_dict()
    out["bars_used"] = len(df)
    out["bars_capped"] = len(rows) >= MAX_BARS  # true if we truncated
    return out
