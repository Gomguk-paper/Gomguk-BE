from __future__ import annotations

from typing import Any, Optional, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.api.deps import SessionDep, CurrentUser, CurrentUserOptional
from app.core.enums import Site
from app.models.paper import Paper, PaperTag
from app.models.user import UserPaperLike, UserPaperScrap

router = APIRouter()


# =========================
# Response Schemas
# =========================
class PaperOut(BaseModel):
    id: int
    title: str
    abstract: str
    authors: list[str]
    year: int
    image_url: str
    raw_url: str
    venue: str
    tags: list[str] = []
    metrics: dict = {}
    is_liked: bool = False
    is_scrapped: bool = False


class PaperItem(BaseModel):
    paper: PaperOut


class PagedPapersResponse(BaseModel):
    items: list[PaperItem]
    count: int


# =========================
# Helpers
# =========================
def _source_to_str(source: Any) -> str:
    val = source.value if hasattr(source, "value") else str(source)
    # Map specifically if needed, otherwise capitalize
    if val.lower() == "arxiv":
        return "arXiv"
    if val.lower() == "cvpr":
        return "CVPR"
    return val.upper()


def _to_year(value: Any) -> int:
    # published_at이 int/date/datetime 어떤 형태든 연도로 맞춤
    if isinstance(value, int):
        return value
    if hasattr(value, "year"):
        return int(value.year)
    return int(value)


def _get_paper_or_404(session: SessionDep, paper_id: int) -> Paper:
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


def _to_paper_out(
    p: Paper,
    is_liked: bool = False,
    is_scrapped: bool = False,
) -> PaperOut:
    # Mock metrics for now (randomized or fixed to look good)
    metrics = {
        "trendingScore": 90, 
        "recencyScore": 80, 
        "citations": 100
    }
    
    # Use ORM relationship to get tag names
    tag_names = [t.name for t in p.tags]
        
    return PaperOut(
        id=p.id,
        title=p.title,
        abstract=p.short,  # Map short -> abstract
        authors=p.authors,
        year=_to_year(p.published_at),
        image_url=p.image_url,
        raw_url=p.raw_url,
        venue=_source_to_str(p.source), # Map source -> venue
        tags=tag_names,
        metrics=metrics,
        is_liked=is_liked,
        is_scrapped=is_scrapped,
    )


# =========================
# Routes
# =========================
@router.get(
    "/",
    summary="논문 목록 조회",
    response_model=PagedPapersResponse,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        500: {"description": "Internal Server Error"},
    },
)
def list_papers(
    session: SessionDep,
    user: CurrentUserOptional,
    q: Optional[str] = Query(None, description="제목 검색 (부분 일치)"),
    tag: Optional[int] = Query(None, description="태그 id 필터"),
    source: Optional[Site] = Query(None, description="출처(site) 필터 (예: arxiv)"),
    sort: Literal["trending", "recent", "citations"] = Query(
        "recent",
        description="정렬 옵션(현재는 구분만 하고 실제 정렬은 전부 최신(recent))",
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    base = select(Paper)

    if tag is not None:
        base = (
            select(Paper)
            .join(PaperTag, PaperTag.paper_id == Paper.id)
            .where(PaperTag.tag_id == tag)
        )

    if q:
        base = base.where(Paper.title.ilike(f"%{q}%"))

    if source is not None:
        base = base.where(Paper.source == source)

    # sort는 받되, 현재는 전부 최신 정렬로
    page_stmt = (
        base.options(selectinload(Paper.tags))
        .order_by(Paper.published_at.desc(), Paper.id.desc())
        .offset(offset)
        .limit(limit)
    )
    papers = session.exec(page_stmt).all()

    subq = base.subquery()
    total = session.exec(select(func.count()).select_from(subq)).one()

    return PagedPapersResponse(
        items=[PaperItem(paper=_to_paper_out(p)) for p in papers],
        count=total,
    )


@router.get(
    "/{paper_id}",
    summary="논문 상세 조회 (내 상태 포함)",
    response_model=PaperOut,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        404: {"description": "PAPER_NOT_FOUND"},
        500: {"description": "Internal Server Error"},
    },
)
def get_paper_detail(
    session: SessionDep,
    user: CurrentUserOptional,
    paper_id: int,
):
    paper = _get_paper_or_404(session, paper_id)

    is_liked = False
    is_scrapped = False

    if user:
        is_liked = session.exec(
            select(UserPaperLike)
            .where(UserPaperLike.user_id == user.id, UserPaperLike.paper_id == paper_id)
        ).first() is not None

        is_scrapped = session.exec(
            select(UserPaperScrap)
            .where(UserPaperScrap.user_id == user.id, UserPaperScrap.paper_id == paper_id)
        ).first() is not None

    return _to_paper_out(
        paper,
        is_liked=is_liked,
        is_scrapped=is_scrapped,
    )


@router.put(
    "/{paper_id}/like",
    summary="좋아요 추가 (멱등)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        404: {"description": "PAPER_NOT_FOUND"},
        500: {"description": "Internal Server Error"},
    },
)
def like_paper(session: SessionDep, user: CurrentUser, paper_id: int):
    _get_paper_or_404(session, paper_id)

    existing = session.exec(
        select(UserPaperLike).where(
            UserPaperLike.user_id == user.id,
            UserPaperLike.paper_id == paper_id,
        )
    ).first()

    if not existing:
        session.add(UserPaperLike(user_id=user.id, paper_id=paper_id))
        session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{paper_id}/like",
    summary="좋아요 취소",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        404: {"description": "PAPER_NOT_FOUND or LIKE_NOT_FOUND"},
        500: {"description": "Internal Server Error"},
    },
)
def unlike_paper(session: SessionDep, user: CurrentUser, paper_id: int):
    _get_paper_or_404(session, paper_id)

    existing = session.exec(
        select(UserPaperLike).where(
            UserPaperLike.user_id == user.id,
            UserPaperLike.paper_id == paper_id,
        )
    ).first()

    if not existing:
        raise HTTPException(status_code=404, detail="Like not found")

    session.delete(existing)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{paper_id}/scrap",
    summary="스크랩 추가 (멱등)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        404: {"description": "PAPER_NOT_FOUND"},
        500: {"description": "Internal Server Error"},
    },
)
def scrap_paper(session: SessionDep, user: CurrentUser, paper_id: int):
    _get_paper_or_404(session, paper_id)

    existing = session.exec(
        select(UserPaperScrap).where(
            UserPaperScrap.user_id == user.id,
            UserPaperScrap.paper_id == paper_id,
        )
    ).first()

    if not existing:
        session.add(UserPaperScrap(user_id=user.id, paper_id=paper_id))
        session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{paper_id}/scrap",
    summary="스크랩 취소",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        404: {"description": "PAPER_NOT_FOUND or SCRAP_NOT_FOUND"},
        500: {"description": "Internal Server Error"},
    },
)
def unscrap_paper(session: SessionDep, user: CurrentUser, paper_id: int):
    _get_paper_or_404(session, paper_id)

    existing = session.exec(
        select(UserPaperScrap).where(
            UserPaperScrap.user_id == user.id,
            UserPaperScrap.paper_id == paper_id,
        )
    ).first()

    if not existing:
        raise HTTPException(status_code=404, detail="Scrap not found")

    session.delete(existing)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
