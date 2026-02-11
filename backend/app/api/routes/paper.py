from __future__ import annotations

from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlmodel import select

from app.api.deps import SessionDep, CurrentUser
from app.core.enums import Site, EventType
from app.crud.event import create_event
from app.crud.paper import (
    list_paper_outs_page,
    feed_paper_outs_page,
    get_paper_out_by_id,
)
from app.models.paper import Paper
from app.models.user import UserPaperLike, UserPaperScrap
from app.schemas.paper import PaperOut, PaperItem, PagedPapersResponse

router = APIRouter()


# =========================
# Helpers
# =========================
def _get_paper_or_404(session: SessionDep, paper_id: int) -> Paper:
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


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
    sort: Literal["popular", "recent", "recommend"] = Query(
        "recent",
        description="정렬 옵션(popular=좋아요순, recent=최신순, recommend=추천순(임시로 최신순))",
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    outs, total = list_paper_outs_page(
        session,
        user_id=user.id,
        q=q,
        tag=tag,
        source=source,
        sort=sort,
        limit=limit,
        offset=offset,
    )

    if q or (tag is not None) or (source is not None):
        create_event(
            session,
            user_id=user.id,
            event_type=EventType.search,
            meta={
                "query": q,
                "filters": {
                    "tag": tag,
                    "source": source.value if source is not None else None,
                },
                "sort": sort,
                "limit": limit,
                "offset": offset,
                "source": "paper_list",
            },
        )
        session.commit()

    return PagedPapersResponse(
        items=[PaperItem(paper=o) for o in outs],
        count=total,
    )


@router.get(
    "/{paper_id}",
    summary="논문 개별 조회 (디버그용)",
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
    _get_paper_or_404(session, paper_id)

    out = get_paper_out_by_id(session, user_id=user.id, paper_id=paper_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    create_event(
        session,
        user_id=user.id,
        event_type=EventType.view,
        meta={"paper_id": paper_id, "source": "paper_detail"},
    )
    session.commit()

    return out


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
    outs, total = feed_paper_outs_page(
        session,
        user_id=user.id,
        limit=limit,
        offset=offset,
    )

    return PagedPapersResponse(
        items=[PaperItem(paper=o) for o in outs],
        count=total,
    )
