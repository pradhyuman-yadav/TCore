"""Add timeframe column to ohlcv table

Revision ID: 003
Revises: 002
Create Date: 2026-05-16

The OHLCV table previously used (time, symbol, exchange) as PK, which meant
1m bars from Binance WS and 1h bars from manual sync for the same symbol
shared the same namespace and queries couldn't filter by timeframe.

This migration recreates the table with timeframe in the PK.
All existing rows are assumed to be 1m bars (from Binance WS).
"""

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    # Rename existing hypertable so we can copy from it
    op.execute("ALTER TABLE ohlcv RENAME TO ohlcv_old")

    # Create new table with timeframe in PK
    op.execute("""
        CREATE TABLE ohlcv (
            time        TIMESTAMPTZ NOT NULL,
            symbol      TEXT NOT NULL,
            exchange    TEXT NOT NULL,
            timeframe   TEXT NOT NULL DEFAULT '1m',
            open        DOUBLE PRECISION,
            high        DOUBLE PRECISION,
            low         DOUBLE PRECISION,
            close       DOUBLE PRECISION,
            volume      DOUBLE PRECISION,
            PRIMARY KEY (time, symbol, exchange, timeframe)
        )
    """)

    # Re-create as TimescaleDB hypertable
    op.execute("SELECT create_hypertable('ohlcv', 'time', if_not_exists => TRUE)")

    # Copy existing data — classify all as 1m (they came from Binance WS kline_1m)
    op.execute("""
        INSERT INTO ohlcv (time, symbol, exchange, timeframe, open, high, low, close, volume)
        SELECT time, symbol, exchange, '1m', open, high, low, close, volume
        FROM ohlcv_old
        ON CONFLICT DO NOTHING
    """)

    op.execute("DROP TABLE ohlcv_old")


def downgrade() -> None:
    op.execute("ALTER TABLE ohlcv RENAME TO ohlcv_new")
    op.execute("""
        CREATE TABLE ohlcv (
            time        TIMESTAMPTZ NOT NULL,
            symbol      TEXT NOT NULL,
            exchange    TEXT NOT NULL,
            open        DOUBLE PRECISION,
            high        DOUBLE PRECISION,
            low         DOUBLE PRECISION,
            close       DOUBLE PRECISION,
            volume      DOUBLE PRECISION,
            PRIMARY KEY (time, symbol, exchange)
        )
    """)
    op.execute("SELECT create_hypertable('ohlcv', 'time', if_not_exists => TRUE)")
    op.execute("""
        INSERT INTO ohlcv (time, symbol, exchange, open, high, low, close, volume)
        SELECT time, symbol, exchange, open, high, low, close, volume
        FROM ohlcv_new WHERE timeframe = '1m'
        ON CONFLICT DO NOTHING
    """)
    op.execute("DROP TABLE ohlcv_new")
