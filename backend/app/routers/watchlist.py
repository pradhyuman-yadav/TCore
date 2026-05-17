from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WatchedSymbol
from app.db.session import get_db
from app.state import app_state

log = structlog.get_logger()
router = APIRouter(prefix="/watchlist")

VALID_ASSET_TYPES = {"crypto", "us_stock", "indian_stock"}
MAX_PER_TYPE = 10


class WatchedSymbolCreate(BaseModel):
    symbol: str
    exchange: str
    asset_type: str  # crypto | us_stock | indian_stock


async def _reload_app_state(db: AsyncSession) -> None:
    """Reload watched_symbols into app_state and update WS subscriptions."""
    rows = (
        await db.execute(
            select(WatchedSymbol).where(WatchedSymbol.is_active == True)
        )
    ).scalars().all()
    app_state.watched_symbols = [
        {
            "id": str(r.id),
            "symbol": r.symbol,
            "exchange": r.exchange,
            "asset_type": r.asset_type,
        }
        for r in rows
    ]
    # Re-subscribe Binance WS client to updated crypto symbol list
    try:
        from app.services.binanceus_ws import binanceus_stream
        crypto_symbols = [
            s["symbol"] for s in app_state.watched_symbols if s["asset_type"] == "crypto"
        ]
        await binanceus_stream.update_subscriptions(crypto_symbols)
    except Exception as exc:
        log.warning("watchlist.ws_update_failed", error=str(exc))


@router.get("")
async def list_watched(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(WatchedSymbol)
            .where(WatchedSymbol.is_active == True)
            .order_by(WatchedSymbol.asset_type, WatchedSymbol.added_at)
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "symbol": r.symbol,
            "exchange": r.exchange,
            "asset_type": r.asset_type,
            "added_at": r.added_at.isoformat() if r.added_at else None,
        }
        for r in rows
    ]


@router.post("", status_code=201)
async def add_watched(body: WatchedSymbolCreate, db: AsyncSession = Depends(get_db)):
    if body.asset_type not in VALID_ASSET_TYPES:
        raise HTTPException(status_code=400, detail=f"asset_type must be one of {VALID_ASSET_TYPES}")

    # Check for existing row FIRST (handles reactivation even when at capacity)
    dup = (
        await db.execute(
            select(WatchedSymbol).where(
                WatchedSymbol.symbol == body.symbol,
                WatchedSymbol.exchange == body.exchange,
            )
        )
    ).scalars().first()
    if dup:
        if dup.is_active:
            raise HTTPException(status_code=409, detail="Symbol already being watched")
        # Reactivate previously soft-deleted entry — skip max-count check
        # (it was already counted before; restoring it doesn't add a new slot)
        dup.is_active = True
        await db.commit()
        await _reload_app_state(db)
        log.info("watchlist.reactivated", symbol=body.symbol)
        return {"id": str(dup.id), "symbol": dup.symbol, "exchange": dup.exchange, "asset_type": dup.asset_type}

    # Enforce max 10 per type only for genuinely new symbols
    count_result = await db.execute(
        select(WatchedSymbol).where(
            WatchedSymbol.asset_type == body.asset_type,
            WatchedSymbol.is_active == True,
        )
    )
    active_count = len(count_result.scalars().all())
    if active_count >= MAX_PER_TYPE:
        raise HTTPException(
            status_code=409,
            detail=f"Maximum {MAX_PER_TYPE} symbols per asset type reached",
        )

    row = WatchedSymbol(
        symbol=body.symbol,
        exchange=body.exchange,
        asset_type=body.asset_type,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await _reload_app_state(db)
    log.info("watchlist.added", symbol=body.symbol, exchange=body.exchange)
    return {"id": str(row.id), "symbol": row.symbol, "exchange": row.exchange, "asset_type": row.asset_type}


@router.delete("/{symbol_id}")
async def remove_watched(symbol_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(select(WatchedSymbol).where(WatchedSymbol.id == symbol_id))
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Watched symbol not found")
    if not row.is_active:
        # Already removed — idempotent, no WS reload needed
        return {"removed": str(symbol_id)}
    row.is_active = False
    await db.commit()
    await _reload_app_state(db)
    log.info("watchlist.removed", symbol=row.symbol)
    return {"removed": str(symbol_id)}
