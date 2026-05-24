"""Add signals, news_items, social_posts tables

Revision ID: 004
Revises: 003
Create Date: 2026-05-23
"""

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symbol       TEXT NOT NULL,
            exchange     TEXT NOT NULL,
            zone         TEXT NOT NULL,
            score        DOUBLE PRECISION NOT NULL,
            action       TEXT NOT NULL,
            reason       TEXT,
            strategy_id  UUID,
            triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_signals_triggered_at ON signals (triggered_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_signals_symbol ON signals (symbol)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS news_items (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title        TEXT NOT NULL,
            source       TEXT,
            published_at TIMESTAMPTZ,
            url          TEXT,
            summary      TEXT,
            content_hash TEXT UNIQUE,
            fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_news_published_at ON news_items (published_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS social_posts (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            platform     TEXT NOT NULL,
            source       TEXT,
            title        TEXT NOT NULL,
            url          TEXT,
            upvotes      INTEGER DEFAULT 0,
            comments     INTEGER DEFAULT 0,
            published_at TIMESTAMPTZ,
            content_hash TEXT UNIQUE,
            fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_social_published_at ON social_posts (published_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_social_platform ON social_posts (platform)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS social_posts")
    op.execute("DROP TABLE IF EXISTS news_items")
    op.execute("DROP TABLE IF EXISTS signals")
