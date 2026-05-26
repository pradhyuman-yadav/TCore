# Hawkes-Based Order-Flow-Imbalance Indicator — Build Spec

A drop-in indicator for your TimescaleDB → FastAPI → React stack. It treats buy and
sell market orders as two cross-exciting point processes, fits a bivariate Hawkes model,
and emits a forward-looking imbalance signal. The AI layer never trades — it (optionally)
proposes kernel hyperparameters; the Hawkes intensity is the indicator.

Grounded in: Bacry & Muzy (2013, arXiv:1301.1135) for the price/trade Hawkes framework,
and Nittur Anantha & Jain (2024, arXiv:2408.03594) for the OFI-forecasting construction.
The latter found a **sum-of-exponentials kernel** gave the best OFI forecast among the
models they tested on NSE Nifty futures.

---

## 0. The one thing crypto makes easy

The hardest part of this in equities is *trade classification* — deciding whether a print
was buyer- or seller-initiated. Equity papers lean on the Lee-Ready algorithm or order-ID
matching, both of which "may struggle in highly volatile markets or during periods of rapid
price movements." You don't have that problem.

Binance (and most CEX) trade feeds hand you the taker side directly. On the `aggTrade`
stream the boolean field `m` ("is the buyer the market maker") tells you the aggressor:

- `m == false` → buyer was the taker → **BUY** market order (lifts the ask)
- `m == true`  → seller was the taker → **SELL** market order (hits the bid)

So your classification is deterministic and free. This is a genuine structural advantage of
crypto microstructure over the equity setting the papers were written for.

---

## 1. Definitions

Counting processes over event (tick) time, one per side:

```
N_b(t) = number of BUY market orders up to time t
N_s(t) = number of SELL market orders up to time t
```

**Order Flow Imbalance** over a trailing window of length `h` ending at `T`
(volume-weighted variant in parentheses):

```
OFI(T, h) = (ΔN_b − ΔN_s) / (ΔN_b + ΔN_s)        # count-based, range [-1, 1]
          = (ΔV_b − ΔV_s) / (ΔV_b + ΔV_s)        # volume-based (preferred for crypto)

where ΔN_b = N_b(T) − N_b(T−h),  etc.
```

> Sign convention: positive OFI = net buying pressure. (The arXiv:2408.03594 formula writes
> sell-minus-buy in the numerator; flip the sign if you cross-check against it.)

**Bivariate Hawkes intensity** — the rate of the next buy/sell event given all history:

```
λ_b(t) = μ_b + Σ_{t_i < t} [ φ_bb(t − t_i^b) + φ_bs(t − t_i^s) ]
λ_s(t) = μ_s + Σ_{t_i < t} [ φ_sb(t − t_i^b) + φ_ss(t − t_i^s) ]
```

- `μ_b, μ_s` — baseline (exogenous) arrival rates
- `φ_bb` — buys exciting future buys (momentum / order splitting)
- `φ_bs` — sells exciting future buys, and `φ_sb` the reverse (mean-reversion / liquidity response)
- `φ_ss` — sell self-excitation

The **branching ratio** (spectral radius of the kernel-integral matrix) must be < 1 for the
process to be stable. It is also your endogeneity gauge: near 1 means order flow is mostly
self-generated (reflexive), which empirically coincides with fragile, jumpy regimes.

**Sum-of-exponentials kernel** (the winner in arXiv:2408.03594), each `φ` of the form:

```
φ(τ) = Σ_{k=1..K}  α_k · β_k · exp(−β_k · τ)
```

K = 2 or 3 components is plenty: one fast (sub-second reflexivity), one slow (seconds-scale
flow persistence). Exponentials are chosen because they make the intensity *Markovian* — you
can update it recursively per event in O(1) instead of re-summing history, which is what makes
this viable for a live FastAPI endpoint.

---

## 2. The signal you actually trade off

Two usable outputs, pick based on horizon:

**(a) Instantaneous pressure** — cheap, updates every tick:

```
S_press(t) = (λ_b(t) − λ_s(t)) / (λ_b(t) + λ_s(t))      ∈ [-1, 1]
```

**(b) Forecast OFI distribution** — simulate the fitted process forward over `[t, t+h]`
N times (thinning / Ogata), giving a *distribution* not a point estimate. Trade the tails,
size by confidence. arXiv:2408.03594's core argument is that forecasting the **near-term
distribution** of OFI — not just its mean — is what's actually useful, because HFT flow is
too noisy for point forecasts to mean much.

```
forecast = { mean_OFI, p10, p50, p90, prob(OFI > 0) }  over horizon h
```

---

## 3. Data schema (TimescaleDB)

Raw trades hypertable — this is your source of truth:

```sql
CREATE TABLE trades (
    ts          TIMESTAMPTZ      NOT NULL,   -- exchange event time, microsecond
    symbol      TEXT             NOT NULL,
    venue       TEXT             NOT NULL,    -- 'binance-spot', 'binance-perp', ...
    price       DOUBLE PRECISION NOT NULL,
    qty         DOUBLE PRECISION NOT NULL,
    side        SMALLINT         NOT NULL,    -- +1 = BUY taker, -1 = SELL taker
    agg_id      BIGINT                        -- exchange aggTrade id, for dedupe
);
SELECT create_hypertable('trades', 'ts');
CREATE UNIQUE INDEX ON trades (venue, symbol, agg_id);
```

Fitted-parameter cache — refit on a schedule, read on every request:

```sql
CREATE TABLE hawkes_params (
    fitted_at   TIMESTAMPTZ NOT NULL,
    symbol      TEXT NOT NULL,
    venue       TEXT NOT NULL,
    mu          JSONB NOT NULL,   -- [mu_b, mu_s]
    alpha       JSONB NOT NULL,   -- 2x2xK
    beta        JSONB NOT NULL,   -- 2x2xK
    branching   DOUBLE PRECISION, -- spectral radius, must be < 1
    train_start TIMESTAMPTZ,
    train_end   TIMESTAMPTZ,
    loglik      DOUBLE PRECISION,
    PRIMARY KEY (symbol, venue, fitted_at)
);
```

A continuous aggregate gives you realized OFI cheaply for backtest labels:

```sql
CREATE MATERIALIZED VIEW ofi_1s
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 second', ts) AS bucket, symbol, venue,
       SUM(CASE WHEN side =  1 THEN qty ELSE 0 END) AS buy_vol,
       SUM(CASE WHEN side = -1 THEN qty ELSE 0 END) AS sell_vol
FROM trades GROUP BY bucket, symbol, venue;
```

---

## 4. Estimation

Use the `tick` library (`pip install tick`) — it has MLE for sum-of-exponential Hawkes kernels
out of the box and is the path of least resistance. `HawkesExpKern` (single decay per kernel)
or `HawkesSumExpKern` (multiple fixed decays) are the relevant classes.

```python
import numpy as np
from tick.hawkes import HawkesSumExpKern

def fit_hawkes(buy_times: np.ndarray, sell_times: np.ndarray,
               decays=(50.0, 5.0, 0.5)):   # betas: ~20ms, ~200ms, ~2s
    """
    buy_times / sell_times: 1-D arrays of event timestamps in SECONDS,
    relative to a common t0, strictly increasing.
    Returns a fitted bivariate model.
    """
    realization = [buy_times, sell_times]      # node 0 = BUY, node 1 = SELL
    model = HawkesSumExpKern(decays=np.array(decays), penalty='l1', C=1e3)
    model.fit([realization])
    return model

# Branching ratio (stability + endogeneity). For sum-of-exp, the kernel L1 norm
# per (i,j) is sum_k adjacency[i,j,k]; spectral radius of that 2x2 matrix must be < 1.
def branching_ratio(model):
    A = model.adjacency.sum(axis=2)            # 2x2 integrated kernel norms
    return float(np.max(np.abs(np.linalg.eigvals(A))))
```

Practical fitting notes:

- **Refit cadence:** every 15–60 min on a rolling 2–6 h window. Crypto regimes drift; a model
  from yesterday is close to useless. Store each fit in `hawkes_params`.
- **Reject unstable fits:** if `branching_ratio >= 0.98`, don't promote the params — flag the
  regime as reflexive instead (that itself is a tradeable state signal).
- **Per-asset, per-venue:** arXiv 2026 (Frontiers) found microstructure models **do not
  transfer across coins**, but **do transfer between spot and perp of the same asset**. So fit
  BTC-perp from BTC-spot if you must, never from ETH.

---

## 5. FastAPI endpoint

Two responsibilities: a cheap live read off cached params, and the heavier forecast.

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import numpy as np

app = FastAPI()

class PressureResponse(BaseModel):
    symbol: str
    venue: str
    pressure: float          # S_press in [-1, 1]
    lambda_buy: float
    lambda_sell: float
    branching: float
    regime: str              # 'stable' | 'reflexive'
    params_age_s: float

@app.get("/indicator/ofi/pressure", response_model=PressureResponse)
async def ofi_pressure(symbol: str, venue: str = "binance-perp"):
    params = await load_latest_params(symbol, venue)        # from hawkes_params
    if params is None:
        raise HTTPException(404, "no fitted model; run the fitter first")

    events = await load_recent_events(symbol, venue, lookback_s=30)  # from trades
    lam_b, lam_s = recursive_intensity(params, events)      # O(events), exp-kernel recursion
    denom = lam_b + lam_s
    pressure = (lam_b - lam_s) / denom if denom > 0 else 0.0

    return PressureResponse(
        symbol=symbol, venue=venue, pressure=pressure,
        lambda_buy=lam_b, lambda_sell=lam_s,
        branching=params.branching,
        regime="reflexive" if params.branching >= 0.9 else "stable",
        params_age_s=params.age_s,
    )

@app.get("/indicator/ofi/forecast")
async def ofi_forecast(symbol: str, venue: str = "binance-perp",
                       horizon_s: float = 5.0, n_sims: int = 500):
    params = await load_latest_params(symbol, venue)
    sims = simulate_forward(params, horizon_s, n_sims)      # Ogata thinning
    ofi = [(s.n_buy - s.n_sell) / max(s.n_buy + s.n_sell, 1) for s in sims]
    ofi = np.array(ofi)
    return {
        "mean": float(ofi.mean()),
        "p10": float(np.percentile(ofi, 10)),
        "p50": float(np.percentile(ofi, 50)),
        "p90": float(np.percentile(ofi, 90)),
        "prob_buy_pressure": float((ofi > 0).mean()),
    }
```

The exponential kernel is what lets `recursive_intensity` be O(1) per event: keep a running
sum `R_k` per decay component, and on each new event at gap `Δt`, decay then add:
`R_k ← R_k · exp(−β_k · Δt) + 1`, then `λ = μ + Σ_k α_k β_k R_k`. No history replay.

For the React/TradingView side: plot `pressure` as a sub-pane oscillator and shade the
background when `regime == 'reflexive'`.

---

## 6. The AI layer (kept in its lane)

Per your design rule — agents generate indicators, they don't trade. Reasonable jobs for an
LLM/ML agent here, none of which touch order submission:

- Propose the decay set `(β_1..β_K)` per symbol from recent autocorrelation structure.
- Choose refit window length based on detected regime shifts.
- Generate *candidate* feature combinations (e.g. pressure × spread × realized vol) for you to
  backtest — output as a config, not an action.

---

## 7. Validation — do this before believing any of it

This is where most of these strategies die, so it's not optional.

1. **Purged walk-forward CV.** Train on `[t0, t1]`, leave an embargo gap, test on `[t2, t3]`,
   roll forward. No shuffling, ever. The Frontiers (2026) paper showed gradient-boosted
   microstructure models that looked great **overfit severely** the moment proper leakage
   controls were applied.
2. **Fee-inclusive PnL only.** Their headline finding: **no microstructure strategy survived
   realistic exchange fees** at retail tiers. So bake taker/maker fees and funding into the
   backtest from line one. If the edge only exists gross, it doesn't exist.
3. **Compare against a naive baseline** (last-value / random-walk OFI). If you can't beat
   "OFI stays where it is," the Hawkes machinery is buying you nothing.
4. **Test on spot↔perp of one asset**, since that's the only transfer direction that held up.

Honest framing: the realistic edge here is probably **not** a standalone alpha. It's (a) a
**regime/toxicity filter** that keeps your other strategies out of reflexive states, and (b)
an **execution timing** input — when `prob_buy_pressure` is high, post passive bids and earn
the maker rebate instead of crossing. Maker-rebate capture is often where the margin actually
lives at retail fee tiers, and this signal feeds it directly.

---

## 8. Build order

1. Trade ingestion → `trades` hypertable (you likely have most of this).
2. Offline notebook: fit `HawkesSumExpKern` on a few hours of BTC-perp, eyeball branching ratio
   and kernel shapes. Sanity-check before any infra.
3. The fitter cron job → `hawkes_params`.
4. `/pressure` endpoint (cheap, recursive).
5. Walk-forward backtest with fees. **Gate everything on Section 7 results.**
6. Only then: `/forecast` endpoint and React pane.
