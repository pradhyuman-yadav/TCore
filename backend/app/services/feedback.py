"""
Performance feedback loop.

Why this exists
---------------
Without a feedback loop the agent is static: it never learns whether its own
decisions actually made money. This module closes the loop. Every closed trade
is journaled with the decision context it was made under (mode, regime,
decision source, confidence). A periodic job aggregates those journal records
into per-regime / per-mode expectancy and hit-rate, which is then fed back into
the trader agent's prompt as context — so it can, for example, learn to stand
down in a regime where it has historically lost.

This file holds the PURE core: aggregation math and prompt formatting, operating
on plain `JournalRecord` objects. DB persistence, the scheduler job, and the
agent wiring live elsewhere and call into these functions, keeping the
hard-to-test I/O thin and the testable logic fat.
"""
from __future__ import annotations

from dataclasses import dataclass

_UNKNOWN_REGIME = "unknown"


@dataclass
class JournalRecord:
    """One closed-trade outcome with the context it was decided under."""
    mode: str                      # "paper" | "live"
    pnl: float                     # realised net PnL of the round trip
    regime: str | None = None      # "stable" | "reflexive" | None
    decision_mode: str = "rules"   # "rules" | "agent"
    confidence: float | None = None


def _stats(pnls: list[float]) -> dict:
    n = len(pnls)
    if n == 0:
        return {"count": 0, "wins": 0, "win_rate": 0.0, "expectancy": 0.0,
                "total_pnl": 0.0, "profit_factor": 0.0}
    wins = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    if gross_loss <= 1e-12:
        pf = 999.0 if gross_win > 0 else 0.0
    else:
        pf = gross_win / gross_loss
    return {
        "count": n,
        "wins": wins,
        "win_rate": round(wins / n, 4),
        "expectancy": round(total / n, 4),
        "total_pnl": round(total, 4),
        "profit_factor": round(pf, 4),
    }


def aggregate_performance(records: list[JournalRecord]) -> dict:
    """
    Group closed-trade outcomes into mode → {regime → stats, "_all": stats}.

    Pure. Regime None is bucketed under "unknown". Returns {} for no records.
    """
    by_mode: dict[str, dict[str, list[float]]] = {}
    for r in records:
        regime = r.regime or _UNKNOWN_REGIME
        by_mode.setdefault(r.mode, {}).setdefault(regime, []).append(r.pnl)
        by_mode[r.mode].setdefault("_all", []).append(r.pnl)

    summary: dict[str, dict] = {}
    for mode, regimes in by_mode.items():
        summary[mode] = {regime: _stats(pnls) for regime, pnls in regimes.items()}
    return summary


def format_feedback_for_prompt(
    summary: dict,
    mode: str,
    regime: str | None,
) -> str:
    """
    Render a compact one-line-ish performance note for the agent prompt.

    Focuses on the current `mode` and the relevant `regime` bucket plus the
    overall bucket. Returns "no prior performance data" when nothing is known
    yet — the agent should not infer an edge from an empty history.
    """
    mode_summary = summary.get(mode)
    if not mode_summary:
        return "no prior performance data"

    parts: list[str] = []
    overall = mode_summary.get("_all")
    if overall and overall["count"] > 0:
        parts.append(
            f"overall {overall['count']} trades, win {overall['win_rate']:.0%}, "
            f"expectancy {overall['expectancy']:+.2f} USDT"
        )

    key = regime or _UNKNOWN_REGIME
    rstats = mode_summary.get(key)
    if rstats and rstats["count"] > 0:
        warn = " (historically unprofitable here)" if rstats["expectancy"] <= 0 else ""
        parts.append(
            f"in '{key}' regime: {rstats['count']} trades, "
            f"win {rstats['win_rate']:.0%}, expectancy {rstats['expectancy']:+.2f}{warn}"
        )

    return "; ".join(parts) if parts else "no prior performance data"
