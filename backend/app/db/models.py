import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OHLCV(Base):
    __tablename__ = "ohlcv"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange: Mapped[str] = mapped_column(Text, primary_key=True)
    open: Mapped[float | None] = mapped_column(Double)
    high: Mapped[float | None] = mapped_column(Double)
    low: Mapped[float | None] = mapped_column(Double)
    close: Mapped[float | None] = mapped_column(Double)
    volume: Mapped[float | None] = mapped_column(Double)


class IndicatorSnapshot(Base):
    __tablename__ = "indicator_snapshots"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    indicator_name: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    value: Mapped[float] = mapped_column(Double, nullable=False)
    weight: Mapped[float | None] = mapped_column(Double)
    weighted_value: Mapped[float | None] = mapped_column(Double)


class CompositeScore(Base):
    __tablename__ = "composite_scores"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    score: Mapped[float] = mapped_column(Double, nullable=False)
    zone: Mapped[str] = mapped_column(Text, nullable=False)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default="NOW()"
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float] = mapped_column(Double, nullable=False)
    price: Mapped[float] = mapped_column(Double, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    trigger_score: Mapped[float | None] = mapped_column(Double)
    order_id: Mapped[str | None] = mapped_column(Text)
    fees: Mapped[float | None] = mapped_column(Double, server_default="0")
    pnl: Mapped[float | None] = mapped_column(Double)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float] = mapped_column(Double, nullable=False)
    avg_entry_price: Mapped[float] = mapped_column(Double, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default="NOW()"
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_open: Mapped[bool | None] = mapped_column(Boolean, server_default="TRUE")
    pnl: Mapped[float | None] = mapped_column(Double)


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    config: Mapped[Any] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool | None] = mapped_column(Boolean, server_default="FALSE")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default="NOW()"
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default="NOW()"
    )


class SentimentCache(Base):
    __tablename__ = "sentiment_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str | None] = mapped_column(Text)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Double, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default="NOW()"
    )
    content_hash: Mapped[str | None] = mapped_column(Text, unique=True)


class Controls(Base):
    __tablename__ = "controls"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default="1")
    kill_switch: Mapped[bool | None] = mapped_column(Boolean, server_default="FALSE")
    trading_mode: Mapped[str | None] = mapped_column(Text, server_default="'paper'")
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default="NOW()"
    )


class WatchedSymbol(Base):
    __tablename__ = "watched_symbols"
    __table_args__ = (UniqueConstraint("symbol", "exchange"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)  # crypto | us_stock | indian_stock
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="TRUE")
    added_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default="NOW()"
    )
