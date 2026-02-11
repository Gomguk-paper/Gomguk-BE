from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select as sa_select
from sqlmodel import select

from app.api.deps import SessionDep, CurrentUser
from app.crud.paper import get_paper_outs_by_ids
from app.models.user import UserPaperLike, UserPaperScrap, UserPaperView
from app.schemas.paper import PaperItem, PagedPapersResponse

router = APIRouter()


# =========================
# Response Schemas
# =========================
class MeResponse(BaseModel):
    id: int
    provider: str
    email: str
    name: str
    profile_image: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)


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
        name=user.name,
        profile_image=user.profile_image,
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
    total = session.exec(
        sa_select(func.count())
        .select_from(UserPaperLike)
        .where(UserPaperLike.user_id == user.id)
    ).scalar_one()

    paper_ids = session.exec(
        select(UserPaperLike.paper_id)
        .where(UserPaperLike.user_id == user.id)
        .order_by(UserPaperLike.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    outs = get_paper_outs_by_ids(session, user_id=user.id, paper_ids=list(paper_ids))

    return PagedPapersResponse(
        items=[PaperItem(paper=o) for o in outs],
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
    total = session.exec(
        sa_select(func.count())
        .select_from(UserPaperScrap)
        .where(UserPaperScrap.user_id == user.id)
    ).scalar_one()

    paper_ids = session.exec(
        select(UserPaperScrap.paper_id)
        .where(UserPaperScrap.user_id == user.id)
        .order_by(UserPaperScrap.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    outs = get_paper_outs_by_ids(session, user_id=user.id, paper_ids=list(paper_ids))

    return PagedPapersResponse(
        items=[PaperItem(paper=o) for o in outs],
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
    total = session.exec(
        sa_select(func.count())
        .select_from(UserPaperView)
        .where(UserPaperView.user_id == user.id)
    ).scalar_one()

    paper_ids = session.exec(
        select(UserPaperView.paper_id)
        .where(UserPaperView.user_id == user.id)
        .order_by(UserPaperView.last_viewed_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    outs = get_paper_outs_by_ids(session, user_id=user.id, paper_ids=list(paper_ids))

    return PagedPapersResponse(
        items=[PaperItem(paper=o) for o in outs],
        count=total,
    )
