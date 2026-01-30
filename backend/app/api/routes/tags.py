from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from app.api.deps import SessionDep
from app.models.paper import Tag  # 프로젝트 경로에 맞게 조정

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


# =========================
# Routes
# =========================
@router.get(
    "/",
    summary="태그 목록 조회",
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
    # count = 전체 태그 개수(페이징 적용 전)
    total = session.exec(select(func.count()).select_from(Tag)).one()

    stmt = (
        select(Tag)
        .order_by(Tag.count.desc(), Tag.name.asc())  # 인기순 + 이름순
        .offset(offset)
        .limit(limit)
    )
    tags = session.exec(stmt).all()

    return PagedTagsResponse(
        items=[TagItem(tag=_to_tag_out(t)) for t in tags],
        count=total,
    )
