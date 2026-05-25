"""add asset_type to strategies

Revision ID: 007
Revises: 006
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategies", sa.Column("asset_type", sa.Text(), nullable=True))
    # Tag existing strategies based on the exchange in their config
    op.execute("""
        UPDATE strategies
        SET asset_type = CASE
            WHEN config->>'exchange' ILIKE '%binance%' THEN 'crypto'
            ELSE 'stock'
        END
    """)


def downgrade() -> None:
    op.drop_column("strategies", "asset_type")
