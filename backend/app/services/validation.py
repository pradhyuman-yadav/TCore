"""
Walk-forward validation harness for trading strategies.

Why this exists
---------------
`backtest_runner.run_backtest` gives ONE in-sample equity curve. A single
in-sample number proves nothing — overfit strategies look great in-sample and
die live. This module wraps the existing engine in a walk-forward / purged
cross-validation loop, aggregates out-of-sample (OOS) performance, and applies
a deterministic pass/fail gate. No strategy should be promoted to live trading
until it clears this gate.

Design
------
- We reuse `run_backtest` unchanged as the per-window simulator.
- The OHLCV frame is split into rolling (train, test) folds. We only score the
  TEST windows — that is the out-of-sample performance.
- A `purge` gap (in bars) is dropped between train end and test start, and an
  `embargo` gap after each test window, so adjacent-bar leakage can't inflate
  results. (The current engine uses a static config, so leakage is small today,
  but the harness is correct for when per-fold parameter fitting is added.)
- Costs (fee + slippage) are forced to realistic floors — a backtest with zero
  costs is a lie.

Everything here is pure (no DB, no network) so it is fully unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

import numpy as np
import pandas as pd

from app.services.backtest_runner import (
    BacktestResult,
    BacktestTrade,
    _MIN_WARMUP_BARS,
    run_backtest,
)

# ── Realistic-cost floors ───────────────────────────────────────────────────
# A validation run must not be cheaper than reality. Callers may pass higher
# values; we clamp UP to these floors, never down.
MIN_FEE_RATE = 0.001        # 10 bps taker (Binance US spot, conservative)
MIN_SLIPPAGE_BPS = 2.0      # 2 bps slippage floor on market orders

# ── Bars per year by timeframe — for annualised Sharpe/Sortino ──────────────
_BARS_PER_YEAR: dict[str, float] = {
    "1m": 525_600.0,
    "5m": 105_120.0,
    "15m": 35_040.0,
    "30m": 17_520.0,
    "1h": 8_760.0,
    "2h": 4_380.0,
    "4h": 2_190.0,
    "6h": 1_460.0,
    "12h": 730.0,
    "1d": 365.0,
}


def _periods_per_year(timeframe: str) -> float:
    return _BARS_PER_YEAR.get(timeframe, 365.0)


# ── Gate thresholds ─────────────────────────────────────────────────────────
@dataclass
class GateThresholds:
    """Deterministic promotion criteria, applied to aggregated OOS metrics."""
    min_total_trades: int = 30        # statistical-significance floor
    min_profit_factor: float = 1.2    # gross wins / gross losses
    min_expectancy: float = 0.0       # avg PnL per trade, after costs, > 0
    min_sharpe: float = 1.0           # annualised, on OOS test windows
    max_drawdown: float = 0.25        # worst peak-to-trough on OOS equity
    min_fold_consistency: float = 0.6  # fraction of test folds that are profitable


# ── Rich per-window stats ───────────────────────────────────────────────────
@dataclass
class WindowStats:
    """Honest stats derived from a single test-window BacktestResult."""
    num_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0     # inf-safe: 0 losses -> large finite number
    expectancy: float = 0.0        # mean PnL per closed trade
    max_drawdown: float = 0.0
    sharpe: float | None = None
    sortino: float | None = None

    def to_dict(self) -> dict:
        return {
            "num_trades": self.num_trades,
            "total_pnl": round(self.total_pnl, 4),
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 4),
            "expectancy": round(self.expectancy, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe": round(self.sharpe, 4) if self.sharpe is not None else None,
            "sortino": round(self.sortino, 4) if self.sortino is not None else None,
        }


@dataclass
class FoldResult:
    fold: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    stats: WindowStats
    result: BacktestResult

    def to_dict(self) -> dict:
        return {
            "fold": self.fold,
            "train_bars": [self.train_start, self.train_end],
            "test_bars": [self.test_start, self.test_end],
            "stats": self.stats.to_dict(),
        }


@dataclass
class ValidationReport:
    symbol: str
    timeframe: str
    folds: list[FoldResult] = field(default_factory=list)

    # Aggregated OOS metrics (pooled across all test windows)
    oos_total_pnl: float = 0.0
    oos_num_trades: int = 0
    oos_win_rate: float = 0.0
    oos_profit_factor: float = 0.0
    oos_expectancy: float = 0.0
    oos_max_drawdown: float = 0.0
    oos_sharpe: float | None = None
    oos_sortino: float | None = None
    fold_consistency: float = 0.0   # fraction of profitable folds

    passed: bool = False
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "passed": self.passed,
            "reasons": self.reasons,
            "oos": {
                "total_pnl": round(self.oos_total_pnl, 4),
                "num_trades": self.oos_num_trades,
                "win_rate": round(self.oos_win_rate, 4),
                "profit_factor": round(self.oos_profit_factor, 4),
                "expectancy": round(self.oos_expectancy, 4),
                "max_drawdown": round(self.oos_max_drawdown, 4),
                "sharpe": round(self.oos_sharpe, 4) if self.oos_sharpe is not None else None,
                "sortino": round(self.oos_sortino, 4) if self.oos_sortino is not None else None,
                "fold_consistency": round(self.fold_consistency, 4),
            },
            "folds": [f.to_dict() for f in self.folds],
        }


# ── Splitting ───────────────────────────────────────────────────────────────
def walk_forward_splits(
    n_bars: int,
    train_size: int,
    test_size: int,
    purge: int = 0,
    embargo: int = 0,
    step: int | None = None,
) -> list[tuple[int, int, int, int]]:
    """
    Produce rolling (train_start, train_end, test_start, test_end) index tuples.

    Half-open ranges: bars [train_start, train_end) train, a `purge` gap is
    skipped, then [test_start, test_end) is the OOS window. `embargo` bars are
    skipped after each test window before the next fold begins. `step` controls
    how far the window slides each fold (defaults to test_size — non-overlapping
    test windows, the honest choice).

    Raises ValueError on non-positive sizes. Returns [] if not enough bars.
    """
    if train_size <= 0 or test_size <= 0:
        raise ValueError("train_size and test_size must be positive")
    if purge < 0 or embargo < 0:
        raise ValueError("purge and embargo must be non-negative")
    if step is None:
        step = test_size
    if step <= 0:
        raise ValueError("step must be positive")

    splits: list[tuple[int, int, int, int]] = []
    train_start = 0
    while True:
        train_end = train_start + train_size
        test_start = train_end + purge
        test_end = test_start + test_size
        if test_end > n_bars:
            break
        splits.append((train_start, train_end, test_start, test_end))
        train_start += step + embargo
    return splits


# ── Stats ───────────────────────────────────────────────────────────────────
def _profit_factor(pnls: Sequence[float]) -> float:
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    if gross_loss <= 1e-12:
        # No losing trades. Return a large finite number rather than inf so the
        # gate comparison and JSON serialisation stay well-behaved.
        return 999.0 if gross_win > 0 else 0.0
    return gross_win / gross_loss


def _max_drawdown(equity: Sequence[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return max_dd


def _sharpe_sortino(
    equity: Sequence[float], periods_per_year: float
) -> tuple[float | None, float | None]:
    if len(equity) <= 2:
        return None, None
    returns = pd.Series(equity).pct_change().dropna()
    if returns.empty:
        return None, None
    mean = float(returns.mean())
    std = float(returns.std())
    ann = periods_per_year ** 0.5
    sharpe = (mean / std * ann) if std > 1e-12 else None
    downside = returns[returns < 0]
    dstd = float(downside.std()) if len(downside) > 1 else 0.0
    sortino = (mean / dstd * ann) if dstd > 1e-12 else None
    return sharpe, sortino


def _closed_pnls(result: BacktestResult) -> list[float]:
    return [t.pnl for t in result.trades if t.side == "sell" and t.pnl is not None]


def stats_from_result(result: BacktestResult, timeframe: str) -> WindowStats:
    """Derive honest per-window stats from a BacktestResult."""
    pnls = _closed_pnls(result)
    s = WindowStats()
    s.num_trades = len(pnls)
    s.total_pnl = float(sum(pnls))
    if pnls:
        s.win_rate = sum(1 for p in pnls if p > 0) / len(pnls)
        s.expectancy = s.total_pnl / len(pnls)
        s.profit_factor = _profit_factor(pnls)
    s.max_drawdown = _max_drawdown(result.equity_curve)
    s.sharpe, s.sortino = _sharpe_sortino(
        result.equity_curve, _periods_per_year(timeframe)
    )
    return s


# ── Harness ─────────────────────────────────────────────────────────────────
def run_walk_forward(
    ohlcv: pd.DataFrame,
    strategy_config: dict,
    *,
    timeframe: str = "1h",
    train_size: int = 500,
    test_size: int = 200,
    purge: int = 0,
    embargo: int = 0,
    step: int | None = None,
    initial_capital: float = 10_000.0,
    fee_rate: float = MIN_FEE_RATE,
    slippage_bps: float = MIN_SLIPPAGE_BPS,
    thresholds: GateThresholds | None = None,
) -> ValidationReport:
    """
    Run a walk-forward validation and produce an OOS report + pass/fail gate.

    The engine needs warm-up bars, so each test window is simulated on a slice
    that includes the preceding `train` bars for indicator warm-up, but only the
    test-window trades/equity are scored. Costs are clamped to realistic floors.
    Never raises on empty/short data — returns a failing report with a reason.
    """
    thresholds = thresholds or GateThresholds()
    symbol = strategy_config.get("symbol", "UNKNOWN")
    fee_rate = max(fee_rate, MIN_FEE_RATE)
    slippage_bps = max(slippage_bps, MIN_SLIPPAGE_BPS)

    report = ValidationReport(symbol=symbol, timeframe=timeframe)

    n = len(ohlcv)
    # Test window must exceed warm-up or the engine produces no signals.
    if test_size <= _MIN_WARMUP_BARS:
        report.reasons.append(
            f"test_size ({test_size}) must exceed warm-up ({_MIN_WARMUP_BARS})"
        )
        return report

    splits = walk_forward_splits(
        n, train_size, test_size, purge=purge, embargo=embargo, step=step
    )
    if not splits:
        report.reasons.append(
            f"not enough bars ({n}) for train={train_size} + test={test_size}"
        )
        return report

    pooled_pnls: list[float] = []
    pooled_equity: list[float] = []
    profitable_folds = 0

    for idx, (tr_s, tr_e, te_s, te_e) in enumerate(splits):
        # Feed warm-up context: include `train` bars immediately before the test
        # window so indicators are warm, but offset equity so each fold starts at
        # `initial_capital`. We simulate the [train_for_warmup : test_end) slice
        # then keep only bars belonging to the test window.
        warmup_start = max(0, te_s - _MIN_WARMUP_BARS)
        sim_slice = ohlcv.iloc[warmup_start:te_e]
        res = run_backtest(
            sim_slice,
            strategy_config,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
        )
        stats = stats_from_result(res, timeframe)
        report.folds.append(
            FoldResult(
                fold=idx,
                train_start=tr_s,
                train_end=tr_e,
                test_start=te_s,
                test_end=te_e,
                stats=stats,
                result=res,
            )
        )
        pooled_pnls.extend(_closed_pnls(res))
        pooled_equity.extend(res.equity_curve)
        if stats.total_pnl > 0:
            profitable_folds += 1

    # ── Aggregate pooled OOS metrics ────────────────────────────────────────
    report.oos_num_trades = len(pooled_pnls)
    report.oos_total_pnl = float(sum(pooled_pnls))
    if pooled_pnls:
        report.oos_win_rate = sum(1 for p in pooled_pnls if p > 0) / len(pooled_pnls)
        report.oos_expectancy = report.oos_total_pnl / len(pooled_pnls)
        report.oos_profit_factor = _profit_factor(pooled_pnls)
    report.oos_max_drawdown = _max_drawdown(pooled_equity)
    report.oos_sharpe, report.oos_sortino = _sharpe_sortino(
        pooled_equity, _periods_per_year(timeframe)
    )
    report.fold_consistency = profitable_folds / len(splits) if splits else 0.0

    _apply_gate(report, thresholds)
    return report


def _apply_gate(report: ValidationReport, t: GateThresholds) -> None:
    """Set report.passed and accumulate human-readable failure reasons."""
    reasons: list[str] = []

    if report.oos_num_trades < t.min_total_trades:
        reasons.append(
            f"too few OOS trades: {report.oos_num_trades} < {t.min_total_trades}"
        )
    if report.oos_profit_factor < t.min_profit_factor:
        reasons.append(
            f"profit factor {report.oos_profit_factor:.2f} < {t.min_profit_factor}"
        )
    if report.oos_expectancy <= t.min_expectancy:
        reasons.append(
            f"expectancy {report.oos_expectancy:.4f} <= {t.min_expectancy}"
        )
    if report.oos_sharpe is None or report.oos_sharpe < t.min_sharpe:
        shown = "n/a" if report.oos_sharpe is None else f"{report.oos_sharpe:.2f}"
        reasons.append(f"sharpe {shown} < {t.min_sharpe}")
    if report.oos_max_drawdown > t.max_drawdown:
        reasons.append(
            f"max drawdown {report.oos_max_drawdown:.2f} > {t.max_drawdown}"
        )
    if report.fold_consistency < t.min_fold_consistency:
        reasons.append(
            f"fold consistency {report.fold_consistency:.2f} < {t.min_fold_consistency}"
        )

    report.reasons = reasons
    report.passed = not reasons
