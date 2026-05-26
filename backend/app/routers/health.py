import time

import httpx
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
    Checks proxy health first, then makes a real sentiment call.
    """
    from app.services.sentiment_agent import _call_claude, _PROXY_URL, _MODEL, _MODEL_DIRECT, claude_mode

    mode = claude_mode()
    model = _MODEL if _PROXY_URL else _MODEL_DIRECT

    # If neither proxy nor direct credentials are configured, return clear error immediately
    if not _PROXY_URL:
        import os
        if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("CLAUDE_ACCESS_TOKEN"):
            return {
                "status": "error", "mode": mode, "model": model,
                "detail": "No Claude config found. Set CLAUDE_CODE_OAUTH_TOKEN (proxy) or ANTHROPIC_API_KEY (direct).",
                "test_score": None, "latency_ms": None,
            }

    # Fast path: verify proxy is reachable before an inference call
    proxy_health: dict | None = None
    if _PROXY_URL:
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                r = await client.get(f"{_PROXY_URL}/health")
                r.raise_for_status()
                proxy_health = r.json()
        except Exception as exc:
            return {
                "status": "error", "mode": mode, "model": model,
                "detail": f"Proxy unreachable: {exc}",
                "test_score": None, "latency_ms": None,
                "proxy": None,
            }

    try:
        t0 = time.monotonic()
        score, reasoning = await _call_claude(
            ["Bitcoin reaches new all-time high amid institutional buying"],
            "BTC/USDT",
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {
            "status": "ok",
            "mode": mode,
            "model": model,
            "test_score": round(score, 4),
            "reasoning": reasoning,
            "latency_ms": latency_ms,
            "proxy": proxy_health,
        }
    except Exception as exc:
        return {
            "status": "error", "mode": mode, "model": model,
            "detail": str(exc),
            "test_score": None, "latency_ms": None,
            "proxy": proxy_health,
        }


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
