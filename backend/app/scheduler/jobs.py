from __future__ import annotations

from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.services.aggregator import classify_zone, compute_composite_score, snapshot_composite
from app.services.data_ingestion import fetch_news_headlines
from app.services.execution import execute_signal
from app.services.indicator_engine import compute_indicators, snapshot_indicators
from app.services.rule_engine import evaluate_rules
from app.services.sentiment_agent import score_sentiment
from app.state import app_state

log = structlog.get_logger()

_DEFAULT_CADENCE = 300  # seconds


async def _load_ohlcv_df(symbol: str, exchange: str, timeframe: str, db):
    import pandas as pd
    from app.db.models import OHLCV

    rows = (
        await db.execute(
            select(OHLCV)
            .where(
                OHLCV.symbol == symbol,
                OHLCV.exchange == exchange,
                OHLCV.timeframe == timeframe,
            )
            .order_by(OHLCV.time.asc())
            .limit(500)
        )
    ).scalars().all()

    if not rows:
        return None

    return pd.DataFrame(
        [
            {
                "time": r.time,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ]
    )


async def _count_open_positions(symbol: str, exchange: str, mode: str, db) -> int:
    from app.db.models import Position

    rows = (
        await db.execute(
            select(Position).where(
                Position.symbol == symbol,
                Position.exchange == exchange,
                Position.mode == mode,
                Position.is_open == True,
            )
        )
    ).scalars().all()
    return len(rows)


_SHORT_TO_FULL = {
    "macd":    "macd_hist",
    "bb":      "bb_position",
    "ema":     "ema_cross",
    "volume":  "volume_surge",
}


def _build_indicator_config(strategy: dict):
    from app.services.indicator_engine import IndicatorConfig, IndicatorDef

    tech_names = {"rsi", "macd_hist", "bb_position", "volume_surge", "ema_cross"}
    defs = []

    # Support both formats:
    #   new: strategy["indicators"] = {name: {weight: ..., ...params}}
    #   legacy (StrategyBuilder): strategy["weights"] = {short_name: float}
    indicators_cfg = strategy.get("indicators")
    if indicators_cfg:
        for name, cfg in indicators_cfg.items():
            full_name = _SHORT_TO_FULL.get(name, name)
            if full_name not in tech_names:
                continue
            weight = float(cfg.get("weight", 0.0)) if isinstance(cfg, dict) else 0.0
            params = {k: v for k, v in (cfg.items() if isinstance(cfg, dict) else {}.items()) if k not in ("weight", "cache_ttl_minutes")}
            defs.append(IndicatorDef(name=full_name, weight=weight, params=params))
    else:
        # Legacy flat weights dict from StrategyBuilder
        weights_cfg = strategy.get("weights", {})
        for name, weight in weights_cfg.items():
            full_name = _SHORT_TO_FULL.get(name, name)
            if full_name not in tech_names:
                continue
            defs.append(IndicatorDef(name=full_name, weight=float(weight), params={}))
    return IndicatorConfig(indicators=defs)


async def run_trading_cycle() -> None:
    """Main trading loop: fetch → indicators → sentiment → aggregate → rules → execute."""
    if app_state.kill_switch:
        return

    strategy = app_state.active_strategy
    if not strategy:
        return

    symbol: str = strategy.get("symbol", "")
    exchange: str = strategy.get("exchange", "")
    timeframe: str = strategy.get("timeframe", "1m")
    if not symbol or not exchange:
        return

    from uuid import UUID

    try:
        strategy_id_raw = strategy.get("id")
        strategy_id = UUID(strategy_id_raw) if strategy_id_raw else None

        async with AsyncSessionLocal() as db:
            # 1. Load OHLCV filtered by the strategy's configured timeframe
            ohlcv_df = await _load_ohlcv_df(symbol, exchange, timeframe, db)
            if ohlcv_df is None or len(ohlcv_df) < 30:
                log.info("trading_cycle.insufficient_ohlcv", symbol=symbol, rows=0 if ohlcv_df is None else len(ohlcv_df))
                return

            # 2. Technical indicators
            indicator_config = _build_indicator_config(strategy)
            indicator_values: dict = compute_indicators(ohlcv_df, indicator_config)
            weights: dict = {ind.name: ind.weight for ind in indicator_config.indicators}

            # 3. Sentiment indicators
            indicators_cfg = strategy.get("indicators", {})
            for sent_name in ("news_sentiment", "social_sentiment"):
                if sent_name not in indicators_cfg:
                    continue
                cfg = indicators_cfg[sent_name]
                weight = float(cfg.get("weight", 0.0)) if isinstance(cfg, dict) else 0.0
                ttl = int(cfg.get("cache_ttl_minutes", 15)) if isinstance(cfg, dict) else 15
                weights[sent_name] = weight
                try:
                    headlines = await fetch_news_headlines(symbol.split("/")[0], limit=10)
                    texts = [h.title for h in headlines]
                    sent_score = await score_sentiment(texts, symbol, source=sent_name, cache_ttl_minutes=ttl, db=db)
                    indicator_values[sent_name] = sent_score
                except Exception:
                    indicator_values[sent_name] = None

            # 4. Snapshot indicators
            if strategy_id:
                await snapshot_indicators(symbol, strategy_id, indicator_values, weights, db)

            # 5. Composite score
            composite = compute_composite_score(indicator_values, weights)
            if composite is None:
                log.info("trading_cycle.no_composite_score", symbol=symbol)
                return

            # StrategyBuilder saves thresholds at config root; legacy format stores
            # them under "rules".  Read root first, fall back to "rules" sub-dict.
            rules_cfg = strategy.get("rules", {})
            raw_buy = strategy.get("buy_threshold") or rules_cfg.get("buy_threshold", 0.45)
            raw_sell = strategy.get("sell_threshold") or rules_cfg.get("sell_threshold", 0.35)
            # sell_threshold in StrategyBuilder is stored as a positive magnitude;
            # classify_zone expects a negative value (sell when score < -X)
            buy_threshold  = float(raw_buy)
            sell_threshold = -abs(float(raw_sell))
            zone = classify_zone(
                composite,
                buy_threshold=buy_threshold,
                sell_threshold=sell_threshold,
            )

            if strategy_id:
                await snapshot_composite(symbol, strategy_id, composite, zone, db)

            # 6. Rule evaluation
            mode = app_state.trading_mode
            open_positions = await _count_open_positions(symbol, exchange, mode, db)
            signal = evaluate_rules(
                zone=zone,
                kill_switch=app_state.kill_switch,
                open_positions=open_positions,
                daily_pnl=app_state.daily_pnl.get(mode, 0.0),
                strategy_config=strategy,
            )

            log.info(
                "trading_cycle.signal",
                symbol=symbol,
                zone=zone,
                score=round(composite, 4),
                action=signal.action,
            )

            # 6b. Persist signal to DB (committed independently so it survives execute errors)
            from app.db.models import Signal as SignalRecord
            db.add(SignalRecord(
                symbol=symbol,
                exchange=exchange,
                zone=zone,
                score=composite,
                action=signal.action.upper(),
                reason=signal.reason,
                strategy_id=strategy_id,
            ))
            await db.commit()

            # 7. Execute
            if strategy_id:
                await execute_signal(signal, symbol, exchange, strategy_id, composite, db)

    except Exception as exc:
        log.error("trading_cycle.error", error=str(exc))


async def cleanup_old_ohlcv() -> None:
    """Daily job: delete OHLCV rows older than 1 year."""
    from datetime import timedelta

    from sqlalchemy import delete

    from app.db.models import OHLCV
    from app.db.session import AsyncSessionLocal

    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(delete(OHLCV).where(OHLCV.time < cutoff))
            await db.commit()
            log.info("ohlcv.cleanup", deleted_rows=result.rowcount)
    except Exception as exc:
        log.error("ohlcv.cleanup_error", error=str(exc))


async def poll_stock_prices_job() -> None:
    """60s job: poll yfinance prices for non-crypto watched symbols."""
    from app.services.stock_feed import poll_stock_prices

    await poll_stock_prices()


async def refresh_news_job() -> None:
    """30-min job: fetch news from OpenBB + RSS and upsert to news_items."""
    import hashlib
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.db.models import FeedSource, NewsItem
    from app.services.news_aggregator import fetch_combined_news

    crypto_symbols = [
        s["symbol"] for s in app_state.watched_symbols if s["asset_type"] == "crypto"
    ]
    try:
        # Build source_name → category map from DB
        source_category: dict[str, str] = {}
        async with AsyncSessionLocal() as db:
            feed_rows = (await db.execute(
                select(FeedSource).where(FeedSource.type == "rss_news", FeedSource.is_active == True)
            )).scalars().all()
            for r in feed_rows:
                if r.category:
                    source_category[r.name.lower()] = r.category
        # OpenBB items are always crypto-focused
        source_category["openbb"] = "crypto"

        items = await fetch_combined_news(symbols=crypto_symbols or None, limit=100)
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            for item in items:
                title = (item.get("title") or "").strip()
                if not title:
                    continue
                ch = hashlib.md5(title.encode()).hexdigest()
                src = (item.get("source") or "").lower()
                category = next(
                    (v for k, v in source_category.items() if k in src or src in k),
                    None
                )
                stmt = pg_insert(NewsItem).values(
                    title=title,
                    source=item.get("source"),
                    published_at=item.get("published_at"),
                    url=item.get("url"),
                    summary=(item.get("summary") or "")[:500],
                    category=category,
                    content_hash=ch,
                    fetched_at=now,
                ).on_conflict_do_update(
                    index_elements=["content_hash"],
                    set_={
                        "fetched_at": now,
                        "url": item.get("url"),
                        "summary": (item.get("summary") or "")[:500],
                        "category": category,
                    },
                )
                await db.execute(stmt)
            await db.commit()
        log.info("news.refreshed", count=len(items))
    except Exception as exc:
        log.error("news.refresh_error", error=str(exc))


async def refresh_social_job() -> None:
    """15-min job: fetch social posts (Reddit + RSS) and upsert to social_posts."""
    import hashlib
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.db.models import SocialPost
    from app.services.social_aggregator import fetch_reddit_posts, fetch_rss_posts

    now = datetime.now(timezone.utc)
    try:
        async with AsyncSessionLocal() as db:
            # Reddit: all three categories
            for cat in ("crypto", "us_stock", "indian_stock"):
                posts = await fetch_reddit_posts(category=cat, limit_per_sub=20)
                for item in posts:
                    title = (item.get("title") or "").strip()
                    if not title:
                        continue
                    url = item.get("url")
                    ch = hashlib.md5((url or title).encode()).hexdigest()
                    pub = item.get("published_at")
                    stmt = pg_insert(SocialPost).values(
                        platform="reddit",
                        source=item.get("source"),
                        title=title,
                        url=url,
                        upvotes=item.get("score", 0),
                        comments=item.get("comments", 0),
                        published_at=pub,
                        category=cat,
                        content_hash=ch,
                        fetched_at=now,
                    ).on_conflict_do_update(
                        index_elements=["content_hash"],
                        set_={"upvotes": item.get("score", 0), "comments": item.get("comments", 0), "fetched_at": now, "category": cat},
                    )
                    await db.execute(stmt)

            # RSS: crypto + stock feeds
            for feed_category in ("crypto", "us_stock"):
                rss_posts = await fetch_rss_posts(category=feed_category)
                for item in rss_posts:
                    title = (item.get("title") or "").strip()
                    if not title:
                        continue
                    url = item.get("url")
                    ch = hashlib.md5((url or title).encode()).hexdigest()
                    pub = item.get("published_at")
                    stmt = pg_insert(SocialPost).values(
                        platform="rss",
                        source=item.get("source"),
                        title=title,
                        url=url,
                        upvotes=0,
                        comments=0,
                        published_at=pub,
                        category=feed_category,
                        content_hash=ch,
                        fetched_at=now,
                    ).on_conflict_do_update(
                        index_elements=["content_hash"],
                        set_={"fetched_at": now, "category": feed_category},
                    )
                    await db.execute(stmt)

            await db.commit()
        log.info("social.refreshed")
    except Exception as exc:
        log.error("social.refresh_error", error=str(exc))


async def refit_hawkes_job() -> None:
    """30-min job: refit Hawkes OFI model for all active crypto watched symbols."""
    from app.services.hawkes_ofi import fit_model

    crypto_symbols = [s for s in app_state.watched_symbols if s["asset_type"] == "crypto"]
    if not crypto_symbols:
        return

    for sym_info in crypto_symbols:
        symbol = sym_info["symbol"]
        venue  = sym_info["exchange"]
        try:
            async with AsyncSessionLocal() as db:
                params = await fit_model(symbol, venue, db)
            if params is not None:
                app_state.hawkes_regime[symbol] = params.regime
                log.info("hawkes.refitted",
                         symbol=symbol,
                         branching=round(params.branching, 4),
                         regime=params.regime)
        except Exception as exc:
            log.error("hawkes.refit_error", symbol=symbol, error=str(exc))


async def cleanup_tick_trades_job() -> None:
    """Daily job: delete tick_trades rows older than 24 hours."""
    from datetime import timedelta
    from sqlalchemy import delete
    from app.db.models import TickTrade

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(delete(TickTrade).where(TickTrade.ts < cutoff))
            await db.commit()
            log.info("tick_trades.cleanup", deleted_rows=result.rowcount)
    except Exception as exc:
        log.error("tick_trades.cleanup_error", error=str(exc))


def setup_scheduler(scheduler: AsyncIOScheduler) -> None:
    import os
    _in_test = bool(os.getenv("PYTEST_CURRENT_TEST"))

    cadence = _DEFAULT_CADENCE
    strategy = app_state.active_strategy
    if strategy:
        cadence = int(strategy.get("refresh_cadence_seconds", _DEFAULT_CADENCE))

    scheduler.add_job(
        run_trading_cycle,
        trigger="interval",
        seconds=cadence,
        id="trading_cycle",
        replace_existing=True,
        misfire_grace_time=120,  # sentiment LLM calls can take 10-30s
    )

    scheduler.add_job(
        cleanup_old_ohlcv,
        trigger="cron",
        hour=2,
        minute=0,
        id="ohlcv_cleanup",
        replace_existing=True,
        misfire_grace_time=300,
    )

    scheduler.add_job(
        poll_stock_prices_job,
        trigger="interval",
        seconds=300,  # yfinance returns daily bars — polling every 60s was wasteful
        id="stock_prices",
        replace_existing=True,
        misfire_grace_time=60,
    )

    scheduler.add_job(
        refresh_news_job,
        trigger="interval",
        minutes=30,
        id="news_refresh",
        replace_existing=True,
        next_run_time=None if _in_test else datetime.now(timezone.utc),
        misfire_grace_time=300,
    )

    scheduler.add_job(
        refresh_social_job,
        trigger="interval",
        minutes=15,
        id="social_refresh",
        replace_existing=True,
        next_run_time=None if _in_test else datetime.now(timezone.utc),
        misfire_grace_time=180,
    )

    scheduler.add_job(
        refit_hawkes_job,
        trigger="interval",
        minutes=30,
        id="hawkes_refit",
        replace_existing=True,
        next_run_time=None if _in_test else datetime.now(timezone.utc),
        misfire_grace_time=300,
    )

    scheduler.add_job(
        cleanup_tick_trades_job,
        trigger="cron",
        hour=3,
        minute=0,
        id="tick_trades_cleanup",
        replace_existing=True,
        misfire_grace_time=300,
    )

    log.info("scheduler.job_registered", cadence_seconds=cadence)
