"""
Tests for the Claude trader agent (app.services.trader_agent).

Prompt-building and response-parsing are pure and tested directly. The network
call is mocked — no real HTTP. Asserts the call constraints: single user
message, token read from env (never hardcoded).
"""
from __future__ import annotations

import json

import pytest

from app.services.trader_agent import (
    AgentProposal,
    build_agent_prompt,
    parse_agent_response,
    propose_trade,
)


@pytest.fixture(scope="session", autouse=True)
def run_migrations():
    """Override conftest's DB-dependent session fixture — these tests are pure."""
    yield


def _snapshot(**over) -> dict:
    base = {
        "symbol": "BTC/USDT",
        "price": 40_000.0,
        "composite_score": 0.4,
        "zone": "buy",
        "indicators": {"rsi": 0.3, "macd_hist": 0.5},
        "hawkes_pressure": 0.6,
        "hawkes_regime": "stable",
        "news_sentiment": 0.2,
        "open_position": None,
        "equity": 10_000.0,
        "daily_pnl": 0.0,
    }
    base.update(over)
    return base


# ── build_agent_prompt ────────────────────────────────────────────────────────
class TestBuildPrompt:
    def test_contains_all_features(self):
        p = build_agent_prompt(_snapshot())
        for token in ["BTC/USDT", "40000", "composite_score", "hawkes_pressure",
                      "hawkes_regime", "daily_pnl", "JSON"]:
            assert token in p

    def test_open_position_rendered(self):
        p = build_agent_prompt(_snapshot(open_position={"entry": 39000, "qty": 0.1}))
        assert "39000" in p

    def test_no_position_says_none(self):
        p = build_agent_prompt(_snapshot(open_position=None))
        assert "open_position: none" in p

    def test_demands_json_only(self):
        p = build_agent_prompt(_snapshot())
        assert "Return ONLY a JSON object" in p


# ── parse_agent_response ──────────────────────────────────────────────────────
class TestParseResponse:
    def test_parses_clean_json(self):
        raw = '{"action":"buy","size_fraction":0.5,"confidence":0.8,"reason":"trend up"}'
        prop = parse_agent_response(raw)
        assert prop.action == "buy"
        assert prop.size_fraction == 0.5
        assert prop.confidence == 0.8
        assert prop.reason == "trend up"

    def test_parses_json_in_markdown_fence(self):
        raw = '```json\n{"action":"hold","size_fraction":0,"confidence":0.1,"reason":"unclear"}\n```'
        prop = parse_agent_response(raw)
        assert prop.action == "hold"

    def test_parses_json_with_surrounding_prose(self):
        raw = 'Here is my call: {"action":"sell","size_fraction":0.9,"confidence":0.7,"reason":"weak"} done.'
        prop = parse_agent_response(raw)
        assert prop.action == "sell"

    def test_hold_normalises_size_to_zero(self):
        raw = '{"action":"hold","size_fraction":0.9,"confidence":0.5,"reason":"x"}'
        prop = parse_agent_response(raw)
        assert prop.size_fraction == 0.0

    def test_sell_normalises_size_to_zero(self):
        raw = '{"action":"sell","size_fraction":0.9,"confidence":0.5,"reason":"x"}'
        prop = parse_agent_response(raw)
        assert prop.size_fraction == 0.0

    def test_clamps_out_of_range(self):
        raw = '{"action":"buy","size_fraction":5,"confidence":-2,"reason":"x"}'
        prop = parse_agent_response(raw)
        assert prop.size_fraction == 1.0
        assert prop.confidence == 0.0

    def test_invalid_action_raises(self):
        with pytest.raises(ValueError):
            parse_agent_response('{"action":"yolo","size_fraction":1,"confidence":1,"reason":"x"}')

    def test_missing_reason_defaulted(self):
        raw = '{"action":"buy","size_fraction":0.3,"confidence":0.4}'
        prop = parse_agent_response(raw)
        assert prop.reason == "no reason given"

    def test_to_dict_roundtrip(self):
        prop = AgentProposal(action="buy", size_fraction=0.3333, confidence=0.5, reason="r")
        d = prop.to_dict()
        assert d["action"] == "buy" and d["size_fraction"] == 0.3333


# ── propose_trade (network mocked) ────────────────────────────────────────────
class TestProposeTrade:
    async def test_uses_proxy_when_configured(self, mocker, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROXY_URL", "https://proxy.example")
        monkeypatch.setenv("CLAUDE_PROXY_API_KEY", "secret-token")
        mock_call = mocker.patch(
            "app.services.trader_agent._call_agent_proxy",
            return_value='{"action":"buy","size_fraction":0.5,"confidence":0.9,"reason":"ok"}',
        )
        prop = await propose_trade(_snapshot())
        assert prop is not None and prop.action == "buy"
        mock_call.assert_awaited_once()

    async def test_falls_back_to_direct_without_proxy(self, mocker, monkeypatch):
        monkeypatch.delenv("CLAUDE_PROXY_URL", raising=False)
        mock_direct = mocker.patch(
            "app.services.trader_agent._call_agent_direct",
            return_value='{"action":"hold","size_fraction":0,"confidence":0.2,"reason":"meh"}',
        )
        prop = await propose_trade(_snapshot())
        assert prop is not None and prop.action == "hold"
        mock_direct.assert_awaited_once()

    async def test_returns_none_on_network_error(self, mocker, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROXY_URL", "https://proxy.example")
        mocker.patch(
            "app.services.trader_agent._call_agent_proxy",
            side_effect=RuntimeError("boom"),
        )
        prop = await propose_trade(_snapshot())
        assert prop is None  # caller falls back to rules

    async def test_returns_none_on_garbage_response(self, mocker, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROXY_URL", "https://proxy.example")
        mocker.patch(
            "app.services.trader_agent._call_agent_proxy",
            return_value="not json at all",
        )
        prop = await propose_trade(_snapshot())
        assert prop is None

    async def test_single_user_message_and_env_token(self, mocker, monkeypatch):
        # Verify the call constraints: one user message, token pulled from env.
        monkeypatch.setenv("CLAUDE_PROXY_URL", "https://proxy.example")
        monkeypatch.setenv("CLAUDE_PROXY_API_KEY", "tok-123")
        captured = {}

        async def fake_post(self, url, **kwargs):
            captured["json"] = kwargs.get("json")
            captured["auth"] = kwargs.get("auth")

            class _Resp:
                def raise_for_status(self_inner): ...
                def json(self_inner):
                    return {"choices": [{"message": {"content":
                        '{"action":"hold","size_fraction":0,"confidence":0.1,"reason":"x"}'}}]}
            return _Resp()

        mocker.patch("httpx.AsyncClient.post", new=fake_post)
        prop = await propose_trade(_snapshot())
        assert prop is not None
        msgs = captured["json"]["messages"]
        assert len(msgs) == 1 and msgs[0]["role"] == "user"
        # token came from env, surfaced via _BearerAuth
        assert captured["auth"]._token == "tok-123"
