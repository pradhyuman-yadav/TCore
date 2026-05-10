"""Initial schema — all 8 tables, 3 hypertables, seed controls

Revision ID: 001
Revises:
Create Date: 2026-05-09
"""

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ohlcv (
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
        CREATE TABLE IF NOT EXISTS indicator_snapshots (
            time            TIMESTAMPTZ NOT NULL,
            symbol          TEXT NOT NULL,
            strategy_id     UUID,
            indicator_name  TEXT NOT NULL,
            value           DOUBLE PRECISION NOT NULL,
            weight          DOUBLE PRECISION,
            weighted_value  DOUBLE PRECISION,
            PRIMARY KEY (time, symbol, indicator_name)
        )
    """)
    op.execute(
        "SELECT create_hypertable('indicator_snapshots', 'time', if_not_exists => TRUE)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS composite_scores (
            time        TIMESTAMPTZ NOT NULL,
            symbol      TEXT NOT NULL,
            strategy_id UUID,
            score       DOUBLE PRECISION NOT NULL,
            zone        TEXT NOT NULL,
            PRIMARY KEY (time, symbol)
        )
    """)
    op.execute(
        "SELECT create_hypertable('composite_scores', 'time', if_not_exists => TRUE)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            symbol          TEXT NOT NULL,
            exchange        TEXT NOT NULL,
            side            TEXT NOT NULL,
            quantity        DOUBLE PRECISION NOT NULL,
            price           DOUBLE PRECISION NOT NULL,
            status          TEXT NOT NULL,
            mode            TEXT NOT NULL,
            strategy_id     UUID,
            trigger_score   DOUBLE PRECISION,
            order_id        TEXT,
            fees            DOUBLE PRECISION DEFAULT 0,
            pnl             DOUBLE PRECISION
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symbol          TEXT NOT NULL,
            exchange        TEXT NOT NULL,
            side            TEXT NOT NULL,
            quantity        DOUBLE PRECISION NOT NULL,
            avg_entry_price DOUBLE PRECISION NOT NULL,
            mode            TEXT NOT NULL,
            strategy_id     UUID,
            opened_at       TIMESTAMPTZ DEFAULT NOW(),
            closed_at       TIMESTAMPTZ,
            is_open         BOOLEAN DEFAULT TRUE,
            pnl             DOUBLE PRECISION
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT NOT NULL UNIQUE,
            config      JSONB NOT NULL,
            is_active   BOOLEAN DEFAULT FALSE,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_cache (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source          TEXT NOT NULL,
            symbol          TEXT,
            raw_content     TEXT NOT NULL,
            score           DOUBLE PRECISION NOT NULL,
            reasoning       TEXT,
            model_used      TEXT,
            fetched_at      TIMESTAMPTZ DEFAULT NOW(),
            content_hash    TEXT UNIQUE
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS controls (
            id              INTEGER PRIMARY KEY DEFAULT 1,
            kill_switch     BOOLEAN DEFAULT FALSE,
            trading_mode    TEXT DEFAULT 'paper',
            updated_at      TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT single_row CHECK (id = 1)
        )
    """)

    op.execute("INSERT INTO controls (id) VALUES (1) ON CONFLICT DO NOTHING")


def downgrade() -> None:
    for table in [
        "controls",
        "sentiment_cache",
        "strategies",
        "positions",
        "trades",
        "composite_scores",
        "indicator_snapshots",
        "ohlcv",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
