"""add event_log hypertable for the system activity audit trail

Revision ID: 010
Revises: 009
Create Date: 2026-06-01
"""
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS event_log (
            ts        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            id        UUID        NOT NULL DEFAULT gen_random_uuid(),
            category  TEXT        NOT NULL,
            level     TEXT        NOT NULL DEFAULT 'info',
            symbol    TEXT,
            message   TEXT        NOT NULL,
            payload   JSONB,
            PRIMARY KEY (ts, id)
        )
    """)
    # High-volume time-series -> hypertable, chunked by day.
    op.execute("SELECT create_hypertable('event_log', 'ts', if_not_exists => TRUE)")
    op.execute("""
        CREATE INDEX IF NOT EXISTS event_log_cat_ts_idx
        ON event_log (category, ts DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS event_log_sym_ts_idx
        ON event_log (symbol, ts DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS event_log_sym_ts_idx")
    op.execute("DROP INDEX IF EXISTS event_log_cat_ts_idx")
    op.execute("DROP TABLE IF EXISTS event_log")
