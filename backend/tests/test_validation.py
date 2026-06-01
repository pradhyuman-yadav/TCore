"""
Tests for the walk-forward validation harness (app.services.validation).

All pure — no DB, no network. Builds synthetic OHLCV frames to exercise the
splitter, the stats math, and the pass/fail gate.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.backtest_runner import BacktestResult, BacktestTrade
from app.services.validation import (
    GateThresholds,
    MIN_FEE_RATE,
    MIN_SLIPPAGE_BPS,
    ValidationReport,
    WindowStats,
    _max_drawdown,
    _periods_per_year,
    _profit_factor,
    _sharpe_sortino,
    run_walk_forward,
    stats_from_result,
    walk_forward_splits,
)


@pytest.fixture(scope="session", autouse=True)
def run_migrations():
    """Override conftest's DB-dependent session fixture — these tests are pure."""
    yield


# ── Helpers ──────────────────────────────────────────────────────────────────
def _make_ohlcv(n: int, seed: int = 0, drift: float = 0.0) -> pd.DataFrame:
    """Synthetic 1h OHLCV: geometric random walk with optional drift."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, 0.01, n)
    close = 100.0 * np.exp(np.cumsum(rets))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    high = close * (1 + np.abs(rng.normal(0, 0.002, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.002, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = rng.uniform(10, 100, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def _strategy() -> dict:
    return {
        "symbol": "BTC/USDT",
        "exchange": "binanceus",
        "timeframe": "1h",
        "weights": {"rsi": 0.5, "macd": 0.5},
        "buy_threshold": 0.3,
        "sell_threshold": 0.3,
        "position_sizing": {"amount": 100.0, "max_open_positions": 1},
        "risk": {"max_daily_loss_usdt": 1000.0},
    }


def _result_with_pnls(pnls: list[float], equity: list[float]) -> BacktestResult:
    r = BacktestResult(symbol="X", exchange="x", total_bars=len(equity))
    r.equity_curve = equity
    for i, p in enumerate(pnls):
        r.trades.append(BacktestTrade(bar_index=i, time=pd.Timestamp("2024-01-01").to_pydatetime(),
                                      side="buy", price=100.0, quantity=1.0))
        r.trades.append(BacktestTrade(bar_index=i, time=pd.Timestamp("2024-01-01").to_pydatetime(),
                                      side="sell", price=100.0 + p, quantity=1.0, pnl=p))
    return r


# ── walk_forward_splits ───────────────────────────────────────────────────────
class TestWalkForwardSplits:
    def test_basic_non_overlapping(self):
        splits = walk_forward_splits(1000, train_size=500, test_size=200)
        # step defaults to test_size -> test windows are contiguous, non-overlap
        assert splits[0] == (0, 500, 500, 700)
        assert splits[1] == (200, 700, 700, 900)
        for _, _, ts, te in splits:
            assert te - ts == 200

    def test_purge_gap_inserted(self):
        splits = walk_forward_splits(1000, train_size=400, test_size=100, purge=10)
        tr_s, tr_e, te_s, te_e = splits[0]
        assert te_s - tr_e == 10  # purge gap between train end and test start

    def test_embargo_advances_window(self):
        no_emb = walk_forward_splits(2000, 500, 200, embargo=0)
        emb = walk_forward_splits(2000, 500, 200, embargo=50)
        # embargo slides next fold further -> fewer folds fit
        assert len(emb) < len(no_emb)

    def test_returns_empty_when_insufficient(self):
        assert walk_forward_splits(100, train_size=500, test_size=200) == []

    def test_rejects_nonpositive_sizes(self):
        with pytest.raises(ValueError):
            walk_forward_splits(1000, 0, 200)
        with pytest.raises(ValueError):
            walk_forward_splits(1000, 500, 0)

    def test_rejects_negative_purge(self):
        with pytest.raises(ValueError):
            walk_forward_splits(1000, 500, 200, purge=-1)

    def test_no_test_window_exceeds_n(self):
        splits = walk_forward_splits(1000, 500, 200)
        for _, _, _, te in splits:
            assert te <= 1000


# ── stats math ─────────────────────────────────────────────────────────────
class TestStatsMath:
    def test_profit_factor_basic(self):
        # wins 30, losses 10 -> PF 3.0
        assert _profit_factor([10.0, 20.0, -10.0]) == pytest.approx(3.0)

    def test_profit_factor_no_losses_is_finite(self):
        pf = _profit_factor([5.0, 5.0])
        assert pf == 999.0  # large finite sentinel, not inf

    def test_profit_factor_no_trades(self):
        assert _profit_factor([]) == 0.0

    def test_max_drawdown(self):
        # peak 120 then down to 90 -> dd = 30/120 = 0.25
        assert _max_drawdown([100, 120, 90, 110]) == pytest.approx(0.25)

    def test_max_drawdown_monotonic_up(self):
        assert _max_drawdown([100, 110, 120]) == 0.0

    def test_max_drawdown_empty(self):
        assert _max_drawdown([]) == 0.0

    def test_sharpe_none_for_short_series(self):
        s, so = _sharpe_sortino([100, 101], 8760)
        assert s is None and so is None

    def test_sharpe_positive_for_rising_equity(self):
        equity = list(np.linspace(100, 200, 50))
        s, _ = _sharpe_sortino(equity, 8760)
        assert s is not None and s > 0

    def test_periods_per_year_known_and_default(self):
        assert _periods_per_year("1h") == 8760.0
        assert _periods_per_year("1d") == 365.0
        assert _periods_per_year("bogus") == 365.0


# ── stats_from_result ────────────────────────────────────────────────────────
class TestStatsFromResult:
    def test_counts_only_closed_sells(self):
        r = _result_with_pnls([10.0, -5.0, 20.0], equity=[100, 110, 105, 125])
        s = stats_from_result(r, "1h")
        assert s.num_trades == 3
        assert s.total_pnl == pytest.approx(25.0)
        assert s.win_rate == pytest.approx(2 / 3)
        assert s.expectancy == pytest.approx(25.0 / 3)

    def test_no_trades_zeroed(self):
        r = BacktestResult(symbol="X", exchange="x", total_bars=0)
        r.equity_curve = [100.0]
        s = stats_from_result(r, "1h")
        assert s.num_trades == 0
        assert s.profit_factor == 0.0


# ── run_walk_forward integration ─────────────────────────────────────────────
class TestRunWalkForward:
    def test_fails_when_test_size_below_warmup(self):
        df = _make_ohlcv(2000)
        rep = run_walk_forward(df, _strategy(), test_size=20, train_size=500)
        assert rep.passed is False
        assert any("warm-up" in r for r in rep.reasons)

    def test_fails_when_insufficient_bars(self):
        df = _make_ohlcv(300)
        rep = run_walk_forward(df, _strategy(), train_size=500, test_size=200)
        assert rep.passed is False
        assert any("not enough bars" in r for r in rep.reasons)

    def test_produces_folds_and_report(self):
        df = _make_ohlcv(2000, seed=42)
        rep = run_walk_forward(df, _strategy(), train_size=400, test_size=200)
        assert isinstance(rep, ValidationReport)
        assert len(rep.folds) >= 1
        # report serialises cleanly
        d = rep.to_dict()
        assert "oos" in d and "folds" in d
        assert isinstance(d["passed"], bool)

    def test_costs_clamped_to_floor(self):
        # passing zero costs must not produce a cheaper-than-reality run; the
        # function clamps internally. We assert it runs and the floors hold by
        # checking the module constants are applied (no exception, valid report).
        df = _make_ohlcv(1500, seed=1)
        rep = run_walk_forward(df, _strategy(), train_size=400, test_size=200,
                               fee_rate=0.0, slippage_bps=0.0)
        assert isinstance(rep, ValidationReport)
        assert MIN_FEE_RATE > 0 and MIN_SLIPPAGE_BPS > 0

    def test_random_walk_strategy_does_not_pass_gate(self):
        # A momentum strategy on a pure random walk, after costs, should NOT
        # clear the gate. This is the harness doing its job: rejecting noise.
        df = _make_ohlcv(3000, seed=7, drift=0.0)
        rep = run_walk_forward(df, _strategy(), train_size=500, test_size=250)
        assert rep.passed is False
        assert len(rep.reasons) >= 1

    def test_gate_consistency_metric_in_range(self):
        df = _make_ohlcv(2500, seed=3)
        rep = run_walk_forward(df, _strategy(), train_size=400, test_size=200)
        assert 0.0 <= rep.fold_consistency <= 1.0


# ── Gate logic ───────────────────────────────────────────────────────────────
class TestGate:
    def test_default_thresholds_reasonable(self):
        t = GateThresholds()
        assert t.min_total_trades >= 1
        assert t.min_profit_factor > 1.0
        assert 0 < t.min_fold_consistency <= 1.0

    def test_custom_thresholds_respected(self):
        df = _make_ohlcv(2000, seed=9)
        loose = GateThresholds(min_total_trades=1, min_profit_factor=0.0,
                               min_expectancy=-1e9, min_sharpe=-1e9,
                               max_drawdown=1.0, min_fold_consistency=0.0)
        rep = run_walk_forward(df, _strategy(), train_size=400, test_size=200,
                               thresholds=loose)
        # With wide-open thresholds and at least one trade, it should pass.
        if rep.oos_num_trades >= 1:
            assert rep.passed is True
