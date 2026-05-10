from __future__ import annotations

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


async def _load_ohlcv_df(symbol: str, exchange: str, db):
    import pandas as pd
    from app.db.models import OHLCV

    rows = (
        await db.execute(
            select(OHLCV)
            .where(OHLCV.symbol == symbol, OHLCV.exchange == exchange)
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


def _build_indicator_config(strategy: dict):
    from app.services.indicator_engine import IndicatorConfig, IndicatorDef

    tech_names = {"rsi", "macd_hist", "bb_position", "volume_surge", "ema_cross"}
    indicators_cfg = strategy.get("indicators", {})
    defs = []
    for name, cfg in indicators_cfg.items():
        if name not in tech_names:
            continue
        weight = float(cfg.get("weight", 0.0)) if isinstance(cfg, dict) else 0.0
        params = {k: v for k, v in (cfg.items() if isinstance(cfg, dict) else {}.items()) if k not in ("weight", "cache_ttl_minutes")}
        defs.append(IndicatorDef(name=name, weight=weight, params=params))
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
    if not symbol or not exchange:
        return

    from uuid import UUID

    try:
        strategy_id_raw = strategy.get("id")
        strategy_id = UUID(strategy_id_raw) if strategy_id_raw else None

        async with AsyncSessionLocal() as db:
            # 1. Load OHLCV
            ohlcv_df = await _load_ohlcv_df(symbol, exchange, db)
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

            rules_cfg = strategy.get("rules", {})
            zone = classify_zone(
                composite,
                buy_threshold=float(rules_cfg.get("buy_threshold", 0.45)),
                sell_threshold=float(rules_cfg.get("sell_threshold", -0.35)),
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

            # 7. Execute
            if strategy_id:
                await execute_signal(signal, symbol, exchange, strategy_id, composite, db)

    except Exception as exc:
        log.error("trading_cycle.error", error=str(exc))


def setup_scheduler(scheduler: AsyncIOScheduler) -> None:
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
        misfire_grace_time=30,
    )
    log.info("scheduler.job_registered", cadence_seconds=cadence)
