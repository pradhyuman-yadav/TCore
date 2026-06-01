"""
Signal ensemble & regime gating.

Why this exists
---------------
Two edges were computed but never used in the trade decision:

  1. Hawkes order-flow imbalance pressure (`app_state.hawkes_pressure`) — a
     microstructure signal in [-1, 1] (net buy vs sell taker pressure).
  2. The Hawkes branching regime (`app_state.hawkes_regime`) — 'stable' vs
     'reflexive'. A reflexive regime (branching ratio ≥ ~0.9) is self-exciting
     and chaotic: order flow begets more order flow, mean-reversion edges break
     down, and stops get run. Opening fresh risk there is a good way to lose.

`aggregator.compute_composite_score` already fuses arbitrary named signals by
weight, so folding pressure in is just adding one more weighted input — no new
fusion engine needed. This module provides:

  - `fold_microstructure`: add Hawkes pressure to the value/weight dicts.
  - `gate_entry`: veto/downgrade entries based on regime and flow confirmation.

Pure functions — no I/O — so they are fully unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass

HAWKES_KEY = "hawkes_pressure"


def fold_microstructure(
    values: dict[str, float | None],
    weights: dict[str, float],
    *,
    pressure: float | None,
    weight: float,
) -> tuple[dict[str, float | None], dict[str, float]]:
    """
    Return new (values, weights) with Hawkes pressure folded in as one signal.

    No mutation of the inputs. When pressure is None or weight <= 0 the inputs
    are returned unchanged (copies). Pressure is clamped to [-1, 1] to match the
    range of the other normalised indicators.
    """
    new_values = dict(values)
    new_weights = dict(weights)
    if pressure is None or weight <= 0.0:
        return new_values, new_weights
    new_values[HAWKES_KEY] = max(-1.0, min(1.0, float(pressure)))
    new_weights[HAWKES_KEY] = float(weight)
    return new_values, new_weights


@dataclass
class RegimePolicy:
    """How the regime/order-flow gate treats proposed entries."""
    block_reflexive_entries: bool = True   # no new longs in a reflexive regime
    require_flow_confirmation: bool = True  # order flow must agree with the entry
    min_flow_agreement: float = 0.0        # required pressure to confirm a buy


def gate_entry(
    zone: str,
    regime: str | None,
    pressure: float | None,
    policy: RegimePolicy | None = None,
) -> tuple[str, str]:
    """
    Apply regime/flow gating to a proposed zone for a long/flat system.

    Returns (gated_zone, reason). Exits are never blocked — only entries (the
    "buy" zone) can be downgraded to "neutral". `regime`/`pressure` may be None
    (e.g. Hawkes not yet fitted for this symbol): in that case the gate is a
    no-op and entries pass through unchanged.
    """
    p = policy or RegimePolicy()

    if zone != "buy":
        return zone, "exit/neutral not gated"

    if p.block_reflexive_entries and regime == "reflexive":
        return "neutral", "reflexive regime: entry blocked"

    if p.require_flow_confirmation and pressure is not None:
        if pressure < p.min_flow_agreement:
            return "neutral", (
                f"order flow disagrees: pressure {pressure:.2f} "
                f"< {p.min_flow_agreement}"
            )

    return "buy", "entry confirmed by regime/flow"
