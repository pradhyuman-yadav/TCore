from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter(prefix="/hawkes")


class PressureResponse(BaseModel):
    symbol:       str
    venue:        str
    pressure:     float   # S_press ∈ [−1, 1]
    lambda_buy:   float
    lambda_sell:  float
    branching:    float
    regime:       str     # 'stable' | 'reflexive'
    params_age_s: float
    tick_count:   int


class ForecastResponse(BaseModel):
    symbol:             str
    venue:              str
    horizon_s:          float
    mean:               float
    p10:                float
    p50:                float
    p90:                float
    prob_buy_pressure:  float


@router.get("/pressure", response_model=PressureResponse)
async def get_pressure(
    symbol: str = Query(..., description="e.g. BTC/USDT"),
    venue:  str = Query(default="binanceus"),
    db: AsyncSession = Depends(get_db),
):
    """
    Cheap live endpoint — reads cached Hawkes params and computes intensity
    from the last 30 s of tick data using O(N) exponential recursion.
    """
    from app.services.hawkes_ofi import (
        compute_pressure, get_recent_events,
        load_cached_params, recursive_intensity,
    )

    params = await load_cached_params(symbol, venue, db)
    if params is None:
        raise HTTPException(
            status_code=404,
            detail="No fitted Hawkes model yet. The refit job runs every 30 min "
                   "once sufficient tick data has accumulated.",
        )

    events      = await get_recent_events(symbol, venue, lookback_s=30.0, db=db)
    lam_b, lam_s = recursive_intensity(params, events)
    pressure     = compute_pressure(lam_b, lam_s)

    return PressureResponse(
        symbol=symbol,
        venue=venue,
        pressure=round(pressure, 6),
        lambda_buy=round(lam_b, 6),
        lambda_sell=round(lam_s, 6),
        branching=round(params.branching, 6),
        regime=params.regime,
        params_age_s=round(params.age_s, 1),
        tick_count=len(events),
    )


@router.get("/forecast", response_model=ForecastResponse)
async def get_forecast(
    symbol:    str   = Query(..., description="e.g. BTC/USDT"),
    venue:     str   = Query(default="binanceus"),
    horizon_s: float = Query(default=5.0, ge=1.0, le=60.0),
    n_sims:    int   = Query(default=200, ge=50, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """
    Heavier endpoint — Ogata-thinning simulation over horizon_s seconds.
    Returns OFI distribution: mean, p10/p50/p90, prob(OFI > 0).
    Runs numpy simulation in a thread pool to avoid blocking the event loop.
    """
    from app.services.hawkes_ofi import (
        get_recent_events, load_cached_params, simulate_forward,
    )

    params = await load_cached_params(symbol, venue, db)
    if params is None:
        raise HTTPException(
            status_code=404,
            detail="No fitted Hawkes model yet.",
        )

    events   = await get_recent_events(symbol, venue, lookback_s=60.0, db=db)
    forecast = await asyncio.to_thread(simulate_forward, params, events, horizon_s, n_sims)

    return ForecastResponse(
        symbol=symbol,
        venue=venue,
        horizon_s=horizon_s,
        **forecast,
    )
