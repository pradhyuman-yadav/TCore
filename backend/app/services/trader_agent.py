"""
Claude trader agent — the reasoning layer.

What it is
----------
An optional decision mode that replaces the deterministic rule engine with a
Claude call. Given a feature snapshot (price, indicators, composite score,
Hawkes order-flow pressure + regime, open position, equity, recent sentiment),
the agent returns a structured proposal: action + size fraction + confidence +
reason. The proposal is then handed to the risk guard, which sizes and clamps
it. **The agent proposes; the risk guard disposes** — the agent can never exceed
a hard risk limit, because it does not size the order itself.

Security / call constraints (hard requirements):
  - The proxy bearer token is read from CLAUDE_PROXY_API_KEY at call time and is
    NEVER stored, logged, or hardcoded.
  - Every request sends a single user message and nothing else — no system
    prompt, no extra turns. One message per call.

Pure helpers (`build_agent_prompt`, `parse_agent_response`) are separated from
the network call so prompt construction and response parsing are unit-testable
without any HTTP.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from app.services.sentiment_agent import (
    _ANTHROPIC_URL,
    _MODEL,
    _MODEL_DIRECT,
    _BearerAuth,
    _extract_json,
)

_VALID_ACTIONS = {"buy", "sell", "hold"}


@dataclass
class AgentProposal:
    action: str            # "buy" | "sell" | "hold"
    size_fraction: float   # 0.0–1.0 — fraction of the risk-guard-sized position
    confidence: float      # 0.0–1.0
    reason: str

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "size_fraction": round(self.size_fraction, 4),
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
        }


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def build_agent_prompt(snapshot: dict) -> str:
    """
    Build the single user message from a feature snapshot. Pure — no I/O.

    The snapshot is rendered as compact JSON-ish text so the model sees every
    feature explicitly. The instruction is strict about output format because we
    parse JSON back out.
    """
    import json

    pos = snapshot.get("open_position")
    pos_txt = "none" if not pos else json.dumps(pos)

    return (
        "You are a disciplined crypto trading agent. Decide the next action for a "
        "long/flat spot position. A separate hard risk layer will size and clamp "
        "your decision and can veto it — so propose direction and conviction, not "
        "absolute size. Choosing 'hold' is always acceptable when edge is unclear.\n\n"
        "Market snapshot:\n"
        f"- symbol: {snapshot.get('symbol')}\n"
        f"- price: {snapshot.get('price')}\n"
        f"- composite_score (-1..1): {snapshot.get('composite_score')}\n"
        f"- zone: {snapshot.get('zone')}\n"
        f"- indicators: {json.dumps(snapshot.get('indicators', {}))}\n"
        f"- hawkes_pressure (-1 sell..+1 buy): {snapshot.get('hawkes_pressure')}\n"
        f"- hawkes_regime (stable/reflexive): {snapshot.get('hawkes_regime')}\n"
        f"- news_sentiment (-1..1): {snapshot.get('news_sentiment')}\n"
        f"- open_position: {pos_txt}\n"
        f"- equity_usdt: {snapshot.get('equity')}\n"
        f"- daily_pnl_usdt: {snapshot.get('daily_pnl')}\n"
        f"- past_performance: {snapshot.get('performance', 'no prior performance data')}\n\n"
        "Guidance: avoid opening new longs in a reflexive (self-exciting) regime; "
        "prefer entries confirmed by positive order-flow pressure; respect that a "
        "negative daily PnL means tighten up. If a position is open and the thesis "
        "has weakened, prefer to exit (sell). If past_performance shows this regime "
        "has been unprofitable, lower conviction or hold.\n\n"
        "Return ONLY a JSON object, no prose:\n"
        '{"action": "buy|sell|hold", "size_fraction": <0.0-1.0>, '
        '"confidence": <0.0-1.0>, "reason": "<one sentence>"}'
    )


def parse_agent_response(raw: str) -> AgentProposal:
    """
    Parse and validate the model's JSON reply into an AgentProposal. Pure.

    Raises ValueError when the action is missing/invalid. size_fraction and
    confidence are clamped to [0, 1]; a 'hold' is normalised to size_fraction 0.
    """
    parsed = _extract_json(raw)
    action = str(parsed.get("action", "")).strip().lower()
    if action not in _VALID_ACTIONS:
        raise ValueError(f"invalid action from agent: {action!r}")

    size_fraction = _clamp01(parsed.get("size_fraction", 0.0))
    confidence = _clamp01(parsed.get("confidence", 0.0))
    reason = str(parsed.get("reason", "")).strip() or "no reason given"

    if action != "buy":
        size_fraction = 0.0  # only a buy sizes a new position

    return AgentProposal(
        action=action,
        size_fraction=size_fraction,
        confidence=confidence,
        reason=reason,
    )


async def _call_agent_proxy(message: str, proxy_url: str, timeout: float) -> str:
    """Call the OpenAI-compatible proxy. Token read fresh from env, never stored."""
    token = os.environ.get("CLAUDE_PROXY_API_KEY", "")
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.post(
            f"{proxy_url}/v1/chat/completions",
            auth=_BearerAuth(token),
            headers={"content-type": "application/json"},
            json={
                "model": _MODEL,
                "max_tokens": 256,
                "messages": [{"role": "user", "content": message}],
            },
        )
        resp.raise_for_status()
    body = resp.json()
    return body["choices"][0]["message"]["content"].strip()


async def _call_agent_direct(message: str, timeout: float) -> str:
    """Call the Anthropic API directly (OAuth/API-key headers from claude_auth)."""
    from app.services.claude_auth import get_auth_headers

    auth_headers = await get_auth_headers()
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            _ANTHROPIC_URL,
            headers={
                **auth_headers,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": _MODEL_DIRECT,
                "max_tokens": 256,
                "messages": [{"role": "user", "content": message}],
            },
        )
        resp.raise_for_status()
    body = resp.json()
    return body["content"][0]["text"].strip()


async def propose_trade(snapshot: dict, *, timeout: float = 30.0) -> AgentProposal | None:
    """
    Ask the agent for a trade proposal. Returns None on any failure so the caller
    can fall back to the deterministic rule engine. Never raises.
    """
    proxy_url = os.environ.get("CLAUDE_PROXY_URL", "").rstrip("/")
    try:
        message = build_agent_prompt(snapshot)
        if proxy_url:
            raw = await _call_agent_proxy(message, proxy_url, timeout)
        else:
            raw = await _call_agent_direct(message, timeout)
        return parse_agent_response(raw)
    except Exception:
        return None
