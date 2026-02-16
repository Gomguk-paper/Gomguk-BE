from __future__ import annotations

from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from app.api.deps import SessionDep
from app.crud.paper import get_top_global_trending_papers
from app.models.paper import PaperTag, Tag

router = APIRouter()


# =========================
# Response Schemas
# =========================
class TagOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    count: int


class TagItem(BaseModel):
    tag: TagOut


class PagedTagsResponse(BaseModel):
    items: list[TagItem]
    count: int


class TrendingTagIdsResponse(BaseModel):
    tag_ids: list[int]


# =========================
# Helpers
# =========================
def _to_tag_out(t: Tag) -> TagOut:
    return TagOut(
        id=t.id,
        name=t.name,
        description=t.description,
        count=t.count,
    )


def _get_tag_or_404(session: SessionDep, tag_id: int) -> Tag:
    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


def _get_trending_tag_ids(
    session: SessionDep,
    *,
    candidate_paper_limit: int = 100,
    tag_limit: int = 20,
) -> list[int]:
    top_papers = get_top_global_trending_papers(
        session,
        limit=candidate_paper_limit,
    )
    if not top_papers:
        return []

    trending_by_paper_id = {paper_id: score for paper_id, score in top_papers}
    paper_ids = list(trending_by_paper_id.keys())

    rows = session.exec(
        select(PaperTag.paper_id, PaperTag.tag_id).where(PaperTag.paper_id.in_(paper_ids))
    ).all()

    tag_scores: dict[int, float] = defaultdict(float)
    for paper_id, tag_id in rows:
        tag_scores[tag_id] += trending_by_paper_id.get(paper_id, 0.0)

    ranked = sorted(tag_scores.items(), key=lambda item: item[1], reverse=True)
    return [tag_id for tag_id, _ in ranked[:tag_limit]]


# =========================
# Routes
# =========================
@router.get(
    "/",
    summary="List tags",
    response_model=PagedTagsResponse,
    responses={
        500: {"description": "Internal Server Error"},
    },
)
def list_tags(
    session: SessionDep,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    total = session.exec(select(func.count()).select_from(Tag)).one()

    stmt = (
        select(Tag)
        .order_by(Tag.count.desc(), Tag.name.asc())
        .offset(offset)
        .limit(limit)
    )
    tags = session.exec(stmt).all()

    return PagedTagsResponse(
        items=[TagItem(tag=_to_tag_out(t)) for t in tags],
        count=total,
    )


@router.get(
    "/trending",
    summary="Top trending tag ids",
    response_model=TrendingTagIdsResponse,
    responses={
        500: {"description": "Internal Server Error"},
    },
)
def get_trending_tag_ids(
    session: SessionDep,
    candidate_paper_limit: int = Query(100, ge=1, le=500),
    limit: int = Query(20, ge=1, le=100),
):
    return TrendingTagIdsResponse(
        tag_ids=_get_trending_tag_ids(
            session,
            candidate_paper_limit=candidate_paper_limit,
            tag_limit=limit,
        )
    )


@router.get(
    "/{tag_id}",
    summary="Get tag detail (검수용)",
    response_model=TagOut,
    responses={
        404: {"description": "TAG_NOT_FOUND"},
        500: {"description": "Internal Server Error"},
    },
)
def get_tag_detail(
    session: SessionDep,
    tag_id: int,
):
    return _to_tag_out(_get_tag_or_404(session, tag_id))
