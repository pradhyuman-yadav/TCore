"""Add category column to news_items and social_posts; tag rss_news feed sources

Revision ID: 006
Revises: 005
Create Date: 2026-05-25
"""

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("ALTER TABLE news_items  ADD COLUMN IF NOT EXISTS category TEXT")
    op.execute("ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS category TEXT")

    # Tag existing rss_news feed sources with category
    op.execute("""
        UPDATE feed_sources SET category = 'crypto'
        WHERE type = 'rss_news'
          AND name IN ('CoinDesk', 'CoinTelegraph', 'Decrypt')
    """)
    op.execute("""
        UPDATE feed_sources SET category = 'stock'
        WHERE type = 'rss_news'
          AND name IN ('Reuters', 'ET Markets')
    """)

    # Index for fast filtering
    op.execute("CREATE INDEX IF NOT EXISTS ix_news_category  ON news_items  (category)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_social_category ON social_posts (category)")


def downgrade() -> None:
    op.execute("ALTER TABLE news_items  DROP COLUMN IF EXISTS category")
    op.execute("ALTER TABLE social_posts DROP COLUMN IF EXISTS category")
