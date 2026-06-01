"""
Tests for signal ensemble & regime gating (app.services.signal_ensemble).

Pure — no DB, no network.
"""
from __future__ import annotations

import pytest

from app.services.aggregator import compute_composite_score
from app.services.signal_ensemble import (
    HAWKES_KEY,
    RegimePolicy,
    fold_microstructure,
    gate_entry,
)


@pytest.fixture(scope="session", autouse=True)
def run_migrations():
    """Override conftest's DB-dependent session fixture — these tests are pure."""
    yield


# ── fold_microstructure ───────────────────────────────────────────────────────
class TestFoldMicrostructure:
    def test_adds_pressure_signal(self):
        v, w = fold_microstructure({"rsi": 0.2}, {"rsi": 1.0}, pressure=0.8, weight=0.5)
        assert v[HAWKES_KEY] == pytest.approx(0.8)
        assert w[HAWKES_KEY] == pytest.approx(0.5)
        assert v["rsi"] == 0.2  # original preserved

    def test_does_not_mutate_inputs(self):
        vals = {"rsi": 0.2}
        wts = {"rsi": 1.0}
        fold_microstructure(vals, wts, pressure=0.5, weight=0.5)
        assert HAWKES_KEY not in vals and HAWKES_KEY not in wts

    def test_none_pressure_is_noop(self):
        v, w = fold_microstructure({"rsi": 0.2}, {"rsi": 1.0}, pressure=None, weight=0.5)
        assert HAWKES_KEY not in v

    def test_zero_weight_is_noop(self):
        v, w = fold_microstructure({"rsi": 0.2}, {"rsi": 1.0}, pressure=0.8, weight=0.0)
        assert HAWKES_KEY not in v

    def test_pressure_clamped(self):
        v, _ = fold_microstructure({}, {}, pressure=2.5, weight=1.0)
        assert v[HAWKES_KEY] == 1.0
        v2, _ = fold_microstructure({}, {}, pressure=-9.0, weight=1.0)
        assert v2[HAWKES_KEY] == -1.0

    def test_folds_into_composite_score(self):
        # rsi 0.0 weight 1, pressure +1.0 weight 1 -> composite 0.5
        v, w = fold_microstructure({"rsi": 0.0}, {"rsi": 1.0}, pressure=1.0, weight=1.0)
        score = compute_composite_score(v, w)
        assert score == pytest.approx(0.5)


# ── gate_entry ────────────────────────────────────────────────────────────────
class TestGateEntry:
    def test_reflexive_blocks_buy(self):
        zone, reason = gate_entry("buy", regime="reflexive", pressure=0.9)
        assert zone == "neutral" and "reflexive" in reason

    def test_stable_regime_allows_buy(self):
        zone, _ = gate_entry("buy", regime="stable", pressure=0.5)
        assert zone == "buy"

    def test_negative_flow_blocks_buy(self):
        zone, reason = gate_entry("buy", regime="stable", pressure=-0.3)
        assert zone == "neutral" and "flow" in reason

    def test_positive_flow_confirms_buy(self):
        zone, reason = gate_entry("buy", regime="stable", pressure=0.4)
        assert zone == "buy" and "confirmed" in reason

    def test_sell_never_gated(self):
        zone, _ = gate_entry("sell", regime="reflexive", pressure=-0.9)
        assert zone == "sell"

    def test_neutral_passthrough(self):
        zone, _ = gate_entry("neutral", regime="reflexive", pressure=0.0)
        assert zone == "neutral"

    def test_none_regime_and_pressure_noop(self):
        # Hawkes not yet fitted -> entries pass through unchanged
        zone, _ = gate_entry("buy", regime=None, pressure=None)
        assert zone == "buy"

    def test_policy_can_disable_reflexive_block(self):
        policy = RegimePolicy(block_reflexive_entries=False, require_flow_confirmation=False)
        zone, _ = gate_entry("buy", regime="reflexive", pressure=-0.5, policy=policy)
        assert zone == "buy"

    def test_policy_can_disable_flow_confirmation(self):
        policy = RegimePolicy(require_flow_confirmation=False)
        zone, _ = gate_entry("buy", regime="stable", pressure=-0.9, policy=policy)
        assert zone == "buy"

    def test_custom_min_flow_agreement(self):
        policy = RegimePolicy(min_flow_agreement=0.5)
        # pressure 0.3 < 0.5 -> blocked
        zone, _ = gate_entry("buy", regime="stable", pressure=0.3, policy=policy)
        assert zone == "neutral"
        # pressure 0.6 >= 0.5 -> allowed
        zone2, _ = gate_entry("buy", regime="stable", pressure=0.6, policy=policy)
        assert zone2 == "buy"
