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
_PROXY_API_KEY = os.environ.get("CLAUDE_PROXY_API_KEY", "")  # Bearer token — set via env, never hardcoded
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4"           # proxy model alias
_MODEL_DIRECT = "claude-haiku-4-5-20251001"   # direct API model id


def _make_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, float(v)))


def _extract_json(text: str) -> dict:
    """
    Parse JSON from a response that may contain markdown fences or surrounding prose.
    Tries bare parse first, then hunts for the first { ... } block.
    """
    text = text.strip()
    # Fast path — already bare JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip markdown code fences  ```json ... ``` or ``` ... ```
    import re
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Find first { ... } block
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"No JSON object found in response: {text!r}")


class _BearerAuth(httpx.Auth):
    """Re-injects Authorization header on every hop, including HTTP→HTTPS redirects."""
    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: httpx.Request):  # type: ignore[override]
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


async def _call_claude_proxy(headlines: list[str], symbol: str) -> tuple[float, str]:
    """Call claude-max-api-proxy (OpenAI-compatible)."""
    joined = "\n".join(f"- {h}" for h in headlines)
    message = (
        "You are a financial sentiment analyzer. "
        "Return ONLY a JSON object: {\"score\": <float -1.0 to 1.0>, \"reasoning\": \"<one sentence>\"}\n\n"
        f"Score the sentiment of these {symbol} headlines on a scale of "
        f"-1.0 (very bearish) to 1.0 (very bullish):\n{joined}"
    )
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.post(
            f"{_PROXY_URL}/v1/chat/completions",
            auth=_BearerAuth(_PROXY_API_KEY),
            headers={"content-type": "application/json"},
            json={
                "model": _MODEL,
                "max_tokens": 128,
                "messages": [
                    {"role": "user", "content": message},
                ],
            },
        )
        resp.raise_for_status()

    body = resp.json()
    raw = body["choices"][0]["message"]["content"].strip()
    parsed = _extract_json(raw)
    score = _clamp(float(parsed["score"]))
    reasoning = str(parsed.get("reasoning", ""))
    return score, reasoning


async def _call_claude_direct(headlines: list[str], symbol: str) -> tuple[float, str]:
    """Call Anthropic API directly with ANTHROPIC_API_KEY."""
    from app.services.claude_auth import get_auth_headers
    auth_headers = await get_auth_headers()
    joined = "\n".join(f"- {h}" for h in headlines)
    message = (
        "You are a financial sentiment analyzer. "
        "Return ONLY a JSON object: {\"score\": <float -1.0 to 1.0>, \"reasoning\": \"<one sentence>\"}\n\n"
        f"Score the sentiment of these {symbol} headlines on a scale of "
        f"-1.0 (very bearish) to 1.0 (very bullish):\n{joined}"
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
                "messages": [{"role": "user", "content": message}],
            },
        )
        resp.raise_for_status()

    body = resp.json()
    raw = body["content"][0]["text"].strip()
    parsed = _extract_json(raw)
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


# ── Source reach lookup ───────────────────────────────────────────────────────
_SOURCE_REACH: dict[str, int] = {
    "coindesk":      5_000_000,
    "cointelegraph": 4_000_000,
    "decrypt":       2_000_000,
    "reuters":       26_000_000,
    "bloomberg":     30_000_000,
    "economictimes": 8_000_000,
    "wsj":           38_000_000,
    "ft":            20_000_000,
    "cnbc":          40_000_000,
    "bbc":           100_000_000,
}
_DEFAULT_REACH = 100_000


async def get_source_reach(source: str, platform: str) -> int:
    """
    Returns estimated follower/subscriber count for a news or social source.
    Reddit: fetches live subscriber count from public JSON API.
    Others: matched against known-source dict or default.
    """
    key = source.lower()

    # Reddit: live subscriber count
    if platform == "reddit" and source.startswith("r/"):
        subreddit = source[2:]
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(
                    f"https://www.reddit.com/r/{subreddit}/about.json",
                    headers={"User-Agent": "TradeCore/1.0"},
                )
                return int(r.json()["data"]["subscribers"])
        except Exception:
            return _DEFAULT_REACH

    # Named sources
    for name, reach in _SOURCE_REACH.items():
        if name in key:
            return reach
    return _DEFAULT_REACH


async def _get_symbol_volume(symbol: str, db: "AsyncSession") -> float:
    """Fetch total volume for symbol over last 24 hours from OHLCV table."""
    try:
        from app.db.models import OHLCV
        from sqlalchemy import select as sa_select
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        rows = (
            await db.execute(
                sa_select(OHLCV.volume).where(
                    OHLCV.symbol == symbol,
                    OHLCV.time >= cutoff,
                )
            )
        ).scalars().all()
        return float(sum(r for r in rows if r is not None))
    except Exception:
        return 0.0


async def _call_claude_impact_proxy(message: str, symbol: str) -> tuple[float, str]:
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.post(
            f"{_PROXY_URL}/v1/chat/completions",
            auth=_BearerAuth(_PROXY_API_KEY),
            headers={"content-type": "application/json"},
            json={
                "model": _MODEL,
                "max_tokens": 128,
                "messages": [{"role": "user", "content": message}],
            },
        )
        resp.raise_for_status()
    body = resp.json()
    raw = body["choices"][0]["message"]["content"].strip()
    parsed = _extract_json(raw)
    score = max(0.0, min(1.0, float(parsed["impact"])))
    return round(score, 4), str(parsed.get("reasoning", ""))


async def _call_claude_impact_direct(message: str, symbol: str) -> tuple[float, str]:
    from app.services.claude_auth import get_auth_headers
    auth_headers = await get_auth_headers()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _ANTHROPIC_URL,
            headers={**auth_headers, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": _MODEL_DIRECT,
                "max_tokens": 128,
                "messages": [{"role": "user", "content": message}],
            },
        )
        resp.raise_for_status()
    body = resp.json()
    raw = body["content"][0]["text"].strip()
    parsed = _extract_json(raw)
    score = max(0.0, min(1.0, float(parsed["impact"])))
    return round(score, 4), str(parsed.get("reasoning", ""))


async def score_price_impact(
    text: str,
    symbol: str,
    source_reach: int,
    symbol_volume: float,
    cache_ttl_minutes: int = 1440,   # 24h — impact score for a given item is stable
    db: "AsyncSession | None" = None,
) -> float | None:
    """
    Returns a 4-decimal probability [0.0000, 1.0000] of price impact.
    Cache-first: sha256(text+symbol) checked in SentimentCache before any Claude call.
    """
    if not text:
        return None

    from app.db.models import SentimentCache

    content_hash = _make_hash(text + symbol)

    # ── Cache read ────────────────────────────────────────────────────
    if db is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=cache_ttl_minutes)
        row = (
            await db.execute(
                select(SentimentCache).where(
                    SentimentCache.content_hash == content_hash,
                    SentimentCache.source == "impact",
                    SentimentCache.fetched_at >= cutoff,
                )
            )
        ).scalars().first()
        if row is not None:
            return row.score   # cache hit — zero Claude calls

    # ── Claude call ───────────────────────────────────────────────────
    try:
        message = (
            f"You are a financial market-impact analyst.\n"
            f"Estimate the probability (0.0000 to 1.0000, exactly 4 decimal places) "
            f"that this content will move the price of {symbol}.\n\n"
            f"Signals:\n"
            f"- Source reach: {source_reach:,} followers/subscribers\n"
            f"- Asset 24h volume: ${symbol_volume:,.0f}\n\n"
            f"Return ONLY a JSON object: "
            f'{{\"impact\": <float 0.0000-1.0000>, \"reasoning\": \"<one sentence>\"}}\n\n'
            f"Content: {text}"
        )
        if _PROXY_URL:
            score, reasoning = await _call_claude_impact_proxy(message, symbol)
        else:
            score, reasoning = await _call_claude_impact_direct(message, symbol)
    except Exception:
        return None

    # ── Cache write ───────────────────────────────────────────────────
    if db is not None:
        try:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(SentimentCache).values(
                source="impact",
                symbol=symbol,
                raw_content=text,
                score=score,
                reasoning=reasoning,
                model_used=_MODEL if _PROXY_URL else _MODEL_DIRECT,
                fetched_at=datetime.now(timezone.utc),
                content_hash=content_hash,
            ).on_conflict_do_update(
                index_elements=["content_hash"],
                set_={
                    "score": score,
                    "reasoning": reasoning,
                    "fetched_at": datetime.now(timezone.utc),
                },
            )
            await db.execute(stmt)
            await db.commit()
        except Exception:
            pass

    return score


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
