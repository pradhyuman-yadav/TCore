from contextlib import asynccontextmanager

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from sqlalchemy import select, text

from app.config import settings
from app.db.models import Controls, Strategy
from app.db.session import AsyncSessionLocal, engine
from app.routers import backtest, control, health, live, market, paper, strategy, ws
from app.scheduler.jobs import setup_scheduler
from app.state import app_state
from app.ws.manager import ws_manager

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
        log.info("db.connected")

        controls = (await session.execute(select(Controls))).scalar_one()
        app_state.kill_switch = controls.kill_switch or False
        app_state.trading_mode = controls.trading_mode or "paper"

        strategy = (
            await session.execute(select(Strategy).where(Strategy.is_active == True))
        ).scalars().first()
        if strategy:
            app_state.active_strategy = {"id": str(strategy.id), "name": strategy.name, **strategy.config}
            log.info("strategy.loaded", name=strategy.name)

    scheduler = AsyncIOScheduler()
    setup_scheduler(scheduler)
    scheduler.start()
    app.state.scheduler = scheduler
    log.info("scheduler.started")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    await engine.dispose()
    log.info("shutdown.complete")


app = FastAPI(title="TradeCore", version=settings.app_version, lifespan=lifespan)

app.include_router(health.router)
app.include_router(market.router)
app.include_router(strategy.router)
app.include_router(control.router)
app.include_router(paper.router)
app.include_router(live.router)
app.include_router(ws.router)
app.include_router(backtest.router)
