from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OHLCV
from app.services.exchange_client import get_exchange_client


class OHLCVRow(BaseModel):
    time: datetime
    symbol: str
    exchange: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class NewsItem(BaseModel):
    title: str
    source: str
    published_at: datetime
    url: str | None = None


async def fetch_ohlcv(
    symbol: str,
    exchange: str,
    timeframe: str,
    since: datetime,
    until: datetime | None = None,
) -> list[OHLCVRow]:
    client = get_exchange_client()
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    since_ms = int(since.timestamp() * 1000)

    raw = await client.fetch_ohlcv(symbol, timeframe, since=since_ms)

    rows: list[OHLCVRow] = []
    for bar in raw:
        ts, o, h, l, c, v = bar
        bar_time = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        if until and bar_time > until:
            continue
        rows.append(
            OHLCVRow(
                time=bar_time,
                symbol=symbol,
                exchange=exchange,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v,
            )
        )
    return rows


async def fetch_latest_ohlcv(
    symbol: str,
    exchange: str,
    timeframe: str,
    limit: int = 200,
) -> list[OHLCVRow]:
    client = get_exchange_client()
    raw = await client.fetch_ohlcv(symbol, timeframe, limit=limit)
    return [
        OHLCVRow(
            time=datetime.fromtimestamp(bar[0] / 1000, tz=timezone.utc),
            symbol=symbol,
            exchange=exchange,
            open=bar[1],
            high=bar[2],
            low=bar[3],
            close=bar[4],
            volume=bar[5],
        )
        for bar in raw
    ]


async def upsert_ohlcv(rows: list[OHLCVRow], db: AsyncSession) -> int:
    if not rows:
        return 0

    values = [
        {
            "time": row.time,
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

    stmt = pg_insert(OHLCV).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["time", "symbol", "exchange"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
        },
    )
    await db.execute(stmt)
    await db.commit()
    return len(rows)


async def _fetch_openbb_news(symbol: str, limit: int) -> list[dict]:
    try:
        from openbb import obb  # lazy import

        result = obb.news.world(symbols=symbol, limit=limit)
        items = []
        for item in result.results:
            items.append(
                {
                    "title": item.title,
                    "source": item.source or "unknown",
                    "published_at": item.date,
                    "url": getattr(item, "url", None),
                }
            )
        return items
    except Exception:
        return []


async def fetch_news_headlines(symbol: str, limit: int = 20) -> list[NewsItem]:
    raw = await _fetch_openbb_news(symbol, limit)
    return [NewsItem(**item) for item in raw]
