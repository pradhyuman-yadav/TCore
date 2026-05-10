from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.db.models import SentimentCache
from app.services.sentiment_agent import score_sentiment


HEADLINES = [
    "Bitcoin surges 10% amid institutional buying",
    "ETF inflows hit record high as market sentiment improves",
    "Crypto adoption accelerates in emerging markets",
]


@pytest.fixture
def mock_claude(mocker):
    mocker.patch(
        "app.services.sentiment_agent._call_claude",
        new=AsyncMock(return_value=(0.75, "Positive headlines dominate.")),
    )


async def test_score_sentiment_returns_float_in_range(mock_claude):
    score = await score_sentiment(HEADLINES, "BTC/USDT")
    assert score is not None
    assert isinstance(score, float)
    assert -1.0 <= score <= 1.0


async def test_score_sentiment_caches_to_db(mock_claude, db_session):
    score = await score_sentiment(HEADLINES, "BTC/USDT", db=db_session)
    assert score == 0.75

    rows = (await db_session.execute(select(SentimentCache))).scalars().all()
    assert len(rows) == 1
    assert rows[0].score == 0.75
    assert rows[0].symbol == "BTC/USDT"


async def test_score_sentiment_uses_cache_when_fresh(mocker, db_session):
    call_mock = mocker.patch(
        "app.services.sentiment_agent._call_claude",
        new=AsyncMock(return_value=(0.5, "Initial call.")),
    )

    await score_sentiment(HEADLINES, "BTC/USDT", db=db_session)
    assert call_mock.call_count == 1

    score = await score_sentiment(HEADLINES, "BTC/USDT", cache_ttl_minutes=15, db=db_session)
    assert score == 0.5
    assert call_mock.call_count == 1


async def test_score_sentiment_returns_none_on_api_error(mocker):
    mocker.patch(
        "app.services.sentiment_agent._call_claude",
        new=AsyncMock(side_effect=Exception("OAuth error")),
    )
    score = await score_sentiment(HEADLINES, "BTC/USDT")
    assert score is None


async def test_score_sentiment_skips_stale_cache(mocker, db_session):
    first_mock = mocker.patch(
        "app.services.sentiment_agent._call_claude",
        new=AsyncMock(return_value=(0.3, "Fresh score.")),
    )

    from app.services.sentiment_agent import _make_hash

    joined = "\n".join(HEADLINES)
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    db_session.add(
        SentimentCache(
            source="news",
            symbol="BTC/USDT",
            raw_content=joined,
            score=0.1,
            reasoning="Stale.",
            model_used="old-model",
            fetched_at=stale_time,
            content_hash=_make_hash(joined),
        )
    )
    await db_session.commit()

    score = await score_sentiment(HEADLINES, "BTC/USDT", cache_ttl_minutes=15, db=db_session)
    assert first_mock.call_count == 1
    assert score == 0.3


async def test_empty_headlines_returns_none(mock_claude):
    score = await score_sentiment([], "BTC/USDT")
    assert score is None
