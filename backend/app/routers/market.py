import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OHLCV
from app.db.session import get_db
from app.services.data_ingestion import (
    OHLCVRow,
    fetch_news_headlines,
    fetch_ohlcv,
    upsert_ohlcv,
)

router = APIRouter(prefix="/market")

# yfinance interval limits (max days of history available)
_YF_INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "1h", "1d": "1d",
}
_YF_MAX_DAYS = {"1m": 7, "5m": 59, "15m": 59, "30m": 59, "1h": 729, "1d": 3649}


async def _sync_yfinance(
    symbol: str, exchange: str, timeframe: str, days: int
) -> list[OHLCVRow]:
    """Fetch history from yfinance for US/Indian stock symbols."""
    from app.services.stock_feed import _to_yfinance_symbol

    asset_type = "indian_stock" if exchange == "yfinance_in" else "us_stock"
    yf_sym  = _to_yfinance_symbol(symbol, asset_type)
    interval = _YF_INTERVAL_MAP.get(timeframe, "1d")
    max_days = _YF_MAX_DAYS.get(interval, 365)
    actual_days = min(days, max_days)
    since = datetime.now(timezone.utc) - timedelta(days=actual_days)

    def _fetch() -> list[OHLCVRow]:
        import yfinance as yf  # sync — runs in thread pool

        hist = yf.Ticker(yf_sym).history(
            start=since.strftime("%Y-%m-%d"), interval=interval
        )
        if hist.empty:
            return []
        rows: list[OHLCVRow] = []
        for ts, row in hist.iterrows():
            dt = ts.to_pydatetime()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            rows.append(OHLCVRow(
                time=dt,
                symbol=symbol,
                exchange=exchange,
                timeframe=interval,   # use actual yfinance interval fetched
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
            ))
        return rows

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch)


@router.get("/ohlcv")
async def get_ohlcv(
    symbol: str,
    exchange: str,
    timeframe: str = "1h",
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    # Fetch latest N rows (desc) for the requested timeframe, then reverse for chart
    sub = (
        select(OHLCV)
        .where(OHLCV.symbol == symbol, OHLCV.exchange == exchange, OHLCV.timeframe == timeframe)
        .order_by(OHLCV.time.desc())
        .limit(limit)
        .subquery()
    )
    result = await db.execute(
        select(sub).order_by(sub.c.time.asc())
    )
    rows = result.mappings().all()
    return [
        {
            "time": row["time"].isoformat(),
            "symbol": row["symbol"],
            "exchange": row["exchange"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        }
        for row in rows
    ]


@router.get("/ohlcv/count")
async def get_ohlcv_count(
    symbol: str,
    exchange: str,
    db: AsyncSession = Depends(get_db),
):
    """Return row count so UI knows whether to prompt a sync."""
    result = await db.execute(
        select(func.count()).where(OHLCV.symbol == symbol, OHLCV.exchange == exchange)
    )
    count = result.scalar_one()
    return {"symbol": symbol, "exchange": exchange, "count": count}


@router.get("/news")
async def get_news(symbol: str, limit: int = 20):
    items = await fetch_news_headlines(symbol, limit=limit)
    return [item.model_dump() for item in items]


@router.post("/sync")
async def sync_market_data(
    symbol: str,
    exchange: str,
    timeframe: str = "1h",
    days: int = Query(default=90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Fetch historical OHLCV from exchange and store in DB.

    days: how many days of history to pull (default 90, max 365)
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    if exchange in ("yfinance_us", "yfinance_in"):
        rows = await _sync_yfinance(symbol, exchange, timeframe, days)
        # Compute actual days fetched (may be capped by yfinance interval limits)
        interval = _YF_INTERVAL_MAP.get(timeframe, "1d")
        actual_days = min(days, _YF_MAX_DAYS.get(interval, days))
    else:
        rows = await fetch_ohlcv(symbol, exchange, timeframe, since=since)
        actual_days = days
    count = await upsert_ohlcv(rows, db)
    return {
        "symbol": symbol,
        "exchange": exchange,
        "timeframe": timeframe,
        "days_requested": days,
        "days_fetched": actual_days,
        "upserted": count,
    }
