from __future__ import annotations

from typing import Any, Optional, Literal

from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import select

from app.api.deps import SessionDep, CurrentUser
from app.core.enums import Site, EventType
from app.crud.event import create_event
from app.models.paper import Paper, PaperTag
from app.models.user import UserPaperLike, UserPaperScrap

router = APIRouter()


# =========================
# Response Schemas
# =========================
class PaperOut(BaseModel):
    id: int
    title: str
    short: str
    authors: list[str]
    year: int
    image_url: str
    raw_url: str
    source: str
    tags: list[int] = Field(default_factory=list)
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
    return source.value if hasattr(source, "value") else str(source)


def _to_year(published_at: datetime) -> int:
    return published_at.year


def _get_paper_or_404(session: SessionDep, paper_id: int) -> Paper:
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


def _to_paper_out(
    p: Paper,
    tags: Optional[list[int]] = None,
    is_liked: bool = False,
    is_scrapped: bool = False,
) -> PaperOut:
    return PaperOut(
        id=p.id,
        title=p.title,
        short=p.short,
        authors=p.authors,
        year=_to_year(p.published_at),
        image_url=p.image_url,
        raw_url=p.raw_url,
        source=_source_to_str(p.source),
        tags=tags or [],
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
    user: CurrentUser,
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
        base.order_by(Paper.published_at.desc(), Paper.id.desc())
        .offset(offset)
        .limit(limit)
    )
    papers = session.exec(page_stmt).all()

    subq = base.subquery()
    total = session.exec(select(func.count()).select_from(subq)).one()

    # 검색 의도가 있을 때만 search 이벤트 기록
    if q or (tag is not None) or (source is not None):
        create_event(
            session,
            user_id=user.id,
            event_type=EventType.search,
            meta={
                "query": q,
                "filters": {
                    "tag": tag,
                    "source": (source.value if hasattr(source, "value") else str(source)) if source is not None else None,
                },
                "sort": sort,
                "limit": limit,
                "offset": offset,
                "source": "paper_list",
            },
        )
        session.commit()

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
    user: CurrentUser,
    paper_id: int,
):
    paper = _get_paper_or_404(session, paper_id)

    tags = session.exec(
        select(PaperTag.tag_id)
        .where(PaperTag.paper_id == paper_id)
        .order_by(PaperTag.tag_id.asc())
    ).all()

    is_liked = session.exec(
        select(UserPaperLike)
        .where(UserPaperLike.user_id == user.id, UserPaperLike.paper_id == paper_id)
    ).first() is not None

    is_scrapped = session.exec(
        select(UserPaperScrap)
        .where(UserPaperScrap.user_id == user.id, UserPaperScrap.paper_id == paper_id)
    ).first() is not None

    create_event(
        session,
        user_id=user.id,
        event_type=EventType.view,
        meta={"paper_id": paper_id, "source": "paper_detail"},
    )
    session.commit()

    return _to_paper_out(
        paper,
        tags=list(tags),
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
        create_event(
            session,
            user_id=user.id,
            event_type=EventType.like,
            meta={"paper_id": paper_id, "source": "paper_like"},
        )
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
    create_event(
        session,
        user_id=user.id,
        event_type=EventType.unlike,
        meta={"paper_id": paper_id, "source": "paper_unlike"},
    )
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

    create_event(
        session,
        user_id=user.id,
        event_type=EventType.save,
        meta={"paper_id": paper_id, "source": "paper_save"},
    )
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
    create_event(
        session,
        user_id=user.id,
        event_type=EventType.unsave,
        meta={"paper_id": paper_id, "source": "paper_unsave"},
    )
    session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/feed",
    summary="메인 화면 피드 조회 (추천 시스템용)",
    response_model=PagedPapersResponse,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        500: {"description": "Internal Server Error"},
    },
)
def get_feed(
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    page_stmt = (
        select(Paper)
        .order_by(Paper.published_at.desc(), Paper.id.desc())
        .offset(offset)
        .limit(limit)
    )
    papers = session.exec(page_stmt).all()

    total = session.exec(select(func.count()).select_from(Paper)).one()

    paper_ids = [p.id for p in papers]
    if not paper_ids:
        return PagedPapersResponse(items=[], count=total)

    # tags 배치 조회
    tag_rows = session.exec(
        select(PaperTag.paper_id, PaperTag.tag_id)
        .where(PaperTag.paper_id.in_(paper_ids))
    ).all()
    tags_map: dict[int, list[int]] = {}
    for pid, tid in tag_rows:
        tags_map.setdefault(pid, []).append(tid)

    # liked/scrapped 배치 조회
    liked_ids = set(
        session.exec(
            select(UserPaperLike.paper_id)
            .where(UserPaperLike.user_id == user.id, UserPaperLike.paper_id.in_(paper_ids))
        ).all()
    )
    scrapped_ids = set(
        session.exec(
            select(UserPaperScrap.paper_id)
            .where(UserPaperScrap.user_id == user.id, UserPaperScrap.paper_id.in_(paper_ids))
        ).all()
    )

    return PagedPapersResponse(
        items=[
            PaperItem(
                paper=_to_paper_out(
                    p,
                    tags=sorted(tags_map.get(p.id, [])),
                    is_liked=(p.id in liked_ids),
                    is_scrapped=(p.id in scrapped_ids),
                )
            )
            for p in papers
        ],
        count=total,
    )