from fastapi import APIRouter, Request
from sqlalchemy import text

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.state import app_state
from app.ws.manager import ws_manager

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    db_status = "disconnected"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        pass

    scheduler = getattr(request.app.state, "scheduler", None)
    scheduler_status = "running" if scheduler and scheduler.running else "stopped"

    active_name: str | None = None
    if app_state.active_strategy:
        active_name = app_state.active_strategy.get("name")

    return {
        "status": "ok",
        "version": settings.app_version,
        "db": db_status,
        "scheduler": scheduler_status,
        "trading_mode": app_state.trading_mode,
        "kill_switch": app_state.kill_switch,
        "active_strategy": active_name,
        "ws_connections": {
            "signals": ws_manager.connection_count("signals"),
            "trades": ws_manager.connection_count("trades"),
            "portfolio": ws_manager.connection_count("portfolio"),
        },
    }
