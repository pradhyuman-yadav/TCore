import pytest
from sqlalchemy import text


async def test_all_tables_exist(db_session):
    expected = {
        "ohlcv", "indicator_snapshots", "composite_scores",
        "trades", "positions", "strategies", "sentiment_cache", "controls",
    }
    result = await db_session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    tables = {row[0] for row in result}
    assert expected.issubset(tables)


async def test_hypertables_created(db_session):
    result = await db_session.execute(
        text("SELECT hypertable_name FROM timescaledb_information.hypertables")
    )
    hypertables = {row[0] for row in result}
    assert {"ohlcv", "indicator_snapshots", "composite_scores"}.issubset(hypertables)


async def test_controls_seeded_with_single_row(db_session):
    result = await db_session.execute(text("SELECT COUNT(*) FROM controls"))
    assert result.scalar() == 1


async def test_controls_defaults(db_session):
    result = await db_session.execute(
        text("SELECT kill_switch, trading_mode FROM controls")
    )
    row = result.fetchone()
    assert row.kill_switch == False
    assert row.trading_mode == "paper"


async def test_ohlcv_insert_and_query(db_session):
    await db_session.execute(text("""
        INSERT INTO ohlcv (time, symbol, exchange, open, high, low, close, volume)
        VALUES (NOW(), 'BTC/USDT', 'binance', 40000, 41000, 39000, 40500, 100)
    """))
    await db_session.commit()
    result = await db_session.execute(text("SELECT COUNT(*) FROM ohlcv"))
    assert result.scalar() == 1


async def test_controls_single_row_constraint(db_session):
    with pytest.raises(Exception):
        await db_session.execute(text("INSERT INTO controls (id) VALUES (2)"))
