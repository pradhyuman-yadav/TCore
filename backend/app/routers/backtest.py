import asyncio
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OHLCV
from app.db.session import get_db
from app.services.backtest_runner import run_backtest
from app.services.validation import GateThresholds, run_walk_forward
from app.state import app_state

router = APIRouter(prefix="/backtest")

MAX_BARS = 2_000          # hard cap — prevents O(n²) timeout
MAX_VALIDATE_BARS = 10_000  # walk-forward needs many folds -> larger cap
_PREFETCH_DAYS = 90       # how far back to auto-fetch (enough for any meaningful test)
_PREFETCH_TIMEOUT = 20.0  # seconds before we give up and return a clear error


class BacktestRequest(BaseModel):
    symbol: str
    exchange: str
    timeframe: str = "1h"
    initial_capital: float = Field(10_000.0, gt=0)
    fee_rate: float = Field(0.001, ge=0, le=0.05)
    slippage_bps: float = Field(0.0, ge=0, le=500)
    date_from: str | None = None  # ISO date string, e.g. "2024-01-01"
    date_to:   str | None = None  # ISO date string, e.g. "2024-06-01"
    strategy_config: dict | None = None  # uses active strategy if None


class ValidateRequest(BaseModel):
    """Walk-forward validation request. Reuses the same data-load path as /run."""
    symbol: str
    exchange: str
    timeframe: str = "1h"
    initial_capital: float = Field(10_000.0, gt=0)
    fee_rate: float = Field(0.001, ge=0, le=0.05)
    slippage_bps: float = Field(2.0, ge=0, le=500)
    date_from: str | None = None
    date_to: str | None = None
    strategy_config: dict | None = None

    # Walk-forward window sizing (in bars)
    train_size: int = Field(500, gt=0)
    test_size: int = Field(200, gt=0)
    purge: int = Field(0, ge=0)
    embargo: int = Field(0, ge=0)

    # Optional gate-threshold overrides (None -> use GateThresholds defaults)
    min_total_trades: int | None = None
    min_profit_factor: float | None = None
    min_sharpe: float | None = None
    max_drawdown: float | None = None
    min_fold_consistency: float | None = None


async def _do_prefetch(
    symbol: str,
    exchange: str,
    timeframe: str,
    asset_type: str,
    db: AsyncSession,
) -> int:
    """Inner prefetch — called with a timeout wrapper. Returns rows upserted."""
    import structlog
    log = structlog.get_logger()
    since = datetime.now(timezone.utc) - timedelta(days=_PREFETCH_DAYS)

    if asset_type == "crypto":
        from app.services.data_ingestion import fetch_ohlcv, upsert_ohlcv
        rows = await fetch_ohlcv(symbol, exchange, timeframe, since=since)
        if rows:
            await upsert_ohlcv(rows, db)
            log.info("backtest.prefetch_done", symbol=symbol, upserted=len(rows))
            return len(rows)
    else:
        from app.services.stock_feed import fetch_yfinance_history
        from app.services.data_ingestion import OHLCVRow, upsert_ohlcv
        _tf_map = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                   "1h": "1h", "4h": "1h", "1d": "1d"}
        yf_interval = _tf_map.get(timeframe, "1d")
        bars = await fetch_yfinance_history(symbol, asset_type, period="3mo", interval=yf_interval)
        if bars:
            ohlcv_rows = [
                OHLCVRow(
                    time=b["time"], symbol=symbol, exchange=exchange, timeframe=timeframe,
                    open=b["open"], high=b["high"], low=b["low"],
                    close=b["close"], volume=b["volume"],
                )
                for b in bars
            ]
            await upsert_ohlcv(ohlcv_rows, db)
            log.info("backtest.prefetch_done", symbol=symbol, upserted=len(ohlcv_rows))
            return len(ohlcv_rows)
    return 0


async def _prefetch_if_needed(
    symbol: str,
    exchange: str,
    timeframe: str,
    db: AsyncSession,
    min_bars: int = 31,
) -> int:
    """
    If DB has fewer than min_bars, attempt a quick prefetch (capped at
    _PREFETCH_DAYS days, _PREFETCH_TIMEOUT seconds). Returns updated count.
    On timeout or error, logs a warning and returns the original count —
    the caller will raise a friendly 422.
    """
    import structlog
    log = structlog.get_logger()

    count = (
        await db.execute(
            select(func.count()).where(
                OHLCV.symbol == symbol,
                OHLCV.exchange == exchange,
                OHLCV.timeframe == timeframe,
            )
        )
    ).scalar_one()

    if count >= min_bars:
        return count

    log.info("backtest.prefetch_start", symbol=symbol, exchange=exchange,
             timeframe=timeframe, have=count, fetching_days=_PREFETCH_DAYS)

    watched   = {s["symbol"]: s for s in app_state.watched_symbols}
    sym_info  = watched.get(symbol, {})
    asset_type = sym_info.get("asset_type", "crypto")

    try:
        upserted = await asyncio.wait_for(
            _do_prefetch(symbol, exchange, timeframe, asset_type, db),
            timeout=_PREFETCH_TIMEOUT,
        )
        return count + upserted
    except asyncio.TimeoutError:
        log.warning("backtest.prefetch_timeout", symbol=symbol,
                    timeout=_PREFETCH_TIMEOUT)
    except Exception as exc:
        log.warning("backtest.prefetch_error", symbol=symbol, error=str(exc))

    return count


async def _resolve_strategy(strategy_config: dict | None) -> dict:
    if strategy_config is not None:
        return strategy_config
    if app_state.active_strategy is None:
        raise HTTPException(
            status_code=400,
            detail="No active strategy and no strategy_config provided",
        )
    return app_state.active_strategy


async def _load_ohlcv_df(
    body: "BacktestRequest | ValidateRequest",
    db: AsyncSession,
    *,
    cap_bars: int | None = MAX_BARS,
) -> tuple[pd.DataFrame, int]:
    """
    Shared loader: prefetch-if-needed, apply date filters, query, optionally cap
    to the most recent `cap_bars`, and return (DataFrame, raw_row_count).
    Raises a friendly 422 when there is not enough data.
    """
    await _prefetch_if_needed(body.symbol, body.exchange, body.timeframe, db)

    filters = [
        OHLCV.symbol == body.symbol,
        OHLCV.exchange == body.exchange,
        OHLCV.timeframe == body.timeframe,
    ]
    if body.date_from:
        filters.append(OHLCV.time >= datetime.fromisoformat(body.date_from).replace(tzinfo=timezone.utc))
    if body.date_to:
        filters.append(OHLCV.time <= datetime.fromisoformat(body.date_to).replace(tzinfo=timezone.utc))

    rows = (
        await db.execute(select(OHLCV).where(*filters).order_by(OHLCV.time.asc()))
    ).scalars().all()

    if len(rows) < 31:
        date_hint = ""
        if body.date_from or body.date_to:
            date_hint = f" in range {body.date_from or '…'} – {body.date_to or '…'}"
        raise HTTPException(
            status_code=422,
            detail=(
                f"No data for {body.symbol} / {body.timeframe}{date_hint}. "
                f"Go to ChartView → select {body.symbol} → click ⟳ DB Sync to load historical bars first."
            ),
        )

    raw_count = len(rows)
    if cap_bars is not None and raw_count > cap_bars:
        rows = rows[-cap_bars:]

    df = pd.DataFrame(
        [
            {
                "time": r.time, "open": r.open, "high": r.high,
                "low": r.low, "close": r.close, "volume": r.volume,
            }
            for r in rows
        ]
    ).set_index("time")
    return df, raw_count


@router.post("/run")
async def run_backtest_endpoint(
    body: BacktestRequest,
    db: AsyncSession = Depends(get_db),
):
    strategy_config = await _resolve_strategy(body.strategy_config)
    df, raw_count = await _load_ohlcv_df(body, db)

    result = run_backtest(
        df,
        strategy_config,
        initial_capital=body.initial_capital,
        fee_rate=body.fee_rate,
        slippage_bps=body.slippage_bps,
    )
    out = result.to_dict()
    out["bars_used"] = len(df)
    out["bars_capped"] = raw_count > MAX_BARS  # true only if we actually truncated
    return out


@router.post("/validate")
async def validate_strategy_endpoint(
    body: ValidateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Walk-forward / purged validation. Returns aggregated out-of-sample metrics
    and a deterministic pass/fail gate. A strategy must clear this before being
    promoted to (paper or live) trading.
    """
    strategy_config = await _resolve_strategy(body.strategy_config)
    df, raw_count = await _load_ohlcv_df(body, db, cap_bars=MAX_VALIDATE_BARS)

    # Build gate thresholds, overriding only the fields the caller supplied.
    base = GateThresholds()
    thresholds = GateThresholds(
        min_total_trades=body.min_total_trades if body.min_total_trades is not None else base.min_total_trades,
        min_profit_factor=body.min_profit_factor if body.min_profit_factor is not None else base.min_profit_factor,
        min_sharpe=body.min_sharpe if body.min_sharpe is not None else base.min_sharpe,
        max_drawdown=body.max_drawdown if body.max_drawdown is not None else base.max_drawdown,
        min_fold_consistency=body.min_fold_consistency if body.min_fold_consistency is not None else base.min_fold_consistency,
    )

    report = run_walk_forward(
        df,
        strategy_config,
        timeframe=body.timeframe,
        train_size=body.train_size,
        test_size=body.test_size,
        purge=body.purge,
        embargo=body.embargo,
        initial_capital=body.initial_capital,
        fee_rate=body.fee_rate,
        slippage_bps=body.slippage_bps,
        thresholds=thresholds,
    )
    out = report.to_dict()
    out["bars_used"] = len(df)
    out["bars_capped"] = raw_count > MAX_VALIDATE_BARS
    return out
