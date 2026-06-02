"""
System event log — the audit trail behind the Activity tab.

Every meaningful event in the system (a trade decision, a risk-guard veto, an
agent proposal, a regime gate, a trade fill, a control change, a scheduled job,
a data-ingestion batch, an error) is recorded here. Events are persisted to the
`event_log` hypertable AND broadcast over the "events" WebSocket channel so the
UI updates live.

Design
------
- `build_event` is pure: it validates the category/level and assembles the dict
  that is both stored and broadcast. Unit-testable with no I/O.
- `log_event` is the fire-and-forget writer. It opens its own short-lived DB
  session so it never interferes with the caller's transaction, persists the
  row, and broadcasts. It NEVER raises — logging must not break trading.
- Ingestion events are logged at the action/batch level (e.g. "flushed 320
  ticks"), not one row per datum, to keep the trail readable and the DB sane.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

log = structlog.get_logger()

# Categories — keep in sync with the frontend filter chips.
VALID_CATEGORIES = {
    "decision",  # rule/agent decision for a cycle
    "trade",     # order fill / position open-close
    "risk",      # risk-guard veto / clamp / stop / drawdown breaker
    "agent",     # Claude agent proposal
    "regime",    # Hawkes regime gate
    "control",   # kill switch / trading mode change
    "job",       # scheduled job run / completion
    "data",      # data ingestion batch (ohlcv, ticks, news, social)
    "error",     # any handled error worth surfacing
}
VALID_LEVELS = {"info", "warn", "error"}

EVENTS_CHANNEL = "events"


def build_event(
    category: str,
    message: str,
    *,
    level: str = "info",
    symbol: str | None = None,
    payload: dict[str, Any] | None = None,
    ts: datetime | None = None,
) -> dict:
    """
    Validate and assemble an event dict. Pure — no I/O.

    Unknown categories fall back to "data"; unknown levels to "info", so a
    mis-typed call still records something rather than throwing inside a hot path.
    """
    cat = category if category in VALID_CATEGORIES else "data"
    lvl = level if level in VALID_LEVELS else "info"
    when = ts or datetime.now(timezone.utc)
    return {
        "ts": when.isoformat(),
        "category": cat,
        "level": lvl,
        "symbol": symbol,
        "message": str(message),
        "payload": payload or {},
    }


async def log_event(
    category: str,
    message: str,
    *,
    level: str = "info",
    symbol: str | None = None,
    payload: dict[str, Any] | None = None,
    broadcast: bool = True,
) -> None:
    """
    Persist an event and broadcast it live. Never raises.

    Opens its own DB session so it is decoupled from any caller transaction.
    """
    event = build_event(category, message, level=level, symbol=symbol, payload=payload)

    # ── Persist ─────────────────────────────────────────────────────────────
    try:
        from app.db.models import EventLog
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            db.add(EventLog(
                category=event["category"],
                level=event["level"],
                symbol=event["symbol"],
                message=event["message"],
                payload=event["payload"],
            ))
            await db.commit()
    except Exception as exc:
        log.warning("event_log.persist_error", error=str(exc), category=event["category"])

    # ── Broadcast ─────────────────────────────────────────────────────────────
    if broadcast:
        try:
            from app.ws.manager import ws_manager
            await ws_manager.broadcast(EVENTS_CHANNEL, {"type": "event", **event})
        except Exception as exc:
            log.warning("event_log.broadcast_error", error=str(exc))
