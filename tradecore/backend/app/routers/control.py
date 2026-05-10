from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Controls
from app.db.session import get_db
from app.state import app_state

router = APIRouter(prefix="/control")


@router.get("")
async def get_control():
    return {
        "kill_switch": app_state.kill_switch,
        "trading_mode": app_state.trading_mode,
    }


class KillSwitchBody(BaseModel):
    enabled: bool


@router.post("/kill-switch")
async def set_kill_switch(body: KillSwitchBody, db: AsyncSession = Depends(get_db)):
    app_state.kill_switch = body.enabled
    controls = (await db.execute(select(Controls))).scalar_one()
    controls.kill_switch = body.enabled
    await db.commit()
    return {"kill_switch": app_state.kill_switch}


class TradingModeBody(BaseModel):
    mode: str


@router.post("/trading-mode")
async def set_trading_mode(body: TradingModeBody, db: AsyncSession = Depends(get_db)):
    if body.mode not in ("paper", "live"):
        raise HTTPException(status_code=422, detail="mode must be 'paper' or 'live'")
    app_state.trading_mode = body.mode
    controls = (await db.execute(select(Controls))).scalar_one()
    controls.trading_mode = body.mode
    await db.commit()
    return {"trading_mode": app_state.trading_mode}
