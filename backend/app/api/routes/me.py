from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from app.api.deps import SessionDep, CurrentUser
from app.models.paper import Paper
from app.models.user import UserPaperLike, UserPaperScrap, UserPaperView

router = APIRouter()


# =========================
# Response Schemas
# =========================
class MeResponse(BaseModel):
    id: int
    provider: str
    email: str
    nickname: str
    profile_image: Optional[str] = None
    meta: dict[str, Any] = {}


class PaperOut(BaseModel):
    id: int
    title: str
    short: str
    authors: list[str]
    year: int
    image_url: str
    raw_url: str
    source: str


class PaperItem(BaseModel):
    paper: PaperOut


class PagedPapersResponse(BaseModel):
    items: list[PaperItem]
    count: int


# =========================
# Helpers
# =========================
def _source_to_str(source: Any) -> str:
    return source.value if hasattr(source, "value") else str(source)


def _to_paper_out(p: Paper) -> PaperOut:
    return PaperOut(
        id=p.id,
        title=p.title,
        short=p.short,
        authors=p.authors,
        year=p.published_at,       # ✅ 크롤링 시 시간 포맷 확인 필요
        image_url=p.image_url,
        raw_url=p.raw_url,
        source=_source_to_str(p.source),
    )


# =========================
# Routes
# =========================
@router.get(
    "/",
    summary="내 정보 조회 (로그인 확인용)",
    response_model=MeResponse,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        500: {"description": "Internal Server Error"},
    },
)
def me(user: CurrentUser):
    return MeResponse(
        id=user.id,
        provider=user.provider,
        email=user.email,
        nickname=user.name,
        profile_image=user.profile_image,  # DB에 절대 URL 저장 전제
        meta=user.meta or {},
    )


@router.get(
    "/papers/liked",
    summary="좋아요한 논문 목록",
    response_model=PagedPapersResponse,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        500: {"description": "Internal Server Error"},
    },
)
def get_liked_papers(
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    # count = 해당 목록의 전체 개수(페이징 적용 전)
    total = session.exec(
        select(func.count())
        .select_from(UserPaperLike)
        .where(UserPaperLike.user_id == user.id)
    ).one()

    stmt = (
        select(Paper)
        .join(UserPaperLike, UserPaperLike.paper_id == Paper.id)
        .where(UserPaperLike.user_id == user.id)
        .order_by(UserPaperLike.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    papers = session.exec(stmt).all()

    return PagedPapersResponse(
        items=[PaperItem(paper=_to_paper_out(p)) for p in papers],
        count=total,
    )


@router.get(
    "/papers/saved",
    summary="저장(스크랩)한 논문 목록",
    response_model=PagedPapersResponse,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        500: {"description": "Internal Server Error"},
    },
)
def get_saved_papers(
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    # count = 해당 목록의 전체 개수(페이징 적용 전)
    total = session.exec(
        select(func.count())
        .select_from(UserPaperScrap)
        .where(UserPaperScrap.user_id == user.id)
    ).one()

    stmt = (
        select(Paper)
        .join(UserPaperScrap, UserPaperScrap.paper_id == Paper.id)
        .where(UserPaperScrap.user_id == user.id)
        .order_by(UserPaperScrap.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    papers = session.exec(stmt).all()

    return PagedPapersResponse(
        items=[PaperItem(paper=_to_paper_out(p)) for p in papers],
        count=total,
    )


@router.get(
    "/papers/read",
    summary="최근 읽은 논문 목록",
    response_model=PagedPapersResponse,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        500: {"description": "Internal Server Error"},
    },
)
def get_read_papers(
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    # count = 해당 목록의 전체 개수(페이징 적용 전)
    total = session.exec(
        select(func.count())
        .select_from(UserPaperView)
        .where(UserPaperView.user_id == user.id)
    ).one()

    stmt = (
        select(Paper)
        .join(UserPaperView, UserPaperView.paper_id == Paper.id)
        .where(UserPaperView.user_id == user.id)
        .order_by(UserPaperView.last_viewed_at.desc())
        .offset(offset)
        .limit(limit)
    )
    papers = session.exec(stmt).all()

    return PagedPapersResponse(
        items=[PaperItem(paper=_to_paper_out(p)) for p in papers],
        count=total,
    )
