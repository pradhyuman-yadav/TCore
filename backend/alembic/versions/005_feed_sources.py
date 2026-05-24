"""Add feed_sources table for configurable news and social sources

Revision ID: 005
Revises: 004
Create Date: 2026-05-23
"""

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS feed_sources (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            type       TEXT NOT NULL,      -- 'rss_news' | 'reddit' | 'rss_social'
            name       TEXT NOT NULL,
            url        TEXT,               -- RSS: feed URL; reddit: NULL
            category   TEXT,               -- reddit: crypto | us_stock | indian_stock
            is_active  BOOLEAN NOT NULL DEFAULT TRUE,
            added_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Seed: news RSS feeds
    op.execute("""
        INSERT INTO feed_sources (type, name, url) VALUES
          ('rss_news', 'CoinDesk',      'https://www.coindesk.com/arc/outboundfeeds/rss/'),
          ('rss_news', 'CoinTelegraph', 'https://cointelegraph.com/rss'),
          ('rss_news', 'Decrypt',       'https://decrypt.co/feed'),
          ('rss_news', 'Reuters',       'https://feeds.reuters.com/reuters/businessNews'),
          ('rss_news', 'ET Markets',    'https://economictimes.indiatimes.com/markets/rss.cms')
        ON CONFLICT DO NOTHING
    """)

    # Seed: reddit subreddits
    op.execute("""
        INSERT INTO feed_sources (type, name, category) VALUES
          ('reddit', 'Bitcoin',           'crypto'),
          ('reddit', 'CryptoCurrency',    'crypto'),
          ('reddit', 'ethtrader',         'crypto'),
          ('reddit', 'solana',            'crypto'),
          ('reddit', 'binance',           'crypto'),
          ('reddit', 'wallstreetbets',    'us_stock'),
          ('reddit', 'stocks',            'us_stock'),
          ('reddit', 'investing',         'us_stock'),
          ('reddit', 'IndianStockMarket', 'indian_stock'),
          ('reddit', 'IndiaInvestments',  'indian_stock')
        ON CONFLICT DO NOTHING
    """)

    # Seed: social RSS feeds
    op.execute("""
        INSERT INTO feed_sources (type, name, url, category) VALUES
          ('rss_social', 'CoinDesk',      'https://www.coindesk.com/arc/outboundfeeds/rss/',   'crypto'),
          ('rss_social', 'CoinTelegraph', 'https://cointelegraph.com/rss',                     'crypto'),
          ('rss_social', 'Decrypt',       'https://decrypt.co/feed',                           'crypto'),
          ('rss_social', 'The Block',     'https://www.theblock.co/rss.xml',                   'crypto'),
          ('rss_social', 'ET Markets',    'https://economictimes.indiatimes.com/markets/rss.cms', 'us_stock'),
          ('rss_social', 'Moneycontrol',  'https://www.moneycontrol.com/rss/MCtopnews.xml',    'us_stock'),
          ('rss_social', 'Reuters Biz',   'https://feeds.reuters.com/reuters/businessNews',    'us_stock')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feed_sources")
