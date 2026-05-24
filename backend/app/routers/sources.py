from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FeedSource
from app.db.session import get_db

router = APIRouter(prefix="/sources")


def _row(r: FeedSource) -> dict:
    return {
        "id": str(r.id),
        "type": r.type,
        "name": r.name,
        "url": r.url,
        "category": r.category,
        "is_active": r.is_active,
        "added_at": r.added_at.isoformat() if r.added_at else None,
    }


# ── News sources ─────────────────────────────────────────────────────────────

@router.get("/news")
async def list_news_sources(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(FeedSource)
        .where(FeedSource.type == "rss_news")
        .order_by(FeedSource.added_at.asc())
    )).scalars().all()
    return [_row(r) for r in rows]


class AddNewsFeedBody(BaseModel):
    name: str
    url: str


@router.post("/news", status_code=201)
async def add_news_source(body: AddNewsFeedBody, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(
        select(FeedSource).where(FeedSource.type == "rss_news", FeedSource.url == body.url)
    )).scalars().first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            await db.commit()
            return _row(existing)
        raise HTTPException(status_code=409, detail="Feed URL already exists")
    src = FeedSource(type="rss_news", name=body.name, url=body.url)
    db.add(src)
    await db.commit()
    await db.refresh(src)
    return _row(src)


@router.delete("/news/{source_id}", status_code=204)
async def remove_news_source(source_id: str, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(FeedSource).where(FeedSource.id == source_id, FeedSource.type == "rss_news")
    )).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    row.is_active = False
    await db.commit()


# ── Social sources ────────────────────────────────────────────────────────────

@router.get("/social")
async def list_social_sources(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(FeedSource)
        .where(FeedSource.type.in_(["reddit", "rss_social"]))
        .order_by(FeedSource.type, FeedSource.category, FeedSource.added_at.asc())
    )).scalars().all()
    return [_row(r) for r in rows]


class AddSocialSourceBody(BaseModel):
    type: str           # reddit | rss_social
    name: str
    url: str | None = None
    category: str | None = None   # crypto | us_stock | indian_stock


@router.post("/social", status_code=201)
async def add_social_source(body: AddSocialSourceBody, db: AsyncSession = Depends(get_db)):
    if body.type not in ("reddit", "rss_social"):
        raise HTTPException(status_code=422, detail="type must be 'reddit' or 'rss_social'")
    if body.type == "rss_social" and not body.url:
        raise HTTPException(status_code=422, detail="url required for rss_social")

    # Dedup: reddit by name+category, rss_social by url
    if body.type == "reddit":
        existing = (await db.execute(
            select(FeedSource).where(
                FeedSource.type == "reddit",
                FeedSource.name == body.name,
                FeedSource.category == body.category,
            )
        )).scalars().first()
    else:
        existing = (await db.execute(
            select(FeedSource).where(FeedSource.type == "rss_social", FeedSource.url == body.url)
        )).scalars().first()

    if existing:
        if not existing.is_active:
            existing.is_active = True
            await db.commit()
            return _row(existing)
        raise HTTPException(status_code=409, detail="Source already exists")

    src = FeedSource(type=body.type, name=body.name, url=body.url, category=body.category)
    db.add(src)
    await db.commit()
    await db.refresh(src)
    return _row(src)


@router.delete("/social/{source_id}", status_code=204)
async def remove_social_source(source_id: str, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(FeedSource).where(
            FeedSource.id == source_id,
            FeedSource.type.in_(["reddit", "rss_social"]),
        )
    )).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    row.is_active = False
    await db.commit()
