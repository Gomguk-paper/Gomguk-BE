from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field as PydField
from sqlmodel import select

from app.api.deps import SessionDep
from app.core.enums import Site, SummaryStyle
from app.models.paper import Paper, Tag, PaperTag, PaperSummary

router = APIRouter()


# =========================
# Request Schemas
# =========================
class AddTagBody(BaseModel):
    name: str
    description: str = ""


class AddPaperBody(BaseModel):
    title: str
    short: str
    authors: list[str] = PydField(default_factory=list)
    published_at: datetime
    image_url: str
    raw_url: str
    source: str
    tag_ids: list[int] = PydField(default_factory=list)


class AddSummaryBody(BaseModel):
    paper_id: int
    style: Optional[str] = None  # 기본 plain
    body: str


class AddPaperTagsBody(BaseModel):
    tag_ids: list[int]


# =========================
# Response Schemas
# =========================
class TagResponse(BaseModel):
    id: int
    name: str
    description: str
    count: int
    created_at: datetime


class PaperResponse(BaseModel):
    id: int
    title: str
    short: str
    authors: list[str]
    published_at: datetime
    image_url: str
    raw_url: str
    source: str
    created_at: datetime


class SummaryResponse(BaseModel):
    id: int
    paper_id: int
    style: str
    body: str
    created_at: datetime


class AttachTagsResponse(BaseModel):
    paper_id: int
    attached: int


# =========================
# Helpers
# =========================
def _enum_to_str(v: Any) -> str:
    return v.value if hasattr(v, "value") else str(v)


def _parse_site(source: str) -> Site:
    try:
        return Site(source)
    except Exception:
        try:
            return Site[source.lower()]
        except Exception:
            raise HTTPException(status_code=400, detail="INVALID_ENUM")


def _parse_summary_style(style: Optional[str]) -> SummaryStyle:
    if not style:
        style = "plain"
    try:
        return SummaryStyle(style)
    except Exception:
        try:
            return SummaryStyle[style.upper()]
        except Exception:
            raise HTTPException(status_code=400, detail="INVALID_ENUM")


def _get_tags_or_404(session: SessionDep, tag_ids: list[int]) -> list[Tag]:
    if not tag_ids:
        return []

    tags = session.exec(select(Tag).where(Tag.id.in_(tag_ids))).all()
    found = {t.id for t in tags}
    missing = [tid for tid in tag_ids if tid not in found]
    if missing:
        raise HTTPException(status_code=404, detail="TAGS_NOT_FOUND")
    return tags


def _attach_tags(session: SessionDep, paper_id: int, tag_ids: list[int]) -> int:
    """
    - 이미 연결된 태그는 무시
    - 새로 연결된 태그 수만큼 tags.count += 1
    - return: attached 개수
    """
    if not tag_ids:
        return 0

    # 태그 존재 검증
    tags = _get_tags_or_404(session, tag_ids)

    # 이미 연결된 tag_id들
    existing = session.exec(
        select(PaperTag.tag_id).where(
            PaperTag.paper_id == paper_id,
            PaperTag.tag_id.in_(tag_ids),
        )
    ).all()
    existing_ids = set(existing)

    new_ids = [tid for tid in tag_ids if tid not in existing_ids]
    if not new_ids:
        return 0

    # PaperTag 추가
    for tid in new_ids:
        session.add(PaperTag(paper_id=paper_id, tag_id=tid))

    # count 증가 (간단 버전)
    tag_by_id = {t.id: t for t in tags}
    for tid in new_ids:
        tag_by_id[tid].count += 1

    session.commit()
    return len(new_ids)


# =========================
# Routes
# =========================
@router.post(
    "/tag",
    summary="태그 생성",
    response_model=TagResponse,
    responses={
        409: {"description": "TAG_NAME_EXISTS (동일 name 존재)"},
        500: {"description": "Internal Server Error"},
    },
)
def add_tag(session: SessionDep, body: AddTagBody):
    exists = session.exec(select(Tag).where(Tag.name == body.name)).first()
    if exists:
        raise HTTPException(status_code=409, detail="TAG_NAME_EXISTS")

    tag = Tag(name=body.name, description=body.description, count=0)
    session.add(tag)
    session.commit()
    session.refresh(tag)

    return TagResponse(
        id=tag.id,
        name=tag.name,
        description=tag.description,
        count=tag.count,
        created_at=tag.created_at,
    )


@router.post(
    "/paper",
    summary="논문 생성",
    response_model=PaperResponse,
    responses={
        404: {"description": "TAGS_NOT_FOUND (tag_ids 중 일부 없음)"},
        400: {"description": "INVALID_ENUM (source 값 오류)"},
        500: {"description": "Internal Server Error"},
    },
)
def add_paper(session: SessionDep, body: AddPaperBody):
    site_enum = _parse_site(body.source)

    paper = Paper(
        title=body.title,
        short=body.short,
        authors=body.authors,
        published_at=body.published_at,
        image_url=body.image_url,
        raw_url=body.raw_url,
        source=site_enum,
    )
    session.add(paper)
    session.commit()
    session.refresh(paper)

    # tag_ids 있으면 연결
    if body.tag_ids:
        _attach_tags(session, paper.id, body.tag_ids)
        session.refresh(paper)

    return PaperResponse(
        id=paper.id,
        title=paper.title,
        short=paper.short,
        authors=paper.authors or [],
        published_at=paper.published_at,
        image_url=paper.image_url,
        raw_url=paper.raw_url,
        source=_enum_to_str(paper.source),
        created_at=paper.created_at,
    )


@router.post(
    "/summary",
    summary="논문 요약 생성",
    response_model=SummaryResponse,
    responses={
        404: {"description": "PAPER_NOT_FOUND (paper_id 없음)"},
        409: {"description": "SUMMARY_ALREADY_EXISTS (동일 paper_id + style 존재)"},
        400: {"description": "INVALID_ENUM (style 값 오류)"},
        500: {"description": "Internal Server Error"},
    },
)
def add_summary(session: SessionDep, body: AddSummaryBody):
    paper = session.get(Paper, body.paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="PAPER_NOT_FOUND")

    style_enum = _parse_summary_style(body.style)

    exists = session.exec(
        select(PaperSummary).where(
            PaperSummary.paper_id == body.paper_id,
            PaperSummary.style == style_enum,
        )
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="SUMMARY_ALREADY_EXISTS")

    summary = PaperSummary(
        paper_id=body.paper_id,
        style=style_enum,
        body=body.body,
    )
    session.add(summary)
    session.commit()
    session.refresh(summary)

    return SummaryResponse(
        id=summary.id,
        paper_id=summary.paper_id,
        style=_enum_to_str(summary.style),
        body=summary.body,
        created_at=summary.created_at,
    )


@router.post(
    "/paper/{paper_id}/tags",
    summary="기존 논문에 태그 연결(복수)",
    response_model=AttachTagsResponse,
    responses={
        404: {"description": "PAPER_NOT_FOUND (paper_id 없음)"},
        404: {"description": "TAGS_NOT_FOUND (tag_ids 중 일부 없음)"},
        500: {"description": "Internal Server Error"},
    },
)
def attach_tags_to_paper(session: SessionDep, paper_id: int, body: AddPaperTagsBody):
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="PAPER_NOT_FOUND")

    attached = _attach_tags(session, paper_id, body.tag_ids)
    return AttachTagsResponse(paper_id=paper_id, attached=attached)
