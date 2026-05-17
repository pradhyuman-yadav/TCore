import asyncio
import os
import sys
import subprocess

# Load .env BEFORE any app module import so Settings() finds required env vars
from dotenv import load_dotenv

_env_file = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
load_dotenv(_env_file)

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text


@pytest.fixture(autouse=True)
def _zero_paper_fees():
    """
    Reset paper_account fees to zero for every test.
    Real defaults (0.1% fee, 5 bps slip) are correct for production but break
    assertions that expect exact prices / zero-fee PnL.  Individual tests that
    want to verify fee behaviour should override app_state.paper_account directly.
    """
    from app.state import app_state
    saved = dict(app_state.paper_account)
    app_state.paper_account = {
        "initial_capital": 10_000.0,
        "fee_rate": 0.0,
        "slippage_bps": 0.0,
    }
    yield
    app_state.paper_account = saved


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop shared across all tests — prevents asyncpg cross-loop errors."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def run_migrations():
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade head failed:\n{result.stderr}")


@pytest.fixture
async def db_session(run_migrations):
    from app.config import settings

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(
            "TRUNCATE ohlcv, indicator_snapshots, composite_scores, "
            "trades, positions, strategies, sentiment_cache"
        ))
        await session.commit()
        yield session
    await engine.dispose()


@pytest.fixture
async def client(run_migrations):
    from httpx import AsyncClient, ASGITransport
    from asgi_lifespan import LifespanManager
    from app.main import app

    async with LifespanManager(app) as manager:
        async with AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as c:
            yield c
