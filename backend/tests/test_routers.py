from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.state import app_state


# ── Control ──────────────────────────────────────────────────────────────────

async def test_get_control_returns_state(client):
    app_state.kill_switch = False
    app_state.trading_mode = "paper"
    resp = await client.get("/control")
    assert resp.status_code == 200
    data = resp.json()
    assert data["kill_switch"] == False
    assert data["trading_mode"] == "paper"


async def test_set_kill_switch(client):
    resp = await client.post("/control/kill-switch", json={"enabled": True})
    assert resp.status_code == 200
    assert resp.json()["kill_switch"] == True
    assert app_state.kill_switch == True

    # Reset
    await client.post("/control/kill-switch", json={"enabled": False})


async def test_set_trading_mode_paper(client):
    resp = await client.post("/control/trading-mode", json={"mode": "paper"})
    assert resp.status_code == 200
    assert resp.json()["trading_mode"] == "paper"


async def test_set_trading_mode_invalid(client):
    resp = await client.post("/control/trading-mode", json={"mode": "invalid"})
    assert resp.status_code == 422


# ── Strategy ─────────────────────────────────────────────────────────────────

async def test_list_strategies_empty(client):
    resp = await client.get("/strategy")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_create_strategy(client):
    payload = {
        "name": "test_strategy",
        "config": {
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "indicators": {"rsi": {"weight": 1.0}},
            "rules": {"buy_threshold": 0.4, "sell_threshold": -0.4},
            "position_sizing": {"mode": "fixed_usdt", "amount": 100, "max_open_positions": 1},
            "risk": {"max_daily_loss_usdt": 200},
        },
    }
    resp = await client.post("/strategy", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test_strategy"
    assert "id" in data


async def test_create_strategy_duplicate_returns_409(client):
    payload = {"name": "dup_strategy", "config": {"symbol": "ETH/USDT"}}
    await client.post("/strategy", json=payload)
    resp = await client.post("/strategy", json=payload)
    assert resp.status_code == 409


async def test_activate_strategy(client):
    # Create and then activate
    create = await client.post(
        "/strategy",
        json={"name": "activatable", "config": {"symbol": "BTC/USDT", "exchange": "binance"}},
    )
    assert create.status_code == 201
    strategy_id = create.json()["id"]

    resp = await client.post(f"/strategy/{strategy_id}/activate")
    assert resp.status_code == 200
    assert resp.json()["activated"] == strategy_id

    # Active strategy in state should be updated
    assert app_state.active_strategy is not None
    assert app_state.active_strategy["name"] == "activatable"


async def test_activate_nonexistent_strategy_returns_404(client):
    resp = await client.post(f"/strategy/{uuid4()}/activate")
    assert resp.status_code == 404


async def test_get_active_strategy_when_none(client):
    saved = app_state.active_strategy
    app_state.active_strategy = None
    resp = await client.get("/strategy/active")
    assert resp.status_code == 404
    app_state.active_strategy = saved


# ── Paper positions / trades ──────────────────────────────────────────────────

async def test_get_paper_positions_empty(client):
    resp = await client.get("/paper/positions")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_paper_trades_empty(client):
    resp = await client.get("/paper/trades")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Live positions / trades ───────────────────────────────────────────────────

async def test_get_live_positions_empty(client):
    resp = await client.get("/live/positions")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_live_trades_empty(client):
    resp = await client.get("/live/trades")
    assert resp.status_code == 200
    assert resp.json() == []
