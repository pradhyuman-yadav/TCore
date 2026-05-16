"""Add watched_symbols table

Revision ID: 002
Revises: 001
Create Date: 2026-05-16
"""

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS watched_symbols (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symbol     VARCHAR NOT NULL,
            exchange   VARCHAR NOT NULL,
            asset_type VARCHAR NOT NULL,
            is_active  BOOLEAN NOT NULL DEFAULT TRUE,
            added_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (symbol, exchange)
        )
    """)
    op.execute("""
        INSERT INTO watched_symbols (symbol, exchange, asset_type) VALUES
          ('BTC/USDT',  'binanceus',    'crypto'),
          ('ETH/USDT',  'binanceus',    'crypto'),
          ('SOL/USDT',  'binanceus',    'crypto')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS watched_symbols")
