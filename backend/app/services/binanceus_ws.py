from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import datetime, timezone

import structlog

log = structlog.get_logger()

WS_BASE = "wss://stream.binance.us:9443/stream"

# Map common USDT pairs for reverse lookup
_KNOWN_QUOTES = ("USDT", "USDC", "BUSD", "BTC", "ETH", "BNB", "USD")


def _raw_to_symbol(raw: str) -> str:
    """BTCUSDT -> BTC/USDT (best effort using known quote currencies)."""
    raw = raw.upper()
    for quote in _KNOWN_QUOTES:
        if raw.endswith(quote) and len(raw) > len(quote):
            base = raw[: -len(quote)]
            return f"{base}/{quote}"
    return raw


def _symbol_to_streams(symbol: str) -> list[str]:
    """BTC/USDT -> ['btcusdt@kline_1m', 'btcusdt@trade']"""
    base = symbol.replace("/", "").lower()
    return [f"{base}@kline_1m", f"{base}@trade"]


class BinanceUSStreamClient:
    """
    Connects to Binance US combined WebSocket stream.
    Subscribes to kline_1m + trade streams for all tracked crypto symbols.
    - On kline close: upserts bar to OHLCV table + broadcasts to /ws/prices
    - On trade: broadcasts to /ws/live_trades (no DB storage)
    Auto-reconnects with exponential backoff.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._flush_task: asyncio.Task | None = None
        self._symbols: list[str] = []
        self._running = False
        # Tick buffer for Hawkes OFI — ring buffer capped at 5000, flushed every 2s
        self._tick_buffer: deque[dict] = deque(maxlen=5000)

    def _build_url(self) -> str | None:
        if not self._symbols:
            return None
        streams = []
        for sym in self._symbols:
            streams.extend(_symbol_to_streams(sym))
        return f"{WS_BASE}?streams={'/'.join(streams)}"

    async def start(self, symbols: list[str]) -> None:
        self._symbols = symbols
        self._running = True
        if symbols:
            self._task = asyncio.create_task(self._run_loop())
            self._flush_task = asyncio.create_task(self._flush_loop())
            log.info("binanceus_ws.started", symbols=symbols)

    async def update_subscriptions(self, symbols: list[str]) -> None:
        """Called when watchlist changes — reconnect with new symbol set."""
        self._symbols = symbols
        for task in (self._task, self._flush_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._task = self._flush_task = None
        if self._running and symbols:
            self._task = asyncio.create_task(self._run_loop())
            self._flush_task = asyncio.create_task(self._flush_loop())
            log.info("binanceus_ws.resubscribed", symbols=symbols)
        elif not symbols:
            log.info("binanceus_ws.no_symbols_paused")

    async def stop(self) -> None:
        self._running = False
        for task in (self._task, self._flush_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._task = self._flush_task = None
        log.info("binanceus_ws.stopped")

    async def _run_loop(self) -> None:
        """Main connection loop with exponential backoff retry."""
        import websockets

        delay = 1
        while self._running:
            if not self._symbols:
                await asyncio.sleep(5)
                continue
            url = self._build_url()
            if not url:
                await asyncio.sleep(5)
                continue
            try:
                log.info("binanceus_ws.connecting", symbol_count=len(self._symbols))
                async with websockets.connect(
                    url, ping_interval=20, ping_timeout=10, close_timeout=5
                ) as ws:
                    delay = 1  # reset on successful connect
                    log.info("binanceus_ws.connected")
                    async for raw_msg in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(raw_msg)
                            await self._dispatch(data)
                        except Exception as exc:
                            log.warning("binanceus_ws.parse_error", error=str(exc))
            except asyncio.CancelledError:
                return
            except Exception as exc:
                if not self._running:
                    return
                log.warning("binanceus_ws.disconnected", error=str(exc), retry_in=delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    async def _dispatch(self, data: dict) -> None:
        stream = data.get("stream", "")
        payload = data.get("data", {})
        if "@kline_" in stream:
            await self._on_kline(payload)
        elif "@trade" in stream:
            await self._on_trade(payload)

    async def _on_kline(self, data: dict) -> None:
        from app.ws.manager import ws_manager

        k = data.get("k", {})
        symbol = _raw_to_symbol(data.get("s", ""))
        exchange = "binanceus"

        tick = {
            "type": "tick",
            "symbol": symbol,
            "exchange": exchange,
            "time": k.get("t", 0) // 1000,
            "open": float(k.get("o", 0)),
            "high": float(k.get("h", 0)),
            "low": float(k.get("l", 0)),
            "close": float(k.get("c", 0)),
            "volume": float(k.get("v", 0)),
        }
        await ws_manager.broadcast("prices", tick)

        # Persist only closed candles
        if k.get("x", False):
            from app.db.session import AsyncSessionLocal
            from app.services.data_ingestion import OHLCVRow, upsert_ohlcv

            bar_time = datetime.fromtimestamp(k["t"] / 1000, tz=timezone.utc)
            row = OHLCVRow(
                time=bar_time,
                symbol=symbol,
                exchange=exchange,
                timeframe="1m",  # Binance WS kline_1m stream
                open=float(k["o"]),
                high=float(k["h"]),
                low=float(k["l"]),
                close=float(k["c"]),
                volume=float(k["v"]),
            )
            try:
                async with AsyncSessionLocal() as db:
                    await upsert_ohlcv([row], db)
            except Exception as exc:
                log.warning("binanceus_ws.upsert_error", error=str(exc))

    async def _on_trade(self, data: dict) -> None:
        from app.ws.manager import ws_manager

        symbol = _raw_to_symbol(data.get("s", ""))
        is_buyer_maker = bool(data.get("m", False))

        await ws_manager.broadcast("live_trades", {
            "type": "trade",
            "symbol": symbol,
            "price": float(data.get("p", 0)),
            "qty": float(data.get("q", 0)),
            "isBuyerMaker": is_buyer_maker,
            "time": int(data.get("T", 0)) // 1000,
        })

        # Buffer for Hawkes OFI — classify taker side deterministically
        # m=False → buyer was taker → BUY market order (+1)
        # m=True  → seller was taker → SELL market order (-1)
        trade_time_ms = data.get("T", 0)
        trade_id = data.get("t")  # individual trade ID for dedup
        ts = datetime.fromtimestamp(int(trade_time_ms) / 1000, tz=timezone.utc)
        self._tick_buffer.append({
            "ts":     ts,
            "symbol": symbol,
            "venue":  "binanceus",
            "price":  float(data.get("p", 0)),
            "qty":    float(data.get("q", 0)),
            "side":   -1 if is_buyer_maker else 1,
            "agg_id": int(trade_id) if trade_id is not None else None,
        })

    async def _flush_loop(self) -> None:
        """Flush tick buffer to DB every 2 seconds."""
        try:
            while self._running:
                await asyncio.sleep(2)
                if not self._tick_buffer:
                    continue
                # Drain the deque atomically (single-threaded asyncio — safe)
                ticks: list[dict] = []
                while self._tick_buffer:
                    ticks.append(self._tick_buffer.popleft())
                if ticks:
                    await self._persist_ticks(ticks)
        except asyncio.CancelledError:
            return

    async def _persist_ticks(self, ticks: list[dict]) -> None:
        """Batch insert ticks to tick_trades hypertable."""
        from app.db.session import AsyncSessionLocal
        from app.db.models import TickTrade
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        try:
            async with AsyncSessionLocal() as db:
                stmt = (
                    pg_insert(TickTrade)
                    .values(ticks)
                    .on_conflict_do_nothing()
                )
                await db.execute(stmt)
                await db.commit()
        except Exception as exc:
            log.warning("binanceus_ws.tick_flush_error", error=str(exc), count=len(ticks))


# Module-level singleton
binanceus_stream = BinanceUSStreamClient()
