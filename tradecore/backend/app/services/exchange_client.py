from __future__ import annotations

from app.config import settings


class ExchangeClient:
    def __init__(self, exchange_id: str, api_key: str = "", secret: str = ""):
        import ccxt.async_support as ccxt  # lazy import — not needed in tests

        self._exchange = getattr(ccxt, exchange_id)(
            {"apiKey": api_key, "secret": secret}
        )

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int | None = None
    ) -> list:
        return await self._exchange.fetch_ohlcv(
            symbol, timeframe, since=since, limit=limit
        )

    async def fetch_ticker(self, symbol: str) -> dict:
        return await self._exchange.fetch_ticker(symbol)

    async def create_order(
        self, symbol: str, type: str, side: str, amount: float, price: float | None = None
    ) -> dict:
        return await self._exchange.create_order(symbol, type, side, amount, price)

    async def close(self) -> None:
        await self._exchange.close()


_client: ExchangeClient | None = None


def get_exchange_client() -> ExchangeClient:
    global _client
    if _client is None:
        _client = ExchangeClient(
            exchange_id=settings.ccxt_exchange,
            api_key=settings.ccxt_api_key,
            secret=settings.ccxt_secret,
        )
    return _client
