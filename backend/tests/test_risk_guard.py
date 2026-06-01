"""
Tests for the deterministic risk guard (app.services.risk_guard).

All pure — no DB, no network.
"""
from __future__ import annotations

import pytest

from app.services.rule_engine import TradeSignal
from app.services.risk_guard import (
    PositionState,
    RiskContext,
    RiskDecision,
    RiskParams,
    _drawdown,
    _stop_distance,
    _target_distance,
    apply_risk_guard,
    compute_atr,
)


@pytest.fixture(scope="session", autouse=True)
def run_migrations():
    """Override conftest's DB-dependent session fixture — these tests are pure."""
    yield


def _buy(reason="buy zone signal") -> TradeSignal:
    return TradeSignal(action="buy", quantity_usdt=100.0, reason=reason)


def _sell() -> TradeSignal:
    return TradeSignal(action="sell", quantity_usdt=0.0, reason="sell zone signal")


def _hold() -> TradeSignal:
    return TradeSignal(action="hold", quantity_usdt=0.0, reason="zone is neutral")


# ── RiskParams validation ─────────────────────────────────────────────────────
class TestRiskParams:
    def test_defaults_valid(self):
        p = RiskParams()
        assert 0 < p.risk_per_trade_pct < 1

    @pytest.mark.parametrize("kwargs", [
        {"risk_per_trade_pct": 0.0},
        {"risk_per_trade_pct": 1.0},
        {"stop_loss_atr_mult": 0.0},
        {"max_position_pct": 0.0},
        {"max_position_pct": 1.5},
        {"max_drawdown_pct": 0.0},
        {"max_drawdown_pct": 1.0},
    ])
    def test_rejects_bad_params(self, kwargs):
        with pytest.raises(ValueError):
            RiskParams(**kwargs)


# ── Helper math ────────────────────────────────────────────────────────────
class TestHelpers:
    def test_stop_distance_atr(self):
        p = RiskParams(stop_loss_atr_mult=2.0)
        assert _stop_distance(100.0, atr=1.5, p=p) == pytest.approx(3.0)

    def test_stop_distance_fallback_when_no_atr(self):
        p = RiskParams(stop_loss_pct_fallback=0.02)
        assert _stop_distance(100.0, atr=None, p=p) == pytest.approx(2.0)

    def test_target_distance_keeps_rr_on_fallback(self):
        p = RiskParams(stop_loss_atr_mult=2.0, take_profit_atr_mult=3.0,
                       stop_loss_pct_fallback=0.02)
        # rr = 3/2 = 1.5 -> target dist = 100*0.02*1.5 = 3.0
        assert _target_distance(100.0, atr=None, p=p) == pytest.approx(3.0)

    def test_drawdown(self):
        assert _drawdown(80.0, 100.0) == pytest.approx(0.2)
        assert _drawdown(120.0, 100.0) == 0.0  # above peak -> no DD
        assert _drawdown(50.0, 0.0) == 0.0     # guard against zero peak


# ── Forced exits ──────────────────────────────────────────────────────────────
class TestForcedExits:
    def test_stop_loss_forces_sell_even_on_hold(self):
        # entry 100, ATR 1, mult 2 -> stop at 98. price 97 -> stop hit.
        ctx = RiskContext(
            price=97.0, equity=10_000, peak_equity=10_000, atr=1.0,
            open_position=PositionState(entry_price=100.0, quantity=1.0),
        )
        d = apply_risk_guard(_hold(), ctx, RiskParams(stop_loss_atr_mult=2.0))
        assert d.action == "sell" and d.vetoed is True
        assert "stop-loss" in d.reason

    def test_take_profit_forces_sell_even_on_buy(self):
        # entry 100, ATR 1, tp mult 3 -> target 103. price 104 -> tp hit.
        ctx = RiskContext(
            price=104.0, equity=10_000, peak_equity=10_000, atr=1.0,
            open_position=PositionState(entry_price=100.0, quantity=1.0),
        )
        d = apply_risk_guard(_buy(), ctx, RiskParams(take_profit_atr_mult=3.0))
        assert d.action == "sell" and d.vetoed is True
        assert "take-profit" in d.reason

    def test_no_forced_exit_inside_band(self):
        # price between stop (98) and target (103) -> no forced exit
        ctx = RiskContext(
            price=101.0, equity=10_000, peak_equity=10_000, atr=1.0,
            open_position=PositionState(entry_price=100.0, quantity=1.0),
        )
        d = apply_risk_guard(_hold(), ctx, RiskParams())
        assert d.action == "hold"


# ── Sell / hold pass-through ──────────────────────────────────────────────────
class TestPassThrough:
    def test_sell_passes_through(self):
        ctx = RiskContext(price=100, equity=10_000, peak_equity=10_000)
        d = apply_risk_guard(_sell(), ctx)
        assert d.action == "sell" and d.vetoed is False

    def test_hold_passes_through(self):
        ctx = RiskContext(price=100, equity=10_000, peak_equity=10_000)
        d = apply_risk_guard(_hold(), ctx)
        assert d.action == "hold" and d.vetoed is False


# ── Drawdown breaker ──────────────────────────────────────────────────────────
class TestDrawdownBreaker:
    def test_buy_blocked_when_drawdown_exceeded(self):
        # equity 7900 vs peak 10000 -> 21% DD > 20% limit
        ctx = RiskContext(price=100, equity=7_900, peak_equity=10_000, atr=1.0)
        d = apply_risk_guard(_buy(), ctx, RiskParams(max_drawdown_pct=0.20))
        assert d.action == "hold" and d.vetoed is True
        assert "drawdown" in d.reason

    def test_buy_allowed_just_under_limit(self):
        ctx = RiskContext(price=100, equity=8_100, peak_equity=10_000, atr=1.0)
        d = apply_risk_guard(_buy(), ctx, RiskParams(max_drawdown_pct=0.20))
        assert d.action == "buy"


# ── Volatility sizing ─────────────────────────────────────────────────────────
class TestSizing:
    def test_size_risks_fixed_fraction(self):
        # equity 10k, risk 1% -> risk budget 100. ATR 1, mult 2 -> stop dist 2,
        # price 100 -> notional = 100 * 100 / 2 = 5000. Capped by max_position_pct
        # 0.25 -> 2500.
        ctx = RiskContext(price=100, equity=10_000, peak_equity=10_000, atr=1.0)
        p = RiskParams(risk_per_trade_pct=0.01, stop_loss_atr_mult=2.0,
                       max_position_pct=0.25, max_total_exposure_pct=1.0)
        d = apply_risk_guard(_buy(), ctx, p)
        assert d.action == "buy"
        assert d.quantity_usdt == pytest.approx(2500.0)
        assert d.stop_loss == pytest.approx(98.0)
        assert d.take_profit == pytest.approx(103.0)

    def test_wider_stop_gives_smaller_size(self):
        ctx_tight = RiskContext(price=100, equity=10_000, peak_equity=10_000, atr=0.5)
        ctx_wide = RiskContext(price=100, equity=10_000, peak_equity=10_000, atr=5.0)
        p = RiskParams(risk_per_trade_pct=0.01, stop_loss_atr_mult=2.0,
                       max_position_pct=1.0, max_total_exposure_pct=1.0)
        d_tight = apply_risk_guard(_buy(), ctx_tight, p)
        d_wide = apply_risk_guard(_buy(), ctx_wide, p)
        assert d_wide.quantity_usdt < d_tight.quantity_usdt

    def test_exposure_cap_reduces_size(self):
        # exposure budget = 10k*0.6 = 6000, already 5500 open -> only 500 left
        ctx = RiskContext(price=100, equity=10_000, peak_equity=10_000, atr=1.0,
                          total_open_notional=5_500)
        p = RiskParams(max_total_exposure_pct=0.60, max_position_pct=1.0,
                       min_position_usdt=10.0)
        d = apply_risk_guard(_buy(), ctx, p)
        assert d.action == "buy"
        assert d.quantity_usdt == pytest.approx(500.0)

    def test_exposure_cap_full_vetoes(self):
        ctx = RiskContext(price=100, equity=10_000, peak_equity=10_000, atr=1.0,
                          total_open_notional=6_000)
        p = RiskParams(max_total_exposure_pct=0.60)
        d = apply_risk_guard(_buy(), ctx, p)
        assert d.action == "hold" and d.vetoed is True
        assert "exposure" in d.reason

    def test_below_minimum_vetoes(self):
        # remaining exposure of 5 < min_position_usdt 10
        ctx = RiskContext(price=100, equity=10_000, peak_equity=10_000, atr=1.0,
                          total_open_notional=5_995)
        p = RiskParams(max_total_exposure_pct=0.60, min_position_usdt=10.0)
        d = apply_risk_guard(_buy(), ctx, p)
        assert d.action == "hold" and d.vetoed is True
        assert "minimum" in d.reason

    def test_nonpositive_equity_vetoes(self):
        ctx = RiskContext(price=100, equity=0.0, peak_equity=10_000, atr=1.0)
        d = apply_risk_guard(_buy(), ctx, RiskParams())
        assert d.action == "hold" and d.vetoed is True

    def test_sizing_without_atr_uses_fallback(self):
        ctx = RiskContext(price=100, equity=10_000, peak_equity=10_000, atr=None)
        p = RiskParams(risk_per_trade_pct=0.01, stop_loss_pct_fallback=0.02,
                       max_position_pct=1.0, max_total_exposure_pct=1.0)
        d = apply_risk_guard(_buy(), ctx, p)
        # stop dist = 100*0.02 = 2 -> notional = 100*100/2 = 5000
        assert d.quantity_usdt == pytest.approx(5000.0)


# ── ATR ───────────────────────────────────────────────────────────────────────
class TestComputeATR:
    def test_none_when_insufficient_bars(self):
        assert compute_atr([1, 2], [1, 2], [1, 2], period=14) is None

    def test_constant_range_gives_that_range(self):
        # every bar has high-low = 2, no gaps -> ATR = 2
        highs = [11.0] * 20
        lows = [9.0] * 20
        closes = [10.0] * 20
        assert compute_atr(highs, lows, closes, period=14) == pytest.approx(2.0)

    def test_mismatched_lengths_return_none(self):
        assert compute_atr([1, 2, 3], [1, 2], [1, 2, 3], period=1) is None

    def test_includes_gap_in_true_range(self):
        # close jumps create true range via |high - prev_close|
        highs = [10, 20, 20]
        lows = [9, 19, 19]
        closes = [10, 19, 19]
        # i=1: max(20-19, |20-10|, |19-10|) = 10 ; i=2: max(1, |20-19|, |19-19|)=1
        assert compute_atr(highs, lows, closes, period=2) == pytest.approx((10 + 1) / 2)


# ── Serialisation ─────────────────────────────────────────────────────────────
def test_decision_to_dict_roundtrip():
    d = RiskDecision(action="buy", quantity_usdt=123.456, reason="x",
                     stop_loss=98.0, take_profit=103.0, vetoed=False)
    out = d.to_dict()
    assert out["action"] == "buy"
    assert out["quantity_usdt"] == 123.456
    assert out["stop_loss"] == 98.0
    assert out["vetoed"] is False
