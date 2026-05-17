import time

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.state import app_state
from app.ws.manager import ws_manager

router = APIRouter()


@router.get("/health/claude")
async def claude_health():
    """
    Live smoke-test of the Claude integration.
    Calls Claude Haiku with a short BTC sentiment prompt and returns the result.
    """
    from app.services.claude_auth import get_auth_headers
    from app.services.sentiment_agent import _call_claude

    try:
        await get_auth_headers()  # verify credentials accessible (fast path)
    except Exception as exc:
        return {"status": "error", "detail": str(exc), "model": None, "test_score": None, "latency_ms": None}

    try:
        t0 = time.monotonic()
        score, reasoning = await _call_claude(
            ["Bitcoin reaches new all-time high amid institutional buying"],
            "BTC/USDT",
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {
            "status": "ok",
            "model": "claude-haiku-4-5-20251001",
            "test_score": round(score, 4),
            "reasoning": reasoning,
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc), "model": None, "test_score": None, "latency_ms": None}


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
