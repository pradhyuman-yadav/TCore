from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
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


@router.get("")
async def list_strategies(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Strategy).order_by(Strategy.created_at.desc()))).scalars().all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "is_active": r.is_active,
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
    strategy = Strategy(name=body.name, config=body.config, is_active=False)
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)
    return {"id": str(strategy.id), "name": strategy.name, "is_active": strategy.is_active}


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
