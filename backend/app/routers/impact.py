from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter(prefix="/impact")


@router.get("")
async def get_impact_score(
    text:     str           = Query(..., description="Headline or post title"),
    symbol:   str           = Query(..., description="Asset symbol e.g. BTC/USDT"),
    source:   str           = Query(default="", description="Source name e.g. CoinDesk, r/Bitcoin"),
    platform: str           = Query(default="rss", description="reddit | rss | twitter"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return price-impact probability for a single news/social item.
    Cache-first: cached results return in <5ms; uncached calls Claude (~2s).
    Frontend fires these per-item and fills in scores as each resolves.
    """
    from app.services.sentiment_agent import get_source_reach, _get_symbol_volume, score_price_impact

    reach  = await get_source_reach(source, platform)
    volume = await _get_symbol_volume(symbol, db)
    score  = await score_price_impact(text, symbol, reach, volume, db=db)

    return {"impact_score": score}
