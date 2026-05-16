from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter(prefix="/news")


@router.get("")
async def get_news(
    symbols: str | None = Query(default=None, description="Comma-separated symbols e.g. BTC/USDT,ETH/USDT"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Fetch aggregated news from OpenBB + RSS feeds."""
    from app.services.news_aggregator import fetch_combined_news

    sym_list = [s.strip() for s in symbols.split(",")] if symbols else []
    items = await fetch_combined_news(symbols=sym_list or None, limit=limit)

    return [
        {
            "title": item["title"],
            "source": item["source"],
            "published_at": item["published_at"].isoformat() if item.get("published_at") else None,
            "url": item.get("url"),
            "summary": item.get("summary", ""),
        }
        for item in items
    ]
