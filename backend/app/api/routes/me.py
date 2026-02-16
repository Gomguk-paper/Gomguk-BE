from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select as sa_select
from sqlmodel import select

from app.api.deps import SessionDep, CurrentUser
from app.core.storage import profile_image_to_public_url, upload_user_profile_png
from app.crud.paper import get_paper_outs_by_ids
from app.models.user import UserPaperLike, UserPaperScrap, UserPaperView
from app.schemas.paper import PaperItem, PagedPapersResponse

router = APIRouter()


# =========================
# Request Schemas
# =========================
class NameUpdateBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)


# =========================
# Response Schemas
# =========================
class MeCounts(BaseModel):
    liked: int = 0
    saved: int = 0
    read: int = 0


class MeResponse(BaseModel):
    id: int
    provider: str
    email: str
    name: str
    profile_image: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)
    counts: MeCounts = Field(default_factory=MeCounts)


class ProfileImageUpdateResponse(BaseModel):
    profile_image: str
    storage_path: str


class NameUpdateResponse(BaseModel):
    name: str


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
def me(
    session: SessionDep,
    user: CurrentUser
):
    liked_count = session.exec(
        select(func.count()).select_from(UserPaperLike).where(UserPaperLike.user_id == user.id)
    ).one()
    saved_count = session.exec(
        select(func.count()).select_from(UserPaperScrap).where(UserPaperScrap.user_id == user.id)
    ).one()
    read_count = session.exec(
        select(func.count()).select_from(UserPaperView).where(UserPaperView.user_id == user.id)
    ).one()

    return MeResponse(
        id=user.id,
        provider=user.provider,
        email=user.email,
        name=user.name,
        profile_image=profile_image_to_public_url(user.profile_image),
        meta=user.meta or {},
        counts=MeCounts(liked=liked_count, saved=saved_count, read=read_count),
    )


@router.put(
    "/name",
    summary="이름 변경",
    response_model=NameUpdateResponse,
    responses={
        400: {"description": "INVALID_NAME"},
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        500: {"description": "Internal Server Error"},
    },
)
def update_name(
    session: SessionDep,
    user: CurrentUser,
    body: NameUpdateBody,
):
    new_name = body.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="INVALID_NAME")

    if new_name == user.name:
        return NameUpdateResponse(name=user.name)

    user.name = new_name
    session.add(user)
    session.commit()
    session.refresh(user)

    return NameUpdateResponse(name=user.name)


@router.put(
    "/profile-image",
    summary="프로필 이미지 업로드/수정 (PNG only)",
    response_model=ProfileImageUpdateResponse,
    responses={
        400: {"description": "INVALID_FILE"},
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        500: {"description": "Internal Server Error"},
    },
)
def upsert_profile_image(
    session: SessionDep,
    user: CurrentUser,
    image: UploadFile = File(..., description="png 파일"),
):
    try:
        storage_path, public_url = upload_user_profile_png(user_id=user.id, image=image)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"INVALID_FILE: {e}")
    finally:
        image.file.close()

    user.profile_image = storage_path
    session.add(user)
    session.commit()

    return ProfileImageUpdateResponse(profile_image=public_url, storage_path=storage_path)


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
