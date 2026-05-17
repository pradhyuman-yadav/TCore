from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ── Endpoint resolution ──────────────────────────────────────────────────────
# Primary: claude-proxy sidecar (OpenAI-compatible, no auth needed)
#   Routes requests through Claude Code CLI → subscription, no API credits.
# Fallback: direct Anthropic API (requires ANTHROPIC_API_KEY)
_PROXY_URL = os.environ.get("CLAUDE_PROXY_URL", "").rstrip("/")
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4"           # proxy model alias
_MODEL_DIRECT = "claude-haiku-4-5-20251001"   # direct API model id


def _make_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, float(v)))


async def _call_claude_proxy(headlines: list[str], symbol: str) -> tuple[float, str]:
    """Call claude-max-api-proxy (OpenAI-compatible). No auth headers needed."""
    joined = "\n".join(f"- {h}" for h in headlines)
    system = (
        "You are a financial sentiment analyzer. "
        "Return ONLY a JSON object: {\"score\": <float -1.0 to 1.0>, \"reasoning\": \"<one sentence>\"}"
    )
    user = (
        f"Score the sentiment of these {symbol} headlines on a scale of "
        f"-1.0 (very bearish) to 1.0 (very bullish):\n{joined}"
    )
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{_PROXY_URL}/v1/chat/completions",
            headers={"content-type": "application/json"},
            json={
                "model": _MODEL,
                "max_tokens": 128,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
            },
        )
        resp.raise_for_status()

    body = resp.json()
    raw = body["choices"][0]["message"]["content"].strip()
    parsed = json.loads(raw)
    score = _clamp(float(parsed["score"]))
    reasoning = str(parsed.get("reasoning", ""))
    return score, reasoning


async def _call_claude_direct(headlines: list[str], symbol: str) -> tuple[float, str]:
    """Call Anthropic API directly with ANTHROPIC_API_KEY."""
    from app.services.claude_auth import get_auth_headers
    auth_headers = await get_auth_headers()
    joined = "\n".join(f"- {h}" for h in headlines)
    prompt = (
        f"You are a financial sentiment analyzer. Score the overall sentiment of these "
        f"news headlines for {symbol} on a continuous scale from -1.0 (very bearish) to "
        f"1.0 (very bullish). Return ONLY a JSON object with two keys:\n"
        f"  \"score\": a float between -1.0 and 1.0\n"
        f"  \"reasoning\": a single sentence explaining the score\n\n"
        f"Headlines:\n{joined}"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _ANTHROPIC_URL,
            headers={
                **auth_headers,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": _MODEL_DIRECT,
                "max_tokens": 128,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()

    body = resp.json()
    raw = body["content"][0]["text"].strip()
    parsed = json.loads(raw)
    score = _clamp(float(parsed["score"]))
    reasoning = str(parsed.get("reasoning", ""))
    return score, reasoning


async def _call_claude(headlines: list[str], symbol: str) -> tuple[float, str]:
    """Route to proxy if available, otherwise direct API."""
    if _PROXY_URL:
        return await _call_claude_proxy(headlines, symbol)
    # Direct path — requires ANTHROPIC_API_KEY or Claude OAuth credentials
    # If neither is configured, raises RuntimeError with a clear message
    return await _call_claude_direct(headlines, symbol)


def claude_mode() -> str:
    """Returns 'proxy' or 'direct' based on current config."""
    return "proxy" if _PROXY_URL else "direct"


async def score_sentiment(
    headlines: list[str],
    symbol: str,
    source: str = "news",
    cache_ttl_minutes: int = 15,
    db: AsyncSession | None = None,
) -> float | None:
    """
    Returns a sentiment score in [-1.0, 1.0] or None on failure.
    Caches results in sentiment_cache by content hash.
    Never raises.
    """
    if not headlines:
        return None

    from app.db.models import SentimentCache

    joined = "\n".join(headlines)
    content_hash = _make_hash(joined)

    if db is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=cache_ttl_minutes)
        row = (
            await db.execute(
                select(SentimentCache).where(
                    SentimentCache.content_hash == content_hash,
                    SentimentCache.fetched_at >= cutoff,
                )
            )
        ).scalars().first()
        if row is not None:
            return row.score

    try:
        score, reasoning = await _call_claude(headlines, symbol)
    except Exception:
        return None

    if db is not None:
        try:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(SentimentCache).values(
                source=source,
                symbol=symbol,
                raw_content=joined,
                score=score,
                reasoning=reasoning,
                model_used=_MODEL if _PROXY_URL else _MODEL_DIRECT,
                fetched_at=datetime.now(timezone.utc),
                content_hash=content_hash,
            ).on_conflict_do_update(
                index_elements=["content_hash"],
                set_={"score": score, "reasoning": reasoning, "fetched_at": datetime.now(timezone.utc)},
            )
            await db.execute(stmt)
            await db.commit()
        except Exception:
            pass

    return score
