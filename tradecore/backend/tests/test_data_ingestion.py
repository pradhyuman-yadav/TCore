from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.services.data_ingestion import (
    NewsItem,
    OHLCVRow,
    fetch_news_headlines,
    fetch_ohlcv,
    upsert_ohlcv,
)


def make_ohlcv_row(offset: int, close: float = 40000.0) -> OHLCVRow:
    return OHLCVRow(
        time=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=offset),
        symbol="BTC/USDT",
        exchange="binance",
        open=40000.0,
        high=41000.0,
        low=39000.0,
        close=close,
        volume=100.0,
    )


@pytest.fixture
def mock_exchange_client(mocker):
    mock_client = mocker.MagicMock()
    mock_client.fetch_ohlcv = mocker.AsyncMock()
    mock_client.fetch_ticker = mocker.AsyncMock()
    mock_client.create_order = mocker.AsyncMock()
    mocker.patch(
        "app.services.data_ingestion.get_exchange_client",
        return_value=mock_client,
    )
    return mock_client


@pytest.fixture
def mock_openbb(mocker):
    mock = mocker.AsyncMock()
    mocker.patch("app.services.data_ingestion._fetch_openbb_news", mock)
    return mock


@pytest.fixture
async def db_with_ohlcv(db_session):
    rows = [make_ohlcv_row(i) for i in range(5)]
    await upsert_ohlcv(rows, db_session)
    return db_session


async def test_fetch_ohlcv_returns_ohlcvrow_list(mock_exchange_client):
    mock_exchange_client.fetch_ohlcv.return_value = [
        [1700000000000, 40000, 41000, 39000, 40500, 100.0]
    ]
    rows = await fetch_ohlcv("BTC/USDT", "binance", "1h", since=datetime(2024, 1, 1))
    assert len(rows) == 1
    assert isinstance(rows[0], OHLCVRow)
    assert rows[0].symbol == "BTC/USDT"


async def test_upsert_ohlcv_inserts_rows(db_session):
    rows = [make_ohlcv_row(i) for i in range(10)]
    count = await upsert_ohlcv(rows, db_session)
    assert count == 10


async def test_upsert_ohlcv_deduplicates_on_conflict(db_session):
    rows = [make_ohlcv_row(0)]
    await upsert_ohlcv(rows, db_session)
    await upsert_ohlcv(rows, db_session)
    result = await db_session.execute(text("SELECT COUNT(*) FROM ohlcv"))
    assert result.scalar() == 1


async def test_upsert_updates_price_on_conflict(db_session):
    row = make_ohlcv_row(0, close=40000)
    await upsert_ohlcv([row], db_session)
    row.close = 41000
    await upsert_ohlcv([row], db_session)
    result = await db_session.execute(text("SELECT close FROM ohlcv LIMIT 1"))
    assert result.scalar() == 41000


async def test_fetch_news_returns_newsitems(mock_openbb):
    mock_openbb.return_value = [
        {
            "title": "BTC up",
            "source": "reuters",
            "published_at": "2024-01-01T00:00:00Z",
        }
    ]
    items = await fetch_news_headlines("BTC", limit=5)
    assert len(items) == 1
    assert isinstance(items[0], NewsItem)


async def test_market_ohlcv_endpoint(client, db_with_ohlcv):
    resp = await client.get(
        "/market/ohlcv?symbol=BTC/USDT&exchange=binance&timeframe=1h&limit=10"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) <= 10
    assert all("close" in row for row in data)
