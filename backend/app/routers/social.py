from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter(prefix="/social")


@router.get("")
async def get_social(
    source: str = Query(default="reddit", description="reddit | twitter | rss"),
    category: str = Query(default="crypto", description="crypto | us_stock | indian_stock"),
    query: str = Query(default="bitcoin OR crypto", description="Search query for twitter"),
    limit: int = Query(default=30, ge=1, le=100),
):
    """Fetch social media posts from Reddit, Twitter (via Nitter), or RSS feeds."""
    from app.services.social_aggregator import fetch_social
    return await fetch_social(source=source, category=category, query=query, limit=limit)
