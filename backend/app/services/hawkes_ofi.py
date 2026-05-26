"""
Hawkes-Based Order-Flow-Imbalance indicator (crypto only).

Bivariate Hawkes point process on buy/sell market orders with
sum-of-exponentials kernel.  All heavy lifting is in numpy; the `tick`
library is used only for MLE fitting (optional — if not installed, fitting
is disabled but cached params can still be read from DB).

References:
  Bacry & Muzy 2013 (arXiv:1301.1135)
  Nittur Anantha & Jain 2024 (arXiv:2408.03594)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import numpy as np
import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

# ── Hyperparameters ──────────────────────────────────────────────────────────
# Decay values (β) in inverse seconds: fast (~20 ms), medium (~200 ms), slow (~2 s)
_DEFAULT_DECAYS = np.array([50.0, 5.0, 0.5], dtype=float)
_TRAIN_WINDOW_H = 4      # hours of tick data per fit
_MIN_EVENTS     = 200    # skip fit if fewer total events
_MAX_BRANCHING  = 0.98   # reject (but still cache) if spectral radius ≥ this
_CACHE_MAX_AGE  = 4500   # seconds — don't serve params older than 75 min


# ── Cached parameter container ───────────────────────────────────────────────
@dataclass
class _CachedParams:
    mu:        np.ndarray   # (2,)    baseline arrival rates
    alpha:     np.ndarray   # (2,2,K) kernel amplitude matrix
    beta_arr:  np.ndarray   # (K,)    decay constants
    branching: float        # spectral radius of integrated kernel
    fitted_at: datetime
    train_start: datetime
    train_end:   datetime
    loglik: float | None = None

    @property
    def age_s(self) -> float:
        return (datetime.now(timezone.utc) - self.fitted_at).total_seconds()

    @property
    def regime(self) -> str:
        return "reflexive" if self.branching >= 0.9 else "stable"


# In-memory LRU keyed by (symbol, venue)
_params_cache: dict[tuple[str, str], _CachedParams] = {}


# ── Fit ──────────────────────────────────────────────────────────────────────
def _branching_ratio(model) -> float:
    """Spectral radius of the 2×2 integrated-kernel matrix."""
    A = model.adjacency.sum(axis=2)   # (2,2) sum over K decays
    return float(np.max(np.abs(np.linalg.eigvals(A))))


async def fit_model(
    symbol: str,
    venue: str = "binanceus",
    db: "AsyncSession | None" = None,
    decays: np.ndarray | None = None,
) -> _CachedParams | None:
    """
    Load recent ticks, fit HawkesSumExpKern, validate branching ratio,
    persist params to DB, update in-memory cache.
    Returns the fitted _CachedParams (even if branching ≥ 0.98 so the router
    can still show a reflexive-regime state).  Returns None on hard failure.
    """
    try:
        from tick.hawkes import HawkesSumExpKern
    except ImportError:
        log.warning("hawkes_ofi.tick_not_installed — refit skipped")
        return None

    if decays is None:
        decays = _DEFAULT_DECAYS

    train_end   = datetime.now(timezone.utc)
    train_start = train_end - timedelta(hours=_TRAIN_WINDOW_H)

    buy_ts, sell_ts = await _load_ticks(symbol, venue, train_start, train_end, db)

    n_events = len(buy_ts) + len(sell_ts)
    if n_events < _MIN_EVENTS:
        log.info("hawkes_ofi.insufficient_ticks",
                 symbol=symbol, n_events=n_events, required=_MIN_EVENTS)
        return None

    # Timestamps in seconds relative to train_start
    t0         = train_start.timestamp()
    buy_times  = np.sort(np.array(buy_ts,  dtype=float) - t0)
    sell_times = np.sort(np.array(sell_ts, dtype=float) - t0)

    try:
        model = HawkesSumExpKern(decays=decays, penalty="l1", C=1e3)
        model.fit([[buy_times, sell_times]])
    except Exception as exc:
        log.warning("hawkes_ofi.fit_error", symbol=symbol, error=str(exc))
        return None

    branching = _branching_ratio(model)
    if branching >= _MAX_BRANCHING:
        log.info("hawkes_ofi.high_branching",
                 symbol=symbol, branching=round(branching, 4),
                 note="cached as reflexive — not promoted for intensity use")

    loglik: float | None = None
    try:
        loglik = float(model.score([[buy_times, sell_times]]))
    except Exception:
        pass

    params = _CachedParams(
        mu=np.asarray(model.baseline, dtype=float),
        alpha=np.asarray(model.adjacency, dtype=float),
        beta_arr=np.asarray(decays, dtype=float),
        branching=branching,
        fitted_at=datetime.now(timezone.utc),
        train_start=train_start,
        train_end=train_end,
        loglik=loglik,
    )

    if db is not None:
        await _store_params(params, symbol, venue, db)

    _params_cache[(symbol, venue)] = params
    log.info("hawkes_ofi.fitted",
             symbol=symbol, branching=round(branching, 4), n_events=n_events)
    return params


async def _load_ticks(
    symbol: str,
    venue: str,
    train_start: datetime,
    train_end: datetime,
    db: "AsyncSession | None",
) -> tuple[list[float], list[float]]:
    """Return (buy_timestamps, sell_timestamps) as Unix float seconds."""
    if db is None:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db_:
            return await _load_ticks(symbol, venue, train_start, train_end, db_)

    from sqlalchemy import select
    from app.db.models import TickTrade

    rows = (await db.execute(
        select(TickTrade.ts, TickTrade.side)
        .where(
            TickTrade.symbol == symbol,
            TickTrade.venue  == venue,
            TickTrade.ts     >= train_start,
            TickTrade.ts     <= train_end,
        )
        .order_by(TickTrade.ts.asc())
    )).fetchall()

    buy_ts  = [r.ts.timestamp() for r in rows if r.side ==  1]
    sell_ts = [r.ts.timestamp() for r in rows if r.side == -1]
    return buy_ts, sell_ts


async def _store_params(
    params: _CachedParams,
    symbol: str,
    venue: str,
    db: "AsyncSession",
) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.db.models import HawkesParams

    try:
        stmt = pg_insert(HawkesParams).values(
            fitted_at=params.fitted_at,
            symbol=symbol,
            venue=venue,
            mu=params.mu.tolist(),
            alpha=params.alpha.tolist(),
            beta_vals=params.beta_arr.tolist(),
            branching=params.branching,
            train_start=params.train_start,
            train_end=params.train_end,
            loglik=params.loglik,
        ).on_conflict_do_nothing()
        await db.execute(stmt)
        await db.commit()
    except Exception as exc:
        log.warning("hawkes_ofi.store_params_error", error=str(exc))


# ── Param loading ────────────────────────────────────────────────────────────
async def load_cached_params(
    symbol: str,
    venue: str = "binanceus",
    db: "AsyncSession | None" = None,
) -> _CachedParams | None:
    """Return in-memory cached params if fresh, else query DB."""
    cached = _params_cache.get((symbol, venue))
    if cached is not None and cached.age_s < _CACHE_MAX_AGE:
        return cached

    if db is None:
        return None

    from sqlalchemy import select
    from app.db.models import HawkesParams

    row = (await db.execute(
        select(HawkesParams)
        .where(HawkesParams.symbol == symbol, HawkesParams.venue == venue)
        .order_by(HawkesParams.fitted_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    if row is None:
        return None

    params = _CachedParams(
        mu=np.array(row.mu, dtype=float),
        alpha=np.array(row.alpha, dtype=float),
        beta_arr=np.array(row.beta_vals, dtype=float),
        branching=float(row.branching or 0.0),
        fitted_at=row.fitted_at.replace(tzinfo=timezone.utc)
                  if row.fitted_at.tzinfo is None else row.fitted_at,
        train_start=(row.train_start or row.fitted_at).replace(tzinfo=timezone.utc)
                    if (row.train_start or row.fitted_at).tzinfo is None
                    else (row.train_start or row.fitted_at),
        train_end=(row.train_end or row.fitted_at).replace(tzinfo=timezone.utc)
                  if (row.train_end or row.fitted_at).tzinfo is None
                  else (row.train_end or row.fitted_at),
        loglik=row.loglik,
    )
    _params_cache[(symbol, venue)] = params
    return params


# ── Recent event loading ──────────────────────────────────────────────────────
async def get_recent_events(
    symbol: str,
    venue: str,
    lookback_s: float = 30.0,
    db: "AsyncSession | None" = None,
) -> list[tuple[float, int]]:
    """Return [(timestamp_unix_float, side), …] for ticks in the last lookback_s seconds."""
    if db is None:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db_:
            return await get_recent_events(symbol, venue, lookback_s, db_)

    from sqlalchemy import select
    from app.db.models import TickTrade

    since = datetime.now(timezone.utc) - timedelta(seconds=lookback_s)
    rows = (await db.execute(
        select(TickTrade.ts, TickTrade.side)
        .where(
            TickTrade.symbol == symbol,
            TickTrade.venue  == venue,
            TickTrade.ts     >= since,
        )
        .order_by(TickTrade.ts.asc())
    )).fetchall()

    return [(r.ts.timestamp(), r.side) for r in rows]


# ── Intensity calculation ─────────────────────────────────────────────────────
def recursive_intensity(
    params: _CachedParams,
    events: list[tuple[float, int]],
) -> tuple[float, float]:
    """
    Compute λ_b, λ_s at current time via exponential-kernel recursion — O(N events).

    R[j, k] = Σ_{past events of type j} exp(−β_k · (t_now − t_event))
    λ_i     = μ_i + Σ_j Σ_k α_ijk · β_k · R[j, k]
    """
    mu       = params.mu        # (2,)
    alpha    = params.alpha     # (2, 2, K)
    beta_arr = params.beta_arr  # (K,)

    R      = np.zeros((2, len(beta_arr)), dtype=float)   # (n_types, K)
    t_now  = datetime.now(timezone.utc).timestamp()

    for t_event, side in events:
        delta = t_now - t_event
        if delta < 0:
            continue
        j = 0 if side == 1 else 1   # +1=buy→j=0, -1=sell→j=1
        R[j, :] += np.exp(-beta_arr * delta)

    # λ_i = μ_i + Σ_j Σ_k α_ijk · β_k · R_jk
    lam = mu + (alpha * beta_arr[None, None, :] * R[None, :, :]).sum(axis=(1, 2))
    lam = np.maximum(lam, 0.0)

    return float(lam[0]), float(lam[1])


def compute_pressure(lambda_buy: float, lambda_sell: float) -> float:
    """S_press = (λ_b − λ_s) / (λ_b + λ_s) ∈ [−1, 1]."""
    denom = lambda_buy + lambda_sell
    return (lambda_buy - lambda_sell) / denom if denom > 1e-12 else 0.0


# ── Forward simulation ────────────────────────────────────────────────────────
def simulate_forward(
    params: _CachedParams,
    events: list[tuple[float, int]],
    horizon_s: float = 5.0,
    n_sims: int = 200,
) -> dict[str, float]:
    """
    Ogata thinning simulation: run the Hawkes process forward horizon_s seconds
    N times from the current intensity state.  Returns OFI distribution stats.
    """
    mu       = params.mu
    alpha    = params.alpha
    beta_arr = params.beta_arr

    # Starting R matrix from recent events
    R0    = np.zeros((2, len(beta_arr)), dtype=float)
    t_ref = datetime.now(timezone.utc).timestamp()
    for t_event, side in events:
        delta = t_ref - t_event
        if delta >= 0:
            j = 0 if side == 1 else 1
            R0[j, :] += np.exp(-beta_arr * delta)

    rng         = np.random.default_rng()
    ofi_samples = []

    for _ in range(n_sims):
        n_buy, n_sell = _simulate_one(mu, alpha, beta_arr, R0.copy(), horizon_s, rng)
        total = n_buy + n_sell
        ofi_samples.append((n_buy - n_sell) / total if total > 0 else 0.0)

    arr = np.array(ofi_samples)
    return {
        "mean":              float(arr.mean()),
        "p10":               float(np.percentile(arr, 10)),
        "p50":               float(np.percentile(arr, 50)),
        "p90":               float(np.percentile(arr, 90)),
        "prob_buy_pressure": float((arr > 0).mean()),
    }


def _simulate_one(
    mu:        np.ndarray,
    alpha:     np.ndarray,
    beta_arr:  np.ndarray,
    R:         np.ndarray,
    horizon_s: float,
    rng:       np.random.Generator,
) -> tuple[int, int]:
    """
    One Ogata-thinning realization of the bivariate Hawkes process.
    Returns (n_buy_events, n_sell_events) over [0, horizon_s].
    """
    n_buy = n_sell = 0
    t = 0.0

    for _ in range(10_000):   # safety cap — process terminates naturally
        # Total intensity at current time
        lam = mu + (alpha * beta_arr[None, None, :] * R[None, :, :]).sum(axis=(1, 2))
        lam = np.maximum(lam, 0.0)
        lam_total = float(lam.sum())

        if lam_total < 1e-12:
            break

        # Sample candidate inter-arrival time at current (upper-bound) rate
        u      = rng.exponential(1.0 / lam_total)
        t_cand = t + u
        if t_cand > horizon_s:
            break

        # Decay R to t_cand (no new event yet)
        R_new = R * np.exp(-beta_arr[None, :] * u)

        # True intensity at t_cand
        lam_c       = mu + (alpha * beta_arr[None, None, :] * R_new[None, :, :]).sum(axis=(1, 2))
        lam_c       = np.maximum(lam_c, 0.0)
        lam_c_total = float(lam_c.sum())

        # Thinning accept/reject
        if rng.random() < lam_c_total / lam_total:
            # Which node fires?
            p_buy = float(lam_c[0]) / lam_c_total if lam_c_total > 0 else 0.5
            j = 0 if rng.random() < p_buy else 1
            if j == 0:
                n_buy += 1
            else:
                n_sell += 1
            R_new[j, :] += 1.0   # new event contributes to future intensity

        R = R_new
        t = t_cand

    return n_buy, n_sell
