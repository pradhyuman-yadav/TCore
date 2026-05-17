from __future__ import annotations

import asyncio
import structlog
from datetime import datetime, timezone

log = structlog.get_logger()


def _to_yfinance_symbol(symbol: str, asset_type: str) -> str:
    """Convert our symbol format to yfinance ticker.
    - us_stock:     "AAPL"      -> "AAPL"
    - indian_stock: "RELIANCE"  -> "RELIANCE.NS"
    """
    if asset_type == "indian_stock" and not symbol.endswith((".NS", ".BO")):
        return f"{symbol}.NS"
    return symbol


def _fetch_yf_sync(yf_symbol: str) -> dict | None:
    """Synchronous yfinance fetch — must be run in a thread pool."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period="2d", interval="1d")
        if hist.empty:
            return None
        latest = hist.iloc[-1]
        ts = hist.index[-1]
        # Ensure timezone-aware datetime
        if hasattr(ts, "to_pydatetime"):
            dt = ts.to_pydatetime()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = datetime.now(timezone.utc)
        return {
            "time": dt,
            "open": float(latest["Open"]),
            "high": float(latest["High"]),
            "low": float(latest["Low"]),
            "close": float(latest["Close"]),
            "volume": float(latest["Volume"]),
        }
    except Exception as exc:
        log.warning("stock_feed.fetch_error", symbol=yf_symbol, error=str(exc))
        return None


async def fetch_yfinance_history(
    symbol: str,
    asset_type: str,
    period: str = "1y",
    interval: str = "1d",
) -> list[dict]:
    """Fetch historical OHLCV bars from yfinance. Returns list of bar dicts."""
    yf_sym = _to_yfinance_symbol(symbol, asset_type)
    loop = asyncio.get_event_loop()

    def _fetch() -> list[dict]:
        try:
            import yfinance as yf

            hist = yf.Ticker(yf_sym).history(period=period, interval=interval)
            if hist.empty:
                return []
            rows = []
            for ts, row in hist.iterrows():
                dt = ts.to_pydatetime()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                rows.append({
                    "time": dt,
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]),
                })
            return rows
        except Exception as exc:
            log.warning("stock_feed.history_error", symbol=yf_sym, error=str(exc))
            return []

    return await loop.run_in_executor(None, _fetch)


async def poll_stock_prices() -> None:
    """APScheduler job: poll latest prices for all non-crypto watched symbols."""
    from app.db.session import AsyncSessionLocal
    from app.services.data_ingestion import OHLCVRow, upsert_ohlcv
    from app.state import app_state
    from app.ws.manager import ws_manager

    stock_symbols = [
        s for s in app_state.watched_symbols if s.get("asset_type") != "crypto"
    ]
    if not stock_symbols:
        return

    loop = asyncio.get_event_loop()
    rows_to_upsert: list[OHLCVRow] = []

    for sym_info in stock_symbols:
        symbol = sym_info["symbol"]
        exchange = sym_info["exchange"]
        asset_type = sym_info["asset_type"]
        yf_sym = _to_yfinance_symbol(symbol, asset_type)

        bar = await loop.run_in_executor(None, _fetch_yf_sync, yf_sym)
        if not bar:
            continue

        row = OHLCVRow(
            time=bar["time"],
            symbol=symbol,
            exchange=exchange,
            timeframe="1d",  # yfinance daily poll
            open=bar["open"],
            high=bar["high"],
            low=bar["low"],
            close=bar["close"],
            volume=bar["volume"],
        )
        rows_to_upsert.append(row)

        await ws_manager.broadcast("prices", {
            "type": "tick",
            "symbol": symbol,
            "exchange": exchange,
            "time": int(bar["time"].timestamp()),
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
            "volume": bar["volume"],
        })

    if rows_to_upsert:
        try:
            async with AsyncSessionLocal() as db:
                await upsert_ohlcv(rows_to_upsert, db)
            log.info("stock_feed.upserted", count=len(rows_to_upsert))
        except Exception as exc:
            log.warning("stock_feed.upsert_error", error=str(exc))
