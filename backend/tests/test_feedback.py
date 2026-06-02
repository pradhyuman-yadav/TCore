"""
Tests for the performance feedback core (app.services.feedback).

Pure — no DB, no network.
"""
from __future__ import annotations

import pytest

from app.services.feedback import (
    JournalRecord,
    aggregate_performance,
    format_feedback_for_prompt,
)


@pytest.fixture(scope="session", autouse=True)
def run_migrations():
    """Override conftest's DB-dependent session fixture — these tests are pure."""
    yield


def _rec(pnl, regime="stable", mode="paper", decision_mode="agent"):
    return JournalRecord(mode=mode, pnl=pnl, regime=regime, decision_mode=decision_mode)


# ── aggregate_performance ─────────────────────────────────────────────────────
class TestAggregate:
    def test_empty_returns_empty(self):
        assert aggregate_performance([]) == {}

    def test_groups_by_mode_and_regime(self):
        recs = [
            _rec(10, "stable"), _rec(-5, "stable"),
            _rec(-8, "reflexive"),
            _rec(20, "stable", mode="live"),
        ]
        summary = aggregate_performance(recs)
        assert set(summary) == {"paper", "live"}
        assert summary["paper"]["stable"]["count"] == 2
        assert summary["paper"]["reflexive"]["count"] == 1
        assert summary["paper"]["_all"]["count"] == 3
        assert summary["live"]["stable"]["count"] == 1

    def test_stats_values(self):
        recs = [_rec(10), _rec(20), _rec(-10)]
        s = aggregate_performance(recs)["paper"]["stable"]
        assert s["count"] == 3
        assert s["wins"] == 2
        assert s["win_rate"] == pytest.approx(2 / 3, abs=1e-3)
        assert s["expectancy"] == pytest.approx(20 / 3, abs=1e-3)
        assert s["total_pnl"] == pytest.approx(20.0)
        assert s["profit_factor"] == pytest.approx(3.0)

    def test_no_losses_profit_factor_finite(self):
        s = aggregate_performance([_rec(5), _rec(5)])["paper"]["stable"]
        assert s["profit_factor"] == 999.0

    def test_none_regime_bucketed_unknown(self):
        s = aggregate_performance([_rec(5, regime=None)])
        assert "unknown" in s["paper"]


# ── format_feedback_for_prompt ────────────────────────────────────────────────
class TestFormat:
    def test_no_data_message(self):
        assert format_feedback_for_prompt({}, "paper", "stable") == "no prior performance data"

    def test_unknown_mode_message(self):
        summary = aggregate_performance([_rec(5, mode="live")])
        assert format_feedback_for_prompt(summary, "paper", "stable") == "no prior performance data"

    def test_includes_overall_and_regime(self):
        recs = [_rec(10, "stable"), _rec(-5, "stable"), _rec(-8, "reflexive")]
        summary = aggregate_performance(recs)
        txt = format_feedback_for_prompt(summary, "paper", "stable")
        assert "overall" in txt and "stable" in txt

    def test_warns_on_unprofitable_regime(self):
        recs = [_rec(-8, "reflexive"), _rec(-4, "reflexive")]
        summary = aggregate_performance(recs)
        txt = format_feedback_for_prompt(summary, "paper", "reflexive")
        assert "historically unprofitable" in txt

    def test_no_warning_when_profitable(self):
        recs = [_rec(8, "stable"), _rec(4, "stable")]
        summary = aggregate_performance(recs)
        txt = format_feedback_for_prompt(summary, "paper", "stable")
        assert "historically unprofitable" not in txt

    def test_handles_none_regime_arg(self):
        recs = [_rec(5, regime=None)]
        summary = aggregate_performance(recs)
        txt = format_feedback_for_prompt(summary, "paper", None)
        assert "unknown" in txt
