from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Strategy
from app.db.session import get_db
from app.state import app_state

router = APIRouter(prefix="/strategy")


class StrategyCreate(BaseModel):
    name: str
    config: dict
    asset_type: str | None = None


@router.get("")
async def list_strategies(
    asset_type: str | None = Query(default=None, description="crypto | stock"),
    db: AsyncSession = Depends(get_db),
):
    q = select(Strategy).order_by(Strategy.created_at.desc())
    if asset_type:
        q = q.where(Strategy.asset_type == asset_type)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "is_active": r.is_active,
            "asset_type": r.asset_type,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/active")
async def get_active_strategy():
    if app_state.active_strategy is None:
        raise HTTPException(status_code=404, detail="No active strategy")
    return app_state.active_strategy


@router.post("", status_code=201)
async def create_strategy(body: StrategyCreate, db: AsyncSession = Depends(get_db)):
    existing = (
        await db.execute(select(Strategy).where(Strategy.name == body.name))
    ).scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail="Strategy name already exists")

    # Infer asset_type from exchange in config if not provided
    asset_type = body.asset_type
    if not asset_type:
        exchange = str(body.config.get("exchange", "")).lower()
        asset_type = "crypto" if "binance" in exchange else "stock"

    strategy = Strategy(name=body.name, config=body.config, is_active=False, asset_type=asset_type)
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)
    return {
        "id": str(strategy.id),
        "name": strategy.name,
        "is_active": strategy.is_active,
        "asset_type": strategy.asset_type,
    }


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: UUID, db: AsyncSession = Depends(get_db)):
    target = (
        await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    ).scalars().first()
    if target is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {
        "id": str(target.id),
        "name": target.name,
        "is_active": target.is_active,
        "asset_type": target.asset_type,
        "config": target.config,
        "created_at": target.created_at.isoformat() if target.created_at else None,
    }


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(strategy_id: UUID, db: AsyncSession = Depends(get_db)):
    target = (
        await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    ).scalars().first()
    if target is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if target.is_active:
        raise HTTPException(status_code=409, detail="Cannot delete the active strategy — deactivate it first")
    await db.delete(target)
    await db.commit()


@router.post("/{strategy_id}/activate")
async def activate_strategy(strategy_id: UUID, request: Request, db: AsyncSession = Depends(get_db)):
    # Deactivate all
    rows = (await db.execute(select(Strategy))).scalars().all()
    for row in rows:
        row.is_active = False

    # Activate target
    target = (
        await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    ).scalars().first()
    if target is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    target.is_active = True
    await db.commit()

    app_state.active_strategy = {"id": str(target.id), "name": target.name, **target.config}

    # Reschedule trading cycle with the new strategy's cadence
    try:
        cadence = int(target.config.get("refresh_cadence_seconds", 300))
        scheduler = request.app.state.scheduler
        scheduler.reschedule_job(
            "trading_cycle", trigger="interval", seconds=cadence
        )
    except Exception:
        pass  # scheduler not available in tests / before startup

    return {"activated": str(target.id), "name": target.name}
