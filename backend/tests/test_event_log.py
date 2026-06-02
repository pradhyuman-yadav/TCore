"""
Tests for the system event log (app.services.event_log).

build_event is pure and tested directly. log_event's DB + broadcast are mocked.
"""
from __future__ import annotations

import pytest

from app.services.event_log import (
    EVENTS_CHANNEL,
    VALID_CATEGORIES,
    VALID_LEVELS,
    build_event,
    log_event,
)


@pytest.fixture(scope="session", autouse=True)
def run_migrations():
    """Override conftest's DB-dependent session fixture — these tests are pure."""
    yield


# ── build_event ───────────────────────────────────────────────────────────────
class TestBuildEvent:
    def test_basic_shape(self):
        e = build_event("trade", "filled BUY", symbol="BTC/USDT", payload={"x": 1})
        assert e["category"] == "trade"
        assert e["level"] == "info"
        assert e["symbol"] == "BTC/USDT"
        assert e["message"] == "filled BUY"
        assert e["payload"] == {"x": 1}
        assert "ts" in e

    def test_unknown_category_falls_back_to_data(self):
        assert build_event("bogus", "m")["category"] == "data"

    def test_unknown_level_falls_back_to_info(self):
        assert build_event("trade", "m", level="loud")["level"] == "info"

    def test_payload_defaults_to_empty_dict(self):
        assert build_event("job", "m")["payload"] == {}

    def test_message_coerced_to_str(self):
        assert build_event("data", 12345)["message"] == "12345"

    def test_all_valid_categories_pass_through(self):
        for c in VALID_CATEGORIES:
            assert build_event(c, "m")["category"] == c

    def test_all_valid_levels_pass_through(self):
        for lvl in VALID_LEVELS:
            assert build_event("trade", "m", level=lvl)["level"] == lvl


# ── log_event (mocked I/O) ────────────────────────────────────────────────────
class TestLogEvent:
    async def test_persists_and_broadcasts(self, mocker):
        # Mock the session context manager
        mock_session = mocker.AsyncMock()
        mock_ctx = mocker.MagicMock()
        mock_ctx.__aenter__ = mocker.AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = mocker.AsyncMock(return_value=False)
        mocker.patch("app.db.session.AsyncSessionLocal", return_value=mock_ctx)
        mock_broadcast = mocker.patch(
            "app.ws.manager.ws_manager.broadcast", new=mocker.AsyncMock()
        )

        await log_event("trade", "filled", symbol="BTC/USDT")

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_broadcast.assert_awaited_once()
        channel, data = mock_broadcast.await_args.args
        assert channel == EVENTS_CHANNEL
        assert data["type"] == "event"
        assert data["category"] == "trade"

    async def test_never_raises_on_db_error(self, mocker):
        mocker.patch("app.db.session.AsyncSessionLocal", side_effect=RuntimeError("db down"))
        mocker.patch("app.ws.manager.ws_manager.broadcast", new=mocker.AsyncMock())
        # Must not raise
        await log_event("error", "something", level="error")

    async def test_broadcast_skipped_when_disabled(self, mocker):
        mock_session = mocker.AsyncMock()
        mock_ctx = mocker.MagicMock()
        mock_ctx.__aenter__ = mocker.AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = mocker.AsyncMock(return_value=False)
        mocker.patch("app.db.session.AsyncSessionLocal", return_value=mock_ctx)
        mock_broadcast = mocker.patch(
            "app.ws.manager.ws_manager.broadcast", new=mocker.AsyncMock()
        )
        await log_event("job", "ran", broadcast=False)
        mock_broadcast.assert_not_awaited()
