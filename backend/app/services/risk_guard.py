"""
Risk guard — the deterministic safety layer between signal and execution.

Why this exists
---------------
`rule_engine.evaluate_rules` decides *direction* (buy/sell/hold) from the
composite score. It does NOT protect capital: no stop-loss, no volatility-based
sizing, no portfolio exposure cap, no drawdown circuit breaker. Those are what
actually stop an account from blowing up.

This module is the hard layer. Whatever the signal — or later, the Claude trader
agent — proposes, the risk guard can clamp it, resize it, or veto it. It is
deterministic and pure (no I/O), so it is fully testable and can never be talked
out of a limit by a clever model. **The agent proposes; the risk guard disposes.**

Scope: the platform trades long/flat (open a long, close it). Sizing and stops
are written for that. Short support can be added later symmetrically.

Forced exits (stop-loss / take-profit) override the incoming signal: if an open
position has breached its stop or target, the guard returns SELL even when the
signal says hold or buy. Stops are recomputed each cycle from entry price and
current ATR (a simple volatility stop), so they adapt as volatility changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.services.rule_engine import TradeSignal


def compute_atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> float | None:
    """
    Average True Range over the last `period` bars (simple mean of true ranges).

    True range = max(high-low, |high-prev_close|, |low-prev_close|).
    Returns None when there are not enough bars. Pure — no pandas dependency so
    it stays unit-testable and import-light.
    """
    n = len(closes)
    if n < period + 1 or len(highs) != n or len(lows) != n:
        return None
    trs: list[float] = []
    for i in range(1, n):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    last = trs[-period:]
    return sum(last) / len(last) if last else None


# ── Configuration ───────────────────────────────────────────────────────────
@dataclass
class RiskParams:
    """Risk limits. Sensible conservative defaults; override per strategy."""
    risk_per_trade_pct: float = 0.01       # risk 1% of equity per new trade
    stop_loss_atr_mult: float = 2.0        # stop distance = mult * ATR
    take_profit_atr_mult: float = 3.0      # target distance = mult * ATR (R:R 1.5)
    stop_loss_pct_fallback: float = 0.02   # used when ATR is unavailable
    max_position_pct: float = 0.25         # single position notional <= 25% equity
    max_total_exposure_pct: float = 0.60   # sum of open notional <= 60% equity
    max_drawdown_pct: float = 0.20         # halt NEW entries when equity DD > 20%
    min_position_usdt: float = 10.0        # don't bother below this

    def __post_init__(self) -> None:
        if not (0 < self.risk_per_trade_pct < 1):
            raise ValueError("risk_per_trade_pct must be in (0, 1)")
        if self.stop_loss_atr_mult <= 0 or self.take_profit_atr_mult <= 0:
            raise ValueError("ATR multipliers must be positive")
        if not (0 < self.max_position_pct <= 1):
            raise ValueError("max_position_pct must be in (0, 1]")
        if not (0 < self.max_total_exposure_pct <= 1):
            raise ValueError("max_total_exposure_pct must be in (0, 1]")
        if not (0 < self.max_drawdown_pct < 1):
            raise ValueError("max_drawdown_pct must be in (0, 1)")


@dataclass
class PositionState:
    """The open long position for the symbol under evaluation, if any."""
    entry_price: float
    quantity: float
    side: str = "buy"   # long/flat platform: always "buy" for now


@dataclass
class RiskContext:
    """Everything the guard needs to make a capital-safe decision."""
    price: float                          # current mark price
    equity: float                         # account equity (capital + realised PnL)
    peak_equity: float                    # high-water mark, for drawdown breaker
    atr: float | None = None              # recent ATR for vol sizing/stops
    open_position: PositionState | None = None  # this symbol's open long
    total_open_notional: float = 0.0      # portfolio-wide open notional (this symbol incl.)


@dataclass
class RiskDecision:
    action: str                    # "buy" | "sell" | "hold"
    quantity_usdt: float           # sized notional for buy; 0.0 for sell/hold
    reason: str
    stop_loss: float | None = None
    take_profit: float | None = None
    vetoed: bool = False           # True when the guard overrode/blocked the signal

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "quantity_usdt": round(self.quantity_usdt, 4),
            "reason": self.reason,
            "stop_loss": round(self.stop_loss, 8) if self.stop_loss is not None else None,
            "take_profit": round(self.take_profit, 8) if self.take_profit is not None else None,
            "vetoed": self.vetoed,
        }


# ── Helpers ──────────────────────────────────────────────────────────────────
def _stop_distance(price: float, atr: float | None, p: RiskParams) -> float:
    """Stop distance in price units: ATR-based when available, else pct fallback."""
    if atr is not None and atr > 0:
        return atr * p.stop_loss_atr_mult
    return price * p.stop_loss_pct_fallback


def _target_distance(price: float, atr: float | None, p: RiskParams) -> float:
    if atr is not None and atr > 0:
        return atr * p.take_profit_atr_mult
    # keep the same reward:risk ratio as the ATR case when falling back
    rr = p.take_profit_atr_mult / p.stop_loss_atr_mult
    return price * p.stop_loss_pct_fallback * rr


def _drawdown(equity: float, peak_equity: float) -> float:
    if peak_equity <= 0:
        return 0.0
    return max(0.0, (peak_equity - equity) / peak_equity)


# ── The guard ─────────────────────────────────────────────────────────────────
def apply_risk_guard(
    signal: TradeSignal,
    ctx: RiskContext,
    params: RiskParams | None = None,
) -> RiskDecision:
    """
    Clamp/veto/override a proposed signal so it respects hard risk limits.

    Order of precedence:
      1. Forced exits (stop-loss / take-profit) on an open position — these
         OVERRIDE the incoming signal.
      2. Drawdown circuit breaker — blocks all NEW entries (sells still allowed).
      3. Sell signals — passed through (close the position).
      4. Buy signals — volatility-sized, clamped to per-position and portfolio
         exposure caps, vetoed if the resulting size is below the minimum.
      5. Hold — passed through.
    """
    p = params or RiskParams()
    price = ctx.price

    # ── 1. Forced exits override everything ─────────────────────────────────
    if ctx.open_position is not None and price > 0:
        entry = ctx.open_position.entry_price
        stop_price = entry - _stop_distance(entry, ctx.atr, p)
        target_price = entry + _target_distance(entry, ctx.atr, p)
        if price <= stop_price:
            return RiskDecision(
                action="sell", quantity_usdt=0.0,
                reason=f"stop-loss hit: price {price:.4f} <= stop {stop_price:.4f}",
                stop_loss=stop_price, take_profit=target_price, vetoed=True,
            )
        if price >= target_price:
            return RiskDecision(
                action="sell", quantity_usdt=0.0,
                reason=f"take-profit hit: price {price:.4f} >= target {target_price:.4f}",
                stop_loss=stop_price, take_profit=target_price, vetoed=True,
            )

    # ── 2. Sell signal: always allow closing ────────────────────────────────
    if signal.action == "sell":
        return RiskDecision(
            action="sell", quantity_usdt=0.0,
            reason=signal.reason, vetoed=False,
        )

    # ── 3. Hold: nothing to size ────────────────────────────────────────────
    if signal.action != "buy":
        return RiskDecision(
            action="hold", quantity_usdt=0.0, reason=signal.reason, vetoed=False,
        )

    # ── 4. Buy: drawdown breaker blocks new entries ─────────────────────────
    dd = _drawdown(ctx.equity, ctx.peak_equity)
    if dd > p.max_drawdown_pct:
        return RiskDecision(
            action="hold", quantity_usdt=0.0,
            reason=f"drawdown breaker: {dd:.1%} > {p.max_drawdown_pct:.0%}",
            vetoed=True,
        )

    if ctx.equity <= 0 or price <= 0:
        return RiskDecision(
            action="hold", quantity_usdt=0.0,
            reason="non-positive equity or price", vetoed=True,
        )

    # ── 4a. Volatility-based sizing ─────────────────────────────────────────
    # Risk a fixed fraction of equity. Notional is set so that a move to the
    # stop loses exactly `risk_per_trade_pct * equity`:
    #   loss_at_stop = notional * (stop_distance / price) = risk_budget
    #   => notional = risk_budget * price / stop_distance
    stop_dist = _stop_distance(price, ctx.atr, p)
    risk_budget = ctx.equity * p.risk_per_trade_pct
    notional = risk_budget * price / stop_dist if stop_dist > 0 else 0.0

    # ── 4b. Per-position cap ────────────────────────────────────────────────
    max_pos = ctx.equity * p.max_position_pct
    if notional > max_pos:
        notional = max_pos

    # ── 4c. Portfolio exposure cap ──────────────────────────────────────────
    exposure_budget = ctx.equity * p.max_total_exposure_pct
    remaining = exposure_budget - ctx.total_open_notional
    if remaining <= 0:
        return RiskDecision(
            action="hold", quantity_usdt=0.0,
            reason=f"exposure cap reached ({ctx.total_open_notional:.0f}/{exposure_budget:.0f})",
            vetoed=True,
        )
    if notional > remaining:
        notional = remaining

    # ── 4d. Minimum-size veto ───────────────────────────────────────────────
    if notional < p.min_position_usdt:
        return RiskDecision(
            action="hold", quantity_usdt=0.0,
            reason=f"sized position {notional:.2f} below minimum {p.min_position_usdt}",
            vetoed=True,
        )

    stop_price = price - stop_dist
    target_price = price + _target_distance(price, ctx.atr, p)
    return RiskDecision(
        action="buy",
        quantity_usdt=notional,
        reason=f"{signal.reason} | vol-sized {notional:.2f} USDT (risk {p.risk_per_trade_pct:.1%})",
        stop_loss=stop_price,
        take_profit=target_price,
        vetoed=False,
    )
