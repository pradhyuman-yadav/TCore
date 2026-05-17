from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.claude_auth import get_auth_headers

_ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4-5-20251001"


def _make_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, float(v)))


async def _call_claude(headlines: list[str], symbol: str) -> tuple[float, str]:
    """Calls Claude API. Returns (score, reasoning)."""
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
            _ANTHROPIC_MESSAGES_URL,
            headers={
                **auth_headers,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": _MODEL,
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


async def score_sentiment(
    headlines: list[str],
    symbol: str,
    source: str = "news",
    cache_ttl_minutes: int = 15,
    db: AsyncSession | None = None,
) -> float | None:
    """
    Returns a sentiment score in [-1.0, 1.0] or None on failure.
    Uses Claude OAuth token — no API key needed.
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
                model_used=_MODEL,
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
