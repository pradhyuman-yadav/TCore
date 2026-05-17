from __future__ import annotations

import math
from datetime import datetime, timezone
from uuid import UUID

import numpy as np
import pandas as pd
import pandas_ta as ta
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


class IndicatorDef(BaseModel):
    name: str
    weight: float
    params: dict = {}


class IndicatorConfig(BaseModel):
    indicators: list[IndicatorDef]


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, float(v)))


def _rsi(close: pd.Series, params: dict) -> float | None:
    length = params.get("length", 14)
    series = ta.rsi(close, length=length)
    if series is None or series.empty:
        return None
    last = series.iloc[-1]
    if pd.isna(last):
        return None
    return _clamp((float(last) - 50.0) / 50.0)


def _macd_hist(close: pd.Series, params: dict) -> float | None:
    macd = ta.macd(close)
    if macd is None or macd.empty:
        return None
    col = "MACDh_12_26_9"
    if col not in macd.columns:
        return None
    last = macd[col].iloc[-1]
    if pd.isna(last):
        return None
    std = float(close.std())
    if pd.isna(std) or std < 1e-10:
        return None
    return _clamp(math.tanh(float(last) / std * 10.0))


def _bb_position(close: pd.Series, params: dict) -> float | None:
    bbands = ta.bbands(close)
    if bbands is None or bbands.empty:
        return None
    col = "BBP_5_2.0"
    if col not in bbands.columns:
        return None
    pct = bbands[col].iloc[-1]
    if pd.isna(pct):
        return None
    return _clamp((float(pct) - 0.5) * 2.0)


def _volume_surge(close: pd.Series, volume: pd.Series | None, params: dict) -> float | None:
    if volume is None or len(volume) < 20:
        return None
    last = float(volume.iloc[-1])
    mean = float(volume.iloc[-20:].mean())
    if pd.isna(mean) or mean < 1e-10:
        return None
    raw = (last / mean) - 1.0
    return _clamp(math.tanh(raw))


def _ema_cross(close: pd.Series, params: dict) -> float | None:
    fast = params.get("fast", 12)
    slow = params.get("slow", 26)
    ema_f = ta.ema(close, length=fast)
    ema_s = ta.ema(close, length=slow)
    if ema_f is None or ema_s is None:
        return None
    if pd.isna(ema_f.iloc[-1]) or pd.isna(ema_s.iloc[-1]):
        return None
    last_close = float(close.iloc[-1])
    if last_close < 1e-10:
        return None
    raw = (float(ema_f.iloc[-1]) - float(ema_s.iloc[-1])) / last_close
    return _clamp(math.tanh(raw * 100.0))


_DISPATCH = {
    "rsi": _rsi,
    "macd_hist": _macd_hist,
    "bb_position": _bb_position,
    "ema_cross": _ema_cross,
}


def compute_indicators(
    ohlcv: pd.DataFrame,
    config: IndicatorConfig,
) -> dict[str, float | None]:
    """
    Returns {name: normalized_value} for the latest bar only.
    All non-None values are in [-1.0, 1.0]. Never raises.
    """
    close = ohlcv["close"]
    volume = ohlcv.get("volume") if "volume" in ohlcv.columns else None

    result: dict[str, float | None] = {}
    for ind in config.indicators:
        try:
            if ind.name == "volume_surge":
                result[ind.name] = _volume_surge(close, volume, ind.params)
            elif ind.name in _DISPATCH:
                result[ind.name] = _DISPATCH[ind.name](close, ind.params)
            else:
                result[ind.name] = None
        except Exception:
            result[ind.name] = None

    return result


def compute_indicators_vectorized(
    ohlcv: pd.DataFrame,
    config: IndicatorConfig,
) -> pd.DataFrame:
    """
    Compute all indicators on the **full** OHLCV DataFrame in a single pass — O(n).
    Returns a DataFrame with columns = indicator names, same index as ohlcv.
    Values are in [-1, 1]; NaN where warmup data is insufficient.

    Use this in backtests instead of calling compute_indicators() per-bar,
    which is O(n²) and will time out on large datasets.
    """
    close  = ohlcv["close"]
    volume = ohlcv["volume"] if "volume" in ohlcv.columns else None
    out    = pd.DataFrame(index=ohlcv.index)

    for ind in config.indicators:
        name = ind.name
        try:
            if name == "rsi":
                length = ind.params.get("length", 14)
                s = ta.rsi(close, length=length)
                if s is not None:
                    out[name] = ((s - 50.0) / 50.0).clip(-1.0, 1.0)

            elif name == "macd_hist":
                macd = ta.macd(close)
                mcol = "MACDh_12_26_9"
                if macd is not None and mcol in macd.columns:
                    # Rolling std up to each bar — avoids look-ahead in normalisation
                    roll_std = close.expanding(min_periods=2).std()
                    roll_std = roll_std.where(roll_std > 1e-10).ffill().fillna(1.0)
                    out[name] = np.tanh(macd[mcol] / roll_std * 10.0).clip(-1.0, 1.0)

            elif name == "bb_position":
                bbands = ta.bbands(close)
                bcol = "BBP_5_2.0"
                if bbands is not None and bcol in bbands.columns:
                    out[name] = ((bbands[bcol] - 0.5) * 2.0).clip(-1.0, 1.0)

            elif name == "volume_surge":
                if volume is not None:
                    mean20 = volume.rolling(20, min_periods=1).mean().clip(lower=1e-10)
                    out[name] = np.tanh((volume / mean20) - 1.0).clip(-1.0, 1.0)

            elif name == "ema_cross":
                fast = ind.params.get("fast", 12)
                slow = ind.params.get("slow", 26)
                ema_f = ta.ema(close, length=fast)
                ema_s = ta.ema(close, length=slow)
                if ema_f is not None and ema_s is not None:
                    raw = (ema_f - ema_s) / close.clip(lower=1e-10)
                    out[name] = np.tanh(raw * 100.0).clip(-1.0, 1.0)

        except Exception:
            pass  # column absent → treated as None in run_backtest

    return out


async def snapshot_indicators(
    symbol: str,
    strategy_id: UUID,
    values: dict[str, float | None],
    weights: dict[str, float],
    db: AsyncSession,
) -> None:
    from app.db.models import IndicatorSnapshot
    from app.state import app_state

    now = datetime.now(timezone.utc)

    for name, value in values.items():
        if value is None:
            continue
        weight = weights.get(name, 0.0)
        db.add(
            IndicatorSnapshot(
                time=now,
                symbol=symbol,
                strategy_id=strategy_id,
                indicator_name=name,
                value=value,
                weight=weight,
                weighted_value=value * weight,
            )
        )

    await db.commit()

    if symbol not in app_state.indicator_values:
        app_state.indicator_values[symbol] = {}
    for name, value in values.items():
        if value is not None:
            app_state.indicator_values[symbol][name] = value
