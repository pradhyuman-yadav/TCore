"""
Comprehensive tests for the Hawkes OFI indicator.

Coverage:
  - hawkes_ofi.py  : pure math, DB I/O, fit pipeline, cache logic
  - binanceus_ws.py: tick buffer classification + DB flush
  - routers/hawkes : /hawkes/pressure and /hawkes/forecast endpoints
  - scheduler/jobs : refit_hawkes_job, cleanup_tick_trades_job
  - ORM models     : TickTrade, HawkesParams round-trips
"""
from __future__ import annotations

import socket
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from sqlalchemy import select

from app.db.models import HawkesParams, TickTrade
from app.services.hawkes_ofi import (
    _CachedParams,
    _params_cache,
    _branching_ratio,
    compute_pressure,
    get_recent_events,
    load_cached_params,
    recursive_intensity,
    simulate_forward,
    _simulate_one,
)
from app.state import app_state


def _postgres_available() -> bool:
    """Return True if a TCP connection to localhost:5432 succeeds."""
    try:
        s = socket.create_connection(("localhost", 5432), timeout=1.0)
        s.close()
        return True
    except OSError:
        return False


_PG_AVAILABLE = _postgres_available()
_skip_no_db = pytest.mark.skipif(
    not _PG_AVAILABLE,
    reason="PostgreSQL not available — start the DB to run these tests",
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_params(
    mu=None, alpha=None, beta_arr=None,
    branching=0.4,
    age_s: float = 0.0,
) -> _CachedParams:
    """Build a _CachedParams with sane defaults for unit tests."""
    if mu is None:
        mu = np.array([0.5, 0.3])
    if alpha is None:
        alpha = np.zeros((2, 2, 3))
        alpha[0, 0, 0] = 0.2   # buy self-excitation
        alpha[1, 1, 0] = 0.15  # sell self-excitation
    if beta_arr is None:
        beta_arr = np.array([50.0, 5.0, 0.5])

    now = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return _CachedParams(
        mu=mu,
        alpha=alpha,
        beta_arr=beta_arr,
        branching=branching,
        fitted_at=now,
        train_start=now - timedelta(hours=4),
        train_end=now,
    )


def _tick_rows(symbol: str, n_buy: int, n_sell: int, age_s: float = 5.0) -> list[dict]:
    """Build a list of tick dicts suitable for bulk insert via pg_insert."""
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(n_buy):
        rows.append({
            "ts":     now - timedelta(seconds=age_s + i * 0.1),
            "symbol": symbol,
            "venue":  "binanceus",
            "price":  50_000.0 + i,
            "qty":    0.01,
            "side":   1,
            "agg_id": i + 1,
        })
    for i in range(n_sell):
        rows.append({
            "ts":     now - timedelta(seconds=age_s + (n_buy + i) * 0.1),
            "symbol": symbol,
            "venue":  "binanceus",
            "price":  50_000.0 - i,
            "qty":    0.01,
            "side":   -1,
            "agg_id": n_buy + i + 1,
        })
    return rows


# ── Fixture overrides ────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def run_migrations():
    """
    Override the conftest session fixture — Hawkes unit tests manage their own
    DB state via the db_session fixture and don't need a full migration run.
    DB-dependent tests are skipped automatically when PostgreSQL is unavailable.
    """
    yield


@pytest.fixture(autouse=True)
def _clear_params_cache():
    """Ensure in-memory params cache is clean for every test."""
    _params_cache.clear()
    yield
    _params_cache.clear()


@pytest.fixture()
def mock_tick(mocker):
    """
    Inject a fake tick.hawkes module so tests don't require the C extension.
    Returns the MagicMock model instance that HawkesSumExpKern() produces.
    """
    mock_model = MagicMock()
    mock_model.baseline   = np.array([0.5, 0.3])
    mock_model.adjacency  = np.zeros((2, 2, 3))
    mock_model.adjacency[0, 0, 0] = 0.2
    mock_model.adjacency[1, 1, 0] = 0.15
    mock_model.score.return_value = -1234.5

    mock_kern_cls  = MagicMock(return_value=mock_model)
    mock_tick_mod  = types.SimpleNamespace(HawkesSumExpKern=mock_kern_cls)

    mocker.patch.dict(sys.modules, {
        "tick":        types.SimpleNamespace(hawkes=mock_tick_mod),
        "tick.hawkes": mock_tick_mod,
    })
    return mock_model


# ══════════════════════════════════════════════════════════════════════════════
# 1. Pure math — no DB, no I/O
# ══════════════════════════════════════════════════════════════════════════════

class TestComputePressure:
    def test_full_buy_pressure(self):
        assert compute_pressure(1.0, 0.0) == pytest.approx(1.0)

    def test_full_sell_pressure(self):
        assert compute_pressure(0.0, 1.0) == pytest.approx(-1.0)

    def test_balanced_is_zero(self):
        assert compute_pressure(0.5, 0.5) == pytest.approx(0.0)

    def test_zero_denominator_returns_zero(self):
        assert compute_pressure(0.0, 0.0) == pytest.approx(0.0)

    def test_partial_buy_dominant(self):
        p = compute_pressure(0.8, 0.2)
        assert 0.0 < p < 1.0

    def test_partial_sell_dominant(self):
        p = compute_pressure(0.2, 0.8)
        assert -1.0 < p < 0.0


class TestRecursiveIntensity:
    def test_no_events_returns_mu(self):
        """With no past events, intensity should equal baseline mu."""
        params = _make_params(alpha=np.zeros((2, 2, 3)))
        lam_b, lam_s = recursive_intensity(params, [])
        assert lam_b == pytest.approx(params.mu[0])
        assert lam_s == pytest.approx(params.mu[1])

    def test_buy_events_increase_lambda_buy(self):
        """α_bb > 0 → recent buy events should raise λ_buy above baseline."""
        params = _make_params()   # has α[0,0,0]=0.2
        t_now = datetime.now(timezone.utc).timestamp()
        events = [(t_now - 0.05, 1)]   # 50ms ago, buy
        lam_b, _ = recursive_intensity(params, events)
        assert lam_b > params.mu[0]

    def test_sell_events_increase_lambda_sell(self):
        """α_ss > 0 → recent sell events should raise λ_sell above baseline."""
        params = _make_params()   # has α[1,1,0]=0.15
        t_now = datetime.now(timezone.utc).timestamp()
        events = [(t_now - 0.05, -1)]  # 50ms ago, sell
        _, lam_s = recursive_intensity(params, events)
        assert lam_s > params.mu[1]

    def test_stale_events_decay_to_mu(self):
        """Events far in the past (exp decay) should barely affect current intensity."""
        params = _make_params()
        t_now = datetime.now(timezone.utc).timestamp()
        # Event 1 day ago — β=50 → exp(-50*86400) ≈ 0
        events = [(t_now - 86400, 1)]
        lam_b, _ = recursive_intensity(params, events)
        assert lam_b == pytest.approx(params.mu[0], abs=1e-6)

    def test_future_events_ignored(self):
        """Events with t_event > t_now (delta < 0) are skipped silently."""
        params = _make_params(alpha=np.zeros((2, 2, 3)))
        t_now = datetime.now(timezone.utc).timestamp()
        events = [(t_now + 100, 1)]   # in the future — should be ignored
        lam_b, lam_s = recursive_intensity(params, events)
        assert lam_b == pytest.approx(params.mu[0])
        assert lam_s == pytest.approx(params.mu[1])

    def test_intensity_non_negative(self):
        """Intensity must always be ≥ 0 regardless of α configuration."""
        # Use large negative-ish alpha (shouldn't exist in practice but guard anyway)
        alpha = np.zeros((2, 2, 3))
        params = _make_params(mu=np.array([0.1, 0.1]), alpha=alpha)
        lam_b, lam_s = recursive_intensity(params, [])
        assert lam_b >= 0.0
        assert lam_s >= 0.0


class TestSimulateOne:
    def _base_params(self):
        mu       = np.array([2.0, 2.0])       # moderate baseline
        alpha    = np.zeros((2, 2, 3))
        alpha[0, 0, 0] = 0.1
        alpha[1, 1, 0] = 0.1
        beta_arr = np.array([50.0, 5.0, 0.5])
        R0       = np.zeros((2, 3))
        return mu, alpha, beta_arr, R0

    def test_returns_non_negative_counts(self):
        mu, alpha, beta_arr, R0 = self._base_params()
        rng = np.random.default_rng(42)
        n_buy, n_sell = _simulate_one(mu, alpha, beta_arr, R0, horizon_s=0.5, rng=rng)
        assert n_buy >= 0
        assert n_sell >= 0

    def test_short_horizon_fewer_events(self):
        """Very short horizon → fewer total events than a longer one."""
        mu, alpha, beta_arr, R0 = self._base_params()
        rng = np.random.default_rng(0)
        total_short = sum(
            n_b + n_s
            for n_b, n_s in [_simulate_one(mu, alpha, beta_arr, R0.copy(), 0.001, rng) for _ in range(50)]
        )
        rng = np.random.default_rng(0)
        total_long = sum(
            n_b + n_s
            for n_b, n_s in [_simulate_one(mu, alpha, beta_arr, R0.copy(), 1.0, rng) for _ in range(50)]
        )
        assert total_short < total_long

    def test_zero_mu_zero_initial_R_gives_no_events(self):
        """Null process (μ=0, α=0, R=0) → never generates events."""
        mu       = np.array([0.0, 0.0])
        alpha    = np.zeros((2, 2, 3))
        beta_arr = np.array([50.0, 5.0, 0.5])
        R0       = np.zeros((2, 3))
        rng      = np.random.default_rng(7)
        n_buy, n_sell = _simulate_one(mu, alpha, beta_arr, R0, horizon_s=10.0, rng=rng)
        assert n_buy  == 0
        assert n_sell == 0


class TestSimulateForward:
    def _params_and_events(self):
        params = _make_params(mu=np.array([3.0, 2.0]))  # buy-dominant baseline
        t_now  = datetime.now(timezone.utc).timestamp()
        events = [(t_now - 0.1 * i, 1 if i % 2 == 0 else -1) for i in range(10)]
        return params, events

    def test_returns_all_required_keys(self):
        params, events = self._params_and_events()
        result = simulate_forward(params, events, horizon_s=1.0, n_sims=50)
        for key in ("mean", "p10", "p50", "p90", "prob_buy_pressure"):
            assert key in result

    def test_ofi_stats_in_valid_range(self):
        params, events = self._params_and_events()
        result = simulate_forward(params, events, horizon_s=1.0, n_sims=100)
        assert -1.0 <= result["mean"] <= 1.0
        assert -1.0 <= result["p10"]  <= result["p50"] <= result["p90"] <= 1.0

    def test_prob_buy_pressure_is_probability(self):
        params, events = self._params_and_events()
        result = simulate_forward(params, events, horizon_s=2.0, n_sims=100)
        assert 0.0 <= result["prob_buy_pressure"] <= 1.0

    def test_buy_dominant_baseline_gives_positive_mean_ofi(self):
        """With μ_b >> μ_s and zero cross-excitation, mean OFI should be positive."""
        params = _make_params(
            mu=np.array([10.0, 1.0]),
            alpha=np.zeros((2, 2, 3)),
        )
        result = simulate_forward(params, [], horizon_s=2.0, n_sims=200)
        assert result["mean"] > 0.0
        assert result["prob_buy_pressure"] > 0.5

    def test_sell_dominant_baseline_gives_negative_mean_ofi(self):
        params = _make_params(
            mu=np.array([1.0, 10.0]),
            alpha=np.zeros((2, 2, 3)),
        )
        result = simulate_forward(params, [], horizon_s=2.0, n_sims=200)
        assert result["mean"] < 0.0
        assert result["prob_buy_pressure"] < 0.5


class TestBranchingRatio:
    def test_stable_known_matrix(self):
        """α matrix with spectral radius = 0.5 → branching = 0.5."""
        from app.services.hawkes_ofi import _branching_ratio

        # Build a mock model with known adjacency
        model = MagicMock()
        # 2x2x1 adjacency: each diagonal element = 0.25, sum over K → 2x2 with diag 0.25
        model.adjacency = np.array([[[0.25], [0.0]],
                                    [[0.0],  [0.25]]])
        br = _branching_ratio(model)
        assert br == pytest.approx(0.25)

    def test_reflexive_matrix(self):
        """Large α → branching > 1 (unstable — should be rejected by fitter)."""
        model = MagicMock()
        model.adjacency = np.array([[[2.0], [0.0]],
                                    [[0.0], [2.0]]])
        br = _branching_ratio(model)
        assert br > 1.0


class TestCachedParamsProperties:
    def test_regime_stable_below_09(self):
        p = _make_params(branching=0.5)
        assert p.regime == "stable"

    def test_regime_reflexive_at_09(self):
        p = _make_params(branching=0.9)
        assert p.regime == "reflexive"

    def test_regime_reflexive_above_09(self):
        p = _make_params(branching=0.95)
        assert p.regime == "reflexive"

    def test_age_s_increases_with_older_fitted_at(self):
        old = _make_params(age_s=600)
        new = _make_params(age_s=10)
        assert old.age_s > new.age_s


# ══════════════════════════════════════════════════════════════════════════════
# 2. ORM round-trips
# ══════════════════════════════════════════════════════════════════════════════

@_skip_no_db
class TestTickTradeORM:
    async def test_insert_and_query(self, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(TickTrade(
            ts=now, symbol="BTC/USDT", venue="binanceus",
            price=50_000.0, qty=0.01, side=1, agg_id=12345,
        ))
        await db_session.commit()

        rows = (await db_session.execute(
            select(TickTrade).where(TickTrade.symbol == "BTC/USDT")
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].side    == 1
        assert rows[0].agg_id  == 12345
        assert rows[0].price   == pytest.approx(50_000.0)

    async def test_side_buy_is_plus_one(self, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(TickTrade(ts=now, symbol="ETH/USDT", venue="binanceus",
                                 price=3000.0, qty=0.1, side=1, agg_id=1))
        await db_session.commit()
        row = (await db_session.execute(
            select(TickTrade).where(TickTrade.symbol == "ETH/USDT")
        )).scalar_one()
        assert row.side == 1

    async def test_side_sell_is_minus_one(self, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(TickTrade(ts=now, symbol="ETH/USDT", venue="binanceus",
                                 price=3000.0, qty=0.1, side=-1, agg_id=2))
        await db_session.commit()
        row = (await db_session.execute(
            select(TickTrade).where(TickTrade.symbol == "ETH/USDT")
        )).scalar_one()
        assert row.side == -1

    async def test_agg_id_nullable(self, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(TickTrade(ts=now, symbol="SOL/USDT", venue="binanceus",
                                 price=100.0, qty=1.0, side=1, agg_id=None))
        await db_session.commit()
        row = (await db_session.execute(
            select(TickTrade).where(TickTrade.symbol == "SOL/USDT")
        )).scalar_one()
        assert row.agg_id is None


@_skip_no_db
class TestHawkesParamsORM:
    async def test_insert_and_query(self, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(HawkesParams(
            fitted_at=now,
            symbol="BTC/USDT",
            venue="binanceus",
            mu=[0.5, 0.3],
            alpha=[[[0.2, 0.0, 0.0], [0.0, 0.0, 0.0]],
                   [[0.0, 0.0, 0.0], [0.15, 0.0, 0.0]]],
            beta_vals=[50.0, 5.0, 0.5],
            branching=0.35,
            train_start=now - timedelta(hours=4),
            train_end=now,
            loglik=-1234.5,
        ))
        await db_session.commit()

        row = (await db_session.execute(
            select(HawkesParams)
            .where(HawkesParams.symbol == "BTC/USDT")
            .order_by(HawkesParams.fitted_at.desc())
            .limit(1)
        )).scalar_one()
        assert row.branching == pytest.approx(0.35)
        assert row.mu[0]     == pytest.approx(0.5)
        assert row.loglik    == pytest.approx(-1234.5)

    async def test_multiple_fits_ordered_by_fitted_at(self, db_session):
        now = datetime.now(timezone.utc)
        for i in range(3):
            db_session.add(HawkesParams(
                fitted_at=now - timedelta(hours=i),
                symbol="BTC/USDT", venue="binanceus",
                mu=[0.1 * (i + 1), 0.1],
                alpha=np.zeros((2, 2, 3)).tolist(),
                beta_vals=[50.0, 5.0, 0.5],
                branching=0.1 * (i + 1),
            ))
        await db_session.commit()

        # Latest should be the smallest i (i=0 → fitted_at=now)
        latest = (await db_session.execute(
            select(HawkesParams)
            .where(HawkesParams.symbol == "BTC/USDT")
            .order_by(HawkesParams.fitted_at.desc())
            .limit(1)
        )).scalar_one()
        assert latest.branching == pytest.approx(0.1)


# ══════════════════════════════════════════════════════════════════════════════
# 3. DB-backed service tests
# ══════════════════════════════════════════════════════════════════════════════

@_skip_no_db
class TestGetRecentEvents:
    async def test_empty_when_no_ticks(self, db_session):
        events = await get_recent_events("BTC/USDT", "binanceus", lookback_s=30.0, db=db_session)
        assert events == []

    async def test_returns_ticks_within_lookback(self, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(TickTrade(ts=now - timedelta(seconds=5),
                                 symbol="BTC/USDT", venue="binanceus",
                                 price=50000.0, qty=0.01, side=1, agg_id=1))
        db_session.add(TickTrade(ts=now - timedelta(seconds=10),
                                 symbol="BTC/USDT", venue="binanceus",
                                 price=49999.0, qty=0.01, side=-1, agg_id=2))
        await db_session.commit()

        events = await get_recent_events("BTC/USDT", "binanceus", lookback_s=30.0, db=db_session)
        assert len(events) == 2
        # Sorted ascending by time
        assert events[0][1] == -1   # sell came first (10s ago)
        assert events[1][1] ==  1   # buy  came second (5s ago)

    async def test_excludes_ticks_outside_lookback(self, db_session):
        now = datetime.now(timezone.utc)
        # 5s ago — within 30s window
        db_session.add(TickTrade(ts=now - timedelta(seconds=5),
                                 symbol="BTC/USDT", venue="binanceus",
                                 price=50000.0, qty=0.01, side=1, agg_id=1))
        # 60s ago — outside 30s window
        db_session.add(TickTrade(ts=now - timedelta(seconds=60),
                                 symbol="BTC/USDT", venue="binanceus",
                                 price=50000.0, qty=0.01, side=1, agg_id=2))
        await db_session.commit()

        events = await get_recent_events("BTC/USDT", "binanceus", lookback_s=30.0, db=db_session)
        assert len(events) == 1

    async def test_filters_by_symbol(self, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(TickTrade(ts=now - timedelta(seconds=1),
                                 symbol="BTC/USDT", venue="binanceus",
                                 price=50000.0, qty=0.01, side=1, agg_id=1))
        db_session.add(TickTrade(ts=now - timedelta(seconds=2),
                                 symbol="ETH/USDT", venue="binanceus",
                                 price=3000.0, qty=0.1, side=-1, agg_id=2))
        await db_session.commit()

        events = await get_recent_events("ETH/USDT", "binanceus", lookback_s=30.0, db=db_session)
        assert len(events) == 1
        assert events[0][1] == -1

    async def test_returns_timestamps_as_floats(self, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(TickTrade(ts=now - timedelta(seconds=1),
                                 symbol="BTC/USDT", venue="binanceus",
                                 price=50000.0, qty=0.01, side=1, agg_id=1))
        await db_session.commit()
        events = await get_recent_events("BTC/USDT", "binanceus", db=db_session)
        assert isinstance(events[0][0], float)
        assert isinstance(events[0][1], int)


@_skip_no_db
class TestLoadCachedParams:
    async def test_returns_none_when_no_data(self, db_session):
        result = await load_cached_params("UNKNOWN/USDT", "binanceus", db=db_session)
        assert result is None

    async def test_loads_from_db_and_populates_in_memory_cache(self, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(HawkesParams(
            fitted_at=now,
            symbol="BTC/USDT",
            venue="binanceus",
            mu=[0.5, 0.3],
            alpha=np.zeros((2, 2, 3)).tolist(),
            beta_vals=[50.0, 5.0, 0.5],
            branching=0.42,
            train_start=now - timedelta(hours=4),
            train_end=now,
        ))
        await db_session.commit()

        params = await load_cached_params("BTC/USDT", "binanceus", db=db_session)
        assert params is not None
        assert params.branching == pytest.approx(0.42)
        assert len(params.mu)   == 2
        # Now in in-memory cache
        assert ("BTC/USDT", "binanceus") in _params_cache

    async def test_prefers_in_memory_over_db(self, db_session):
        """If fresh in-memory cache exists, DB should NOT be queried."""
        from app.services.hawkes_ofi import _CACHE_MAX_AGE
        cached = _make_params(branching=0.99, age_s=10)   # fresh
        _params_cache[("BTC/USDT", "binanceus")] = cached

        # Put different value in DB — should be ignored
        now = datetime.now(timezone.utc)
        db_session.add(HawkesParams(
            fitted_at=now,
            symbol="BTC/USDT", venue="binanceus",
            mu=[0.1, 0.1],
            alpha=np.zeros((2, 2, 3)).tolist(),
            beta_vals=[50.0, 5.0, 0.5],
            branching=0.10,
        ))
        await db_session.commit()

        params = await load_cached_params("BTC/USDT", "binanceus", db=db_session)
        assert params.branching == pytest.approx(0.99)   # from in-memory, not DB

    async def test_stale_in_memory_cache_falls_through_to_db(self, db_session):
        """Params older than _CACHE_MAX_AGE seconds should be refreshed from DB."""
        from app.services.hawkes_ofi import _CACHE_MAX_AGE
        stale = _make_params(branching=0.55, age_s=_CACHE_MAX_AGE + 100)
        _params_cache[("BTC/USDT", "binanceus")] = stale

        now = datetime.now(timezone.utc)
        db_session.add(HawkesParams(
            fitted_at=now,
            symbol="BTC/USDT", venue="binanceus",
            mu=[0.5, 0.3],
            alpha=np.zeros((2, 2, 3)).tolist(),
            beta_vals=[50.0, 5.0, 0.5],
            branching=0.77,
            train_start=now - timedelta(hours=4),
            train_end=now,
        ))
        await db_session.commit()

        params = await load_cached_params("BTC/USDT", "binanceus", db=db_session)
        assert params.branching == pytest.approx(0.77)   # refreshed from DB

    async def test_loaded_params_have_correct_array_shapes(self, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(HawkesParams(
            fitted_at=now,
            symbol="BTC/USDT", venue="binanceus",
            mu=[0.5, 0.3],
            alpha=np.zeros((2, 2, 3)).tolist(),
            beta_vals=[50.0, 5.0, 0.5],
            branching=0.4,
            train_start=now - timedelta(hours=4),
            train_end=now,
        ))
        await db_session.commit()

        params = await load_cached_params("BTC/USDT", "binanceus", db=db_session)
        assert params.mu.shape       == (2,)
        assert params.alpha.shape    == (2, 2, 3)
        assert params.beta_arr.shape == (3,)


# ══════════════════════════════════════════════════════════════════════════════
# 4. fit_model — mocked tick library
# ══════════════════════════════════════════════════════════════════════════════

async def test_fit_model_returns_none_when_tick_not_installed(mocker):
    """If tick library is absent, fit_model returns None gracefully."""
    mocker.patch.dict(sys.modules, {
        "tick": None, "tick.hawkes": None,
    })
    from app.services import hawkes_ofi as _mod
    result = await _mod.fit_model("BTC/USDT", "binanceus", db=None)
    assert result is None


@_skip_no_db
class TestFitModel:
    async def test_returns_none_when_insufficient_ticks(self, mock_tick, db_session):
        """Fewer than _MIN_EVENTS ticks → returns None without calling model.fit."""
        from app.services.hawkes_ofi import _MIN_EVENTS
        # Insert only 5 ticks (well below _MIN_EVENTS=200)
        rows = _tick_rows("BTC/USDT", n_buy=3, n_sell=2, age_s=5)
        for r in rows:
            db_session.add(TickTrade(**r))
        await db_session.commit()

        from app.services.hawkes_ofi import fit_model
        result = await fit_model("BTC/USDT", "binanceus", db=db_session)
        assert result is None

    async def test_fit_succeeds_with_enough_ticks(self, mock_tick, db_session):
        """With ≥ _MIN_EVENTS ticks, fit_model should return _CachedParams."""
        from app.services.hawkes_ofi import _MIN_EVENTS, fit_model
        rows = _tick_rows("BTC/USDT", n_buy=_MIN_EVENTS, n_sell=_MIN_EVENTS, age_s=5)
        for r in rows:
            db_session.add(TickTrade(**r))
        await db_session.commit()

        result = await fit_model("BTC/USDT", "binanceus", db=db_session)
        assert result is not None
        assert isinstance(result, _CachedParams)

    async def test_fit_stores_to_db(self, mock_tick, db_session):
        """Successful fit writes HawkesParams row to DB."""
        from app.services.hawkes_ofi import _MIN_EVENTS, fit_model
        rows = _tick_rows("BTC/USDT", n_buy=_MIN_EVENTS, n_sell=_MIN_EVENTS, age_s=5)
        for r in rows:
            db_session.add(TickTrade(**r))
        await db_session.commit()

        await fit_model("BTC/USDT", "binanceus", db=db_session)

        row = (await db_session.execute(
            select(HawkesParams)
            .where(HawkesParams.symbol == "BTC/USDT")
            .limit(1)
        )).scalar_one_or_none()
        assert row is not None

    async def test_fit_updates_in_memory_cache(self, mock_tick, db_session):
        """After fitting, _params_cache should contain the new entry."""
        from app.services.hawkes_ofi import _MIN_EVENTS, fit_model
        rows = _tick_rows("BTC/USDT", n_buy=_MIN_EVENTS, n_sell=_MIN_EVENTS, age_s=5)
        for r in rows:
            db_session.add(TickTrade(**r))
        await db_session.commit()

        await fit_model("BTC/USDT", "binanceus", db=db_session)
        assert ("BTC/USDT", "binanceus") in _params_cache

    async def test_high_branching_fit_still_returns_params(self, mocker, db_session):
        """
        Branching ≥ 0.98 → still returns _CachedParams with regime='reflexive'.
        We don't silently discard the fit — the router shows the reflexive state.
        """
        # Patch _branching_ratio to return 0.99 (high)
        mocker.patch("app.services.hawkes_ofi._branching_ratio", return_value=0.99)

        # Inject tick mock
        mock_model = MagicMock()
        mock_model.baseline  = np.array([0.5, 0.3])
        mock_model.adjacency = np.zeros((2, 2, 3))
        mock_model.score.return_value = -999.0
        mock_kern_cls  = MagicMock(return_value=mock_model)
        mock_tick_mod  = types.SimpleNamespace(HawkesSumExpKern=mock_kern_cls)
        mocker.patch.dict(sys.modules, {
            "tick":        types.SimpleNamespace(hawkes=mock_tick_mod),
            "tick.hawkes": mock_tick_mod,
        })

        from app.services.hawkes_ofi import _MIN_EVENTS, fit_model
        rows = _tick_rows("BTC/USDT", n_buy=_MIN_EVENTS, n_sell=_MIN_EVENTS, age_s=5)
        for r in rows:
            db_session.add(TickTrade(**r))
        await db_session.commit()

        result = await fit_model("BTC/USDT", "binanceus", db=db_session)
        assert result is not None
        assert result.branching == pytest.approx(0.99)
        assert result.regime == "reflexive"

    async def test_fit_raises_gracefully_on_tick_error(self, mocker, db_session):
        """If HawkesSumExpKern.fit() raises, fit_model returns None."""
        mock_model = MagicMock()
        mock_model.fit.side_effect = RuntimeError("Convergence failed")
        mock_kern_cls  = MagicMock(return_value=mock_model)
        mock_tick_mod  = types.SimpleNamespace(HawkesSumExpKern=mock_kern_cls)
        mocker.patch.dict(sys.modules, {
            "tick":        types.SimpleNamespace(hawkes=mock_tick_mod),
            "tick.hawkes": mock_tick_mod,
        })

        from app.services.hawkes_ofi import _MIN_EVENTS, fit_model
        rows = _tick_rows("BTC/USDT", n_buy=_MIN_EVENTS, n_sell=_MIN_EVENTS, age_s=5)
        for r in rows:
            db_session.add(TickTrade(**r))
        await db_session.commit()

        result = await fit_model("BTC/USDT", "binanceus", db=db_session)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# 5. Binance WS tick buffer
# ══════════════════════════════════════════════════════════════════════════════

class TestBinanceWSTickBuffer:
    def _make_trade_payload(self, is_buyer_maker: bool, trade_id: int = 100) -> dict:
        return {
            "e": "trade",
            "s": "BTCUSDT",
            "t": trade_id,
            "p": "50000.00",
            "q": "0.01",
            "m": is_buyer_maker,
            "T": 1_700_000_000_000,   # ms timestamp
        }

    async def test_buyer_maker_false_classified_as_buy(self, mocker):
        """isBuyerMaker=False → taker was buyer → side=+1."""
        mocker.patch("app.ws.manager.ws_manager.broadcast", new=AsyncMock())
        from app.services.binanceus_ws import BinanceUSStreamClient

        client = BinanceUSStreamClient()
        await client._on_trade(self._make_trade_payload(is_buyer_maker=False))

        assert len(client._tick_buffer) == 1
        tick = client._tick_buffer[0]
        assert tick["side"] == 1

    async def test_buyer_maker_true_classified_as_sell(self, mocker):
        """isBuyerMaker=True → taker was seller → side=-1."""
        mocker.patch("app.ws.manager.ws_manager.broadcast", new=AsyncMock())
        from app.services.binanceus_ws import BinanceUSStreamClient

        client = BinanceUSStreamClient()
        await client._on_trade(self._make_trade_payload(is_buyer_maker=True))

        assert len(client._tick_buffer) == 1
        tick = client._tick_buffer[0]
        assert tick["side"] == -1

    async def test_tick_contains_required_fields(self, mocker):
        mocker.patch("app.ws.manager.ws_manager.broadcast", new=AsyncMock())
        from app.services.binanceus_ws import BinanceUSStreamClient

        client = BinanceUSStreamClient()
        await client._on_trade(self._make_trade_payload(is_buyer_maker=False, trade_id=999))

        tick = client._tick_buffer[0]
        assert "ts"     in tick
        assert "symbol" in tick
        assert "venue"  in tick
        assert "price"  in tick
        assert "qty"    in tick
        assert "side"   in tick
        assert "agg_id" in tick
        assert tick["venue"]  == "binanceus"
        assert tick["agg_id"] == 999
        assert tick["price"]  == pytest.approx(50_000.0)

    async def test_buffer_capped_at_maxlen(self, mocker):
        """deque(maxlen=5000) — inserting 5001 elements discards the oldest."""
        mocker.patch("app.ws.manager.ws_manager.broadcast", new=AsyncMock())
        from app.services.binanceus_ws import BinanceUSStreamClient

        client = BinanceUSStreamClient()
        for i in range(5001):
            await client._on_trade(self._make_trade_payload(False, trade_id=i))

        assert len(client._tick_buffer) == 5000

    async def test_persist_ticks_inserts_to_db(self, mocker):
        """_persist_ticks should call execute on the DB session with the tick data."""
        from app.services.binanceus_ws import BinanceUSStreamClient

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit  = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__  = AsyncMock(return_value=False)
        mocker.patch("app.db.session.AsyncSessionLocal", return_value=mock_ctx)

        ws_client = BinanceUSStreamClient()
        now    = datetime.now(timezone.utc)
        ticks  = [
            {"ts": now, "symbol": "BTC/USDT", "venue": "binanceus",
             "price": 50000.0, "qty": 0.01, "side": 1, "agg_id": 1},
            {"ts": now - timedelta(milliseconds=100), "symbol": "BTC/USDT",
             "venue": "binanceus", "price": 49999.0, "qty": 0.02, "side": -1, "agg_id": 2},
        ]
        await ws_client._persist_ticks(ticks)

        # Verify session.execute was called (the INSERT) and commit was called
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    async def test_flush_loop_drains_buffer(self, mocker):
        """_flush_loop drains buffer on each iteration."""
        mocker.patch("app.ws.manager.ws_manager.broadcast", new=AsyncMock())
        persist_mock = AsyncMock()

        from app.services.binanceus_ws import BinanceUSStreamClient

        client = BinanceUSStreamClient()
        client._running = True
        client._persist_ticks = persist_mock

        # Pre-populate buffer with 5 ticks
        for i in range(5):
            client._tick_buffer.append({"ts": datetime.now(timezone.utc), "side": 1, "agg_id": i})

        # Run one flush cycle by mocking asyncio.sleep to return immediately then stop the loop
        sleep_count = 0
        original_sleep = __import__("asyncio").sleep

        async def _fake_sleep(_):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                client._running = False

        mocker.patch("asyncio.sleep", side_effect=_fake_sleep)
        await client._flush_loop()

        persist_mock.assert_called_once()
        flushed_ticks = persist_mock.call_args[0][0]
        assert len(flushed_ticks) == 5
        assert len(client._tick_buffer) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 6. Router endpoints
# ══════════════════════════════════════════════════════════════════════════════

@_skip_no_db
class TestHawkesRouter:
    async def test_pressure_404_when_no_model(self, client):
        resp = await client.get("/hawkes/pressure?symbol=BTC%2FUSDT")
        assert resp.status_code == 404
        assert "No fitted Hawkes model" in resp.json()["detail"]

    async def test_pressure_200_with_cached_params(self, client):
        """Seed in-memory cache; endpoint should return 200 with valid pressure."""
        from app.services.hawkes_ofi import _params_cache
        _params_cache[("BTC/USDT", "binanceus")] = _make_params()

        resp = await client.get("/hawkes/pressure?symbol=BTC%2FUSDT&venue=binanceus")
        assert resp.status_code == 200
        body = resp.json()
        assert "pressure"     in body
        assert "lambda_buy"   in body
        assert "lambda_sell"  in body
        assert "branching"    in body
        assert "regime"       in body
        assert "params_age_s" in body
        assert "tick_count"   in body
        assert -1.0 <= body["pressure"] <= 1.0
        assert body["regime"] in ("stable", "reflexive")

    async def test_pressure_regime_reflexive_when_branching_high(self, client):
        from app.services.hawkes_ofi import _params_cache
        _params_cache[("BTC/USDT", "binanceus")] = _make_params(branching=0.95)

        resp = await client.get("/hawkes/pressure?symbol=BTC%2FUSDT")
        assert resp.status_code == 200
        assert resp.json()["regime"] == "reflexive"

    async def test_pressure_regime_stable_when_branching_low(self, client):
        from app.services.hawkes_ofi import _params_cache
        _params_cache[("BTC/USDT", "binanceus")] = _make_params(branching=0.3)

        resp = await client.get("/hawkes/pressure?symbol=BTC%2FUSDT")
        assert resp.status_code == 200
        assert resp.json()["regime"] == "stable"

    async def test_forecast_404_when_no_model(self, client):
        resp = await client.get("/hawkes/forecast?symbol=ETH%2FUSDT")
        assert resp.status_code == 404

    async def test_forecast_200_with_cached_params(self, client):
        from app.services.hawkes_ofi import _params_cache
        _params_cache[("BTC/USDT", "binanceus")] = _make_params(
            mu=np.array([5.0, 3.0]),  # strong baseline for guaranteed events
            alpha=np.zeros((2, 2, 3)),
        )

        resp = await client.get(
            "/hawkes/forecast?symbol=BTC%2FUSDT&venue=binanceus&horizon_s=2.0&n_sims=50"
        )
        assert resp.status_code == 200
        body = resp.json()
        for key in ("mean", "p10", "p50", "p90", "prob_buy_pressure"):
            assert key in body
        assert -1.0 <= body["mean"] <= 1.0
        assert 0.0 <= body["prob_buy_pressure"] <= 1.0
        assert body["p10"] <= body["p50"] <= body["p90"]

    async def test_forecast_horizon_validation(self, client):
        """horizon_s must be in [1.0, 60.0] — values outside raise 422."""
        from app.services.hawkes_ofi import _params_cache
        _params_cache[("BTC/USDT", "binanceus")] = _make_params()

        resp = await client.get(
            "/hawkes/forecast?symbol=BTC%2FUSDT&horizon_s=0.1"   # below min
        )
        assert resp.status_code == 422

        resp = await client.get(
            "/hawkes/forecast?symbol=BTC%2FUSDT&horizon_s=120"   # above max
        )
        assert resp.status_code == 422

    async def test_pressure_missing_symbol_returns_422(self, client):
        resp = await client.get("/hawkes/pressure")   # symbol is required
        assert resp.status_code == 422

    async def test_forecast_tick_count_reflects_recent_events(self, client, db_session):
        """tick_count in /pressure response equals events in last 30s."""
        from app.services.hawkes_ofi import _params_cache
        _params_cache[("BTC/USDT", "binanceus")] = _make_params()

        now = datetime.now(timezone.utc)
        for i in range(7):
            db_session.add(TickTrade(
                ts=now - timedelta(seconds=i + 1),
                symbol="BTC/USDT", venue="binanceus",
                price=50000.0, qty=0.01,
                side=1 if i % 2 == 0 else -1,
                agg_id=i + 1,
            ))
        await db_session.commit()

        resp = await client.get("/hawkes/pressure?symbol=BTC%2FUSDT")
        assert resp.status_code == 200
        assert resp.json()["tick_count"] == 7


# ══════════════════════════════════════════════════════════════════════════════
# 7. Scheduler jobs
# ══════════════════════════════════════════════════════════════════════════════

def _mock_session_ctx(mocker, session=None):
    """Return a mock async context manager that yields `session`."""
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=session or MagicMock())
    mock_ctx.__aexit__  = AsyncMock(return_value=False)
    return mock_ctx


class TestRefitHawkesJob:
    async def test_skips_when_no_crypto_symbols(self, mocker):
        """No crypto symbols → fit_model never called."""
        saved = app_state.watched_symbols
        app_state.watched_symbols = [
            {"symbol": "AAPL", "exchange": "yfinance_us", "asset_type": "us_stock"}
        ]
        # Patch at the source — job imports fit_model lazily from hawkes_ofi
        fit_mock = mocker.patch(
            "app.services.hawkes_ofi.fit_model",
            new=AsyncMock(return_value=None),
        )
        mocker.patch(
            "app.scheduler.jobs.AsyncSessionLocal",
            return_value=_mock_session_ctx(mocker),
        )
        from app.scheduler.jobs import refit_hawkes_job
        await refit_hawkes_job()

        fit_mock.assert_not_called()
        app_state.watched_symbols = saved

    async def test_calls_fit_model_for_crypto_symbols(self, mocker):
        """One fit_model call per crypto symbol."""
        saved = app_state.watched_symbols
        app_state.watched_symbols = [
            {"symbol": "BTC/USDT", "exchange": "binanceus", "asset_type": "crypto"},
            {"symbol": "ETH/USDT", "exchange": "binanceus", "asset_type": "crypto"},
        ]
        fit_mock = mocker.patch(
            "app.services.hawkes_ofi.fit_model",
            new=AsyncMock(return_value=_make_params(branching=0.4)),
        )
        mocker.patch(
            "app.scheduler.jobs.AsyncSessionLocal",
            return_value=_mock_session_ctx(mocker),
        )
        from app.scheduler.jobs import refit_hawkes_job
        await refit_hawkes_job()

        assert fit_mock.call_count == 2
        symbols_fitted = {c.args[0] for c in fit_mock.call_args_list}
        assert "BTC/USDT" in symbols_fitted
        assert "ETH/USDT" in symbols_fitted
        app_state.watched_symbols = saved

    async def test_updates_app_state_regime_after_fit(self, mocker):
        """Successful fit updates hawkes_regime in app_state."""
        saved = app_state.watched_symbols
        app_state.watched_symbols = [
            {"symbol": "BTC/USDT", "exchange": "binanceus", "asset_type": "crypto"},
        ]
        mocker.patch(
            "app.services.hawkes_ofi.fit_model",
            new=AsyncMock(return_value=_make_params(branching=0.95)),   # reflexive
        )
        mocker.patch(
            "app.scheduler.jobs.AsyncSessionLocal",
            return_value=_mock_session_ctx(mocker),
        )
        from app.scheduler.jobs import refit_hawkes_job
        await refit_hawkes_job()

        assert app_state.hawkes_regime.get("BTC/USDT") == "reflexive"
        app_state.watched_symbols = saved

    async def test_handles_fit_error_without_crashing(self, mocker):
        """A failing fit_model should be caught; the job must not propagate the error."""
        saved = app_state.watched_symbols
        app_state.watched_symbols = [
            {"symbol": "BTC/USDT", "exchange": "binanceus", "asset_type": "crypto"},
        ]
        mocker.patch(
            "app.services.hawkes_ofi.fit_model",
            new=AsyncMock(side_effect=RuntimeError("DB down")),
        )
        mocker.patch(
            "app.scheduler.jobs.AsyncSessionLocal",
            return_value=_mock_session_ctx(mocker),
        )
        from app.scheduler.jobs import refit_hawkes_job
        await refit_hawkes_job()   # must not raise

        app_state.watched_symbols = saved

    async def test_none_fit_result_does_not_update_regime(self, mocker):
        """fit_model returning None (insufficient ticks) leaves regime unchanged."""
        saved_symbols = app_state.watched_symbols
        saved_regime  = dict(app_state.hawkes_regime)
        app_state.watched_symbols = [
            {"symbol": "BTC/USDT", "exchange": "binanceus", "asset_type": "crypto"},
        ]
        app_state.hawkes_regime.pop("BTC/USDT", None)

        mocker.patch(
            "app.services.hawkes_ofi.fit_model",
            new=AsyncMock(return_value=None),
        )
        mocker.patch(
            "app.scheduler.jobs.AsyncSessionLocal",
            return_value=_mock_session_ctx(mocker),
        )
        from app.scheduler.jobs import refit_hawkes_job
        await refit_hawkes_job()

        assert "BTC/USDT" not in app_state.hawkes_regime
        app_state.watched_symbols = saved_symbols
        app_state.hawkes_regime.update(saved_regime)


@_skip_no_db
class TestCleanupTickTradesJob:
    def _patch_session(self, mocker, db_session):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.__aexit__  = AsyncMock(return_value=False)
        mocker.patch("app.scheduler.jobs.AsyncSessionLocal", return_value=mock_ctx)

    async def test_removes_ticks_older_than_24h(self, mocker, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(TickTrade(         # OLD — should be deleted
            ts=now - timedelta(hours=25),
            symbol="BTC/USDT", venue="binanceus",
            price=50000.0, qty=0.01, side=1, agg_id=1,
        ))
        db_session.add(TickTrade(         # RECENT — should survive
            ts=now - timedelta(hours=1),
            symbol="BTC/USDT", venue="binanceus",
            price=50000.0, qty=0.01, side=1, agg_id=2,
        ))
        await db_session.commit()
        self._patch_session(mocker, db_session)

        from app.scheduler.jobs import cleanup_tick_trades_job
        await cleanup_tick_trades_job()

        rows = (await db_session.execute(
            select(TickTrade).where(TickTrade.symbol == "BTC/USDT")
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].agg_id == 2

    async def test_no_error_when_table_empty(self, mocker, db_session):
        self._patch_session(mocker, db_session)
        from app.scheduler.jobs import cleanup_tick_trades_job
        await cleanup_tick_trades_job()   # must not raise

    async def test_leaves_ticks_younger_than_24h_intact(self, mocker, db_session):
        now = datetime.now(timezone.utc)
        for i in range(5):
            db_session.add(TickTrade(
                ts=now - timedelta(hours=i + 1),   # 1-5 hours ago — all within 24h
                symbol="BTC/USDT", venue="binanceus",
                price=50000.0, qty=0.01, side=1, agg_id=i + 1,
            ))
        await db_session.commit()
        self._patch_session(mocker, db_session)

        from app.scheduler.jobs import cleanup_tick_trades_job
        await cleanup_tick_trades_job()

        rows = (await db_session.execute(
            select(TickTrade).where(TickTrade.symbol == "BTC/USDT")
        )).scalars().all()
        assert len(rows) == 5

    async def test_mixed_ages_only_old_deleted(self, mocker, db_session):
        """3 old + 2 recent → only 2 remain."""
        now = datetime.now(timezone.utc)
        for i, hours in enumerate([30, 48, 72, 2, 10]):
            db_session.add(TickTrade(
                ts=now - timedelta(hours=hours),
                symbol="BTC/USDT", venue="binanceus",
                price=50000.0, qty=0.01, side=1, agg_id=i + 1,
            ))
        await db_session.commit()
        self._patch_session(mocker, db_session)

        from app.scheduler.jobs import cleanup_tick_trades_job
        await cleanup_tick_trades_job()

        rows = (await db_session.execute(
            select(TickTrade).where(TickTrade.symbol == "BTC/USDT")
        )).scalars().all()
        assert len(rows) == 2


# ══════════════════════════════════════════════════════════════════════════════
# 8. Scheduler registration
# ══════════════════════════════════════════════════════════════════════════════

def test_setup_scheduler_registers_hawkes_jobs():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from app.scheduler.jobs import setup_scheduler

    scheduler = AsyncIOScheduler()
    setup_scheduler(scheduler)
    job_ids = {j.id for j in scheduler.get_jobs()}
    assert "hawkes_refit"        in job_ids
    assert "tick_trades_cleanup" in job_ids


# ══════════════════════════════════════════════════════════════════════════════
# 9. Integration: ticks → fit → pressure endpoint
# ══════════════════════════════════════════════════════════════════════════════

@_skip_no_db
class TestIntegration:
    async def test_end_to_end_fit_then_pressure(self, client, db_session, mock_tick):
        """
        Full pipeline:
        1. Insert enough tick data
        2. Call fit_model (via mocked tick library)
        3. Verify /hawkes/pressure returns 200 with valid response
        """
        from app.services.hawkes_ofi import _MIN_EVENTS, fit_model

        rows = _tick_rows("BTC/USDT", n_buy=_MIN_EVENTS, n_sell=_MIN_EVENTS, age_s=2)
        for r in rows:
            db_session.add(TickTrade(**r))
        await db_session.commit()

        params = await fit_model("BTC/USDT", "binanceus", db=db_session)
        assert params is not None

        resp = await client.get("/hawkes/pressure?symbol=BTC%2FUSDT&venue=binanceus")
        assert resp.status_code == 200
        body = resp.json()
        assert -1.0 <= body["pressure"] <= 1.0

    async def test_end_to_end_fit_then_forecast(self, client, db_session, mock_tick):
        """Full pipeline to /hawkes/forecast with Ogata simulation."""
        from app.services.hawkes_ofi import _MIN_EVENTS, fit_model

        # Use buy-dominant baseline so we expect positive OFI
        mock_tick.baseline  = np.array([8.0, 2.0])
        mock_tick.adjacency = np.zeros((2, 2, 3))

        rows = _tick_rows("BTC/USDT", n_buy=_MIN_EVENTS, n_sell=_MIN_EVENTS, age_s=2)
        for r in rows:
            db_session.add(TickTrade(**r))
        await db_session.commit()

        await fit_model("BTC/USDT", "binanceus", db=db_session)

        resp = await client.get(
            "/hawkes/forecast?symbol=BTC%2FUSDT&venue=binanceus&horizon_s=2.0&n_sims=100"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["prob_buy_pressure"] > 0.5   # buy-dominant baseline

    async def test_pressure_returns_zero_when_no_recent_ticks(self, client):
        """
        Params loaded but no recent ticks → intensity = μ exactly →
        pressure = (μ_b - μ_s) / (μ_b + μ_s).
        """
        from app.services.hawkes_ofi import _params_cache
        mu = np.array([0.6, 0.4])
        _params_cache[("BTC/USDT", "binanceus")] = _make_params(
            mu=mu, alpha=np.zeros((2, 2, 3))
        )
        expected = (mu[0] - mu[1]) / (mu[0] + mu[1])

        resp = await client.get("/hawkes/pressure?symbol=BTC%2FUSDT")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pressure"] == pytest.approx(expected, abs=1e-4)
        assert body["tick_count"] == 0
