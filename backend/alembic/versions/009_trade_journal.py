"""add trade_journal table for the performance feedback loop

Revision ID: 009
Revises: 008
Create Date: 2026-06-01
"""
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS trade_journal (
            id            UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
            closed_at     TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
            symbol        TEXT             NOT NULL,
            exchange      TEXT             NOT NULL,
            mode          TEXT             NOT NULL,       -- paper | live
            decision_mode TEXT,                            -- rules | agent
            regime        TEXT,                            -- stable | reflexive
            pressure      DOUBLE PRECISION,
            confidence    DOUBLE PRECISION,
            entry_price   DOUBLE PRECISION,
            exit_price    DOUBLE PRECISION,
            pnl           DOUBLE PRECISION,
            stop_loss     DOUBLE PRECISION,
            take_profit   DOUBLE PRECISION,
            strategy_id   UUID
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS trade_journal_lookup_idx
        ON trade_journal (mode, regime, closed_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS trade_journal_lookup_idx")
    op.execute("DROP TABLE IF EXISTS trade_journal")
