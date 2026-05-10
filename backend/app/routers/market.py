from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
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
    result = await db.execute(
        select(OHLCV)
        .where(OHLCV.symbol == symbol, OHLCV.exchange == exchange)
        .order_by(OHLCV.time.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "time": row.time.isoformat(),
            "symbol": row.symbol,
            "exchange": row.exchange,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
        }
        for row in rows
    ]


@router.get("/news")
async def get_news(symbol: str, limit: int = 20):
    items = await fetch_news_headlines(symbol, limit=limit)
    return [item.model_dump() for item in items]


@router.post("/sync")
async def sync_market_data(
    symbol: str,
    exchange: str,
    timeframe: str = "1h",
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=30)
    rows = await fetch_ohlcv(symbol, exchange, timeframe, since=since)
    count = await upsert_ohlcv(rows, db)
    return {"symbol": symbol, "exchange": exchange, "timeframe": timeframe, "upserted": count}
