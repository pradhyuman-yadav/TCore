from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


def compute_composite_score(
    values: dict[str, float | None],
    weights: dict[str, float],
) -> float | None:
    """
    Weighted average of non-None indicator values.
    Weights are renormalized to sum to 1 across non-None indicators.
    Returns None if no valid (non-None) values exist.
    """
    total_weight = 0.0
    weighted_sum = 0.0

    for name, value in values.items():
        if value is None:
            continue
        w = weights.get(name, 0.0)
        if w <= 0.0:
            continue
        weighted_sum += value * w
        total_weight += w

    if total_weight < 1e-10:
        return None

    return weighted_sum / total_weight


def classify_zone(
    score: float,
    buy_threshold: float,
    sell_threshold: float,
) -> str:
    if score >= buy_threshold:
        return "buy"
    if score <= sell_threshold:
        return "sell"
    return "neutral"


async def snapshot_composite(
    symbol: str,
    strategy_id: UUID,
    score: float,
    zone: str,
    db: AsyncSession,
) -> None:
    from app.db.models import CompositeScore
    from app.state import app_state

    now = datetime.now(timezone.utc)
    db.add(
        CompositeScore(
            time=now,
            symbol=symbol,
            strategy_id=strategy_id,
            score=score,
            zone=zone,
        )
    )
    await db.commit()

    app_state.composite_scores[symbol] = {"score": score, "zone": zone, "time": now.isoformat()}
