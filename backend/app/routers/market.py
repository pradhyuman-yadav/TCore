from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OHLCV
from app.db.session import get_db
from app.services.data_ingestion import (
    fetch_news_headlines,
    fetch_ohlcv,
    upsert_ohlcv,
)

router = APIRouter(prefix="/market")


@router.get("/ohlcv")
async def get_ohlcv(
    symbol: str,
    exchange: str,
    timeframe: str = "1h",
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    # Fetch latest N rows (desc), then reverse to ascending for charts
    sub = (
        select(OHLCV)
        .where(OHLCV.symbol == symbol, OHLCV.exchange == exchange)
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
    rows = await fetch_ohlcv(symbol, exchange, timeframe, since=since)
    count = await upsert_ohlcv(rows, db)
    return {
        "symbol": symbol,
        "exchange": exchange,
        "timeframe": timeframe,
        "days": days,
        "upserted": count,
    }
