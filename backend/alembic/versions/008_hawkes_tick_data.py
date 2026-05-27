"""add tick_trades hypertable and hawkes_params table

Revision ID: 008
Revises: 007
Create Date: 2026-05-25
"""
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── tick_trades: raw aggTrade data from Binance US for Hawkes OFI ──────
    op.execute("""
        CREATE TABLE IF NOT EXISTS tick_trades (
            ts      TIMESTAMPTZ      NOT NULL,
            symbol  TEXT             NOT NULL,
            venue   TEXT             NOT NULL DEFAULT 'binanceus',
            price   DOUBLE PRECISION NOT NULL,
            qty     DOUBLE PRECISION NOT NULL,
            side    SMALLINT         NOT NULL,   -- +1 BUY taker, -1 SELL taker
            agg_id  BIGINT
        )
    """)
    # Promote to TimescaleDB hypertable (chunk by day)
    op.execute(
        "SELECT create_hypertable('tick_trades', 'ts', if_not_exists => TRUE)"
    )
    # Partial unique index — dedup by trade ID when present
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS tick_trades_dedup_idx
        ON tick_trades (ts, venue, symbol, agg_id)
        WHERE agg_id IS NOT NULL
    """)
    # Supporting index for range queries in the Hawkes fitter
    op.execute("""
        CREATE INDEX IF NOT EXISTS tick_trades_sym_ts_idx
        ON tick_trades (symbol, ts DESC)
    """)

    # ── hawkes_params: fitted model parameter cache ─────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS hawkes_params (
            fitted_at   TIMESTAMPTZ      NOT NULL,
            symbol      TEXT             NOT NULL,
            venue       TEXT             NOT NULL,
            mu          JSONB            NOT NULL,   -- [mu_b, mu_s]
            alpha       JSONB            NOT NULL,   -- 2x2xK kernel amplitudes
            beta_vals   JSONB            NOT NULL,   -- K decay constants
            branching   DOUBLE PRECISION,
            train_start TIMESTAMPTZ,
            train_end   TIMESTAMPTZ,
            loglik      DOUBLE PRECISION,
            PRIMARY KEY (symbol, venue, fitted_at)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS hawkes_params_lookup_idx
        ON hawkes_params (symbol, venue, fitted_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS hawkes_params_lookup_idx")
    op.execute("DROP TABLE IF EXISTS hawkes_params")
    op.execute("DROP INDEX IF EXISTS tick_trades_sym_ts_idx")
    op.execute("DROP INDEX IF EXISTS tick_trades_dedup_idx")
    op.execute("DROP TABLE IF EXISTS tick_trades")
