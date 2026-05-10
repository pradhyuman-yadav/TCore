import pytest


async def test_health_returns_200(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


async def test_health_schema(client):
    resp = await client.get("/health")
    data = resp.json()
    assert data["status"] == "ok"
    assert data["db"] == "connected"
    assert data["scheduler"] == "running"
    assert "kill_switch" in data
    assert "ws_connections" in data


async def test_health_no_redis_field(client):
    resp = await client.get("/health")
    assert "redis" not in resp.json()


async def test_kill_switch_default_false(client):
    resp = await client.get("/health")
    assert resp.json()["kill_switch"] == False


async def test_missing_db_env_var_raises_on_startup(monkeypatch):
    monkeypatch.delenv("DB_HOST", raising=False)
    with pytest.raises(Exception):
        from app.config import Settings
        Settings()
