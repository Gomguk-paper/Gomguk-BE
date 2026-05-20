from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Optional, Literal, Any
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Response, status
from redis import Redis
from sqlmodel import select

from app.api.deps import SessionDep, CurrentUser, RedisDep
from app.core.config import settings
from app.core.enums import Site, EventType
from app.crud.event import create_event
from app.crud.paper import (
    list_paper_outs_page,
    feed_paper_outs_page,
    get_paper_out_by_id,
)
from app.models.paper import Paper
from app.models.user import UserPaperLike, UserPaperScrap, UserPaperView
from app.schemas.paper import PaperOut, PaperItem, PagedPapersResponse

router = APIRouter()
PAPER_PAGE_SIZE = 20
PAPER_CACHE_WINDOW_SIZE = 100
PAPER_CACHE_SCAN_COUNT = 100


# =========================
# Helpers
# =========================
def _get_paper_or_404(session: SessionDep, paper_id: int) -> Paper:
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _paper_cache_condition_hash(params: dict[str, Any]) -> str:
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _paper_cache_key(
    *,
    kind: Literal["list", "feed"],
    user_id: int,
    condition_hash: str,
    internal_offset: int,
) -> str:
    return (
        f"papers:{kind}:user:{user_id}:"
        f"cond:{condition_hash}:offset:{internal_offset}"
    )


def _delete_paper_cache_pattern(redis: Redis, pattern: str) -> int:
    deleted = 0
    try:
        for key in redis.scan_iter(match=pattern, count=PAPER_CACHE_SCAN_COUNT):
            deleted += int(redis.delete(key))
    except Exception:
        return deleted
    return deleted


def _delete_paper_cache_group(
    redis: Redis,
    *,
    kind: Literal["list", "feed"],
    user_id: int,
    condition_hash: str,
) -> int:
    return _delete_paper_cache_pattern(
        redis,
        f"papers:{kind}:user:{user_id}:cond:{condition_hash}:offset:*",
    )


def _delete_user_paper_cache(redis: Redis, *, user_id: int) -> int:
    return _delete_paper_cache_pattern(redis, f"papers:*:user:{user_id}:cond:*")


def _get_cached_paper_response(
    redis: Redis,
    *,
    kind: Literal["list", "feed"],
    user_id: int,
    offset: int,
    condition_params: dict[str, Any],
    load_response: Callable[[int], PagedPapersResponse],
) -> PagedPapersResponse:
    condition_hash = _paper_cache_condition_hash(condition_params)
    internal_offset = offset % PAPER_CACHE_WINDOW_SIZE
    refresh_cache = offset > 0 and internal_offset == 0

    if refresh_cache:
        _delete_paper_cache_group(
            redis,
            kind=kind,
            user_id=user_id,
            condition_hash=condition_hash,
        )

    cache_key = _paper_cache_key(
        kind=kind,
        user_id=user_id,
        condition_hash=condition_hash,
        internal_offset=internal_offset,
    )

    cached = None
    if not refresh_cache:
        try:
            cached = redis.get(cache_key)
        except Exception:
            cached = None

    if cached is not None:
        try:
            return PagedPapersResponse.model_validate_json(cached)
        except Exception:
            pass

    response = load_response(internal_offset)

    try:
        redis.setex(
            cache_key,
            settings.PAPER_CACHE_TTL_SECONDS,
            response.model_dump_json(),
        )
    except Exception:
        pass

    return response


def _record_paper_search_event(
    session: SessionDep,
    *,
    user_id: int,
    q: Optional[str],
    tag_filters: list[int],
    source: Optional[Site],
    sort: str,
    limit: int,
    offset: int,
) -> None:
    if not (q or tag_filters or (source is not None)):
        return

    create_event(
        session,
        user_id=user_id,
        event_type=EventType.search,
        meta={
            "query": q,
            "filters": {
                "tags": tag_filters,
                "source": source.value if source is not None else None,
            },
            "sort": sort,
            "limit": limit,
            "offset": offset,
            "source": "paper_list",
        },
    )
    session.commit()


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
    redis: RedisDep,
    user: CurrentUser,
    q: Optional[str] = Query(None, description="제목/요약(short) 검색 (부분 일치)"),
    tags: Optional[list[int]] = Query(None, description="태그 id 필터 (복수, AND 조건)"),
    source: Optional[Site] = Query(None, description="출처(site) 필터 (예: arxiv)"),
    sort: Literal["popular", "recent"] = Query(
        "recent",
        description="정렬 옵션(popular=좋아요순, recent=최신순)",
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    tag_filters = list(dict.fromkeys(tags or []))

    def load_response(internal_offset: int) -> PagedPapersResponse:
        outs, total = list_paper_outs_page(
            session,
            user_id=user.id,
            q=q,
            tags=tag_filters or None,
            source=source,
            sort=sort,
            limit=PAPER_PAGE_SIZE,
            offset=internal_offset,
        )
        return PagedPapersResponse(
            items=[PaperItem(paper=o) for o in outs],
            count=total,
        )

    response = _get_cached_paper_response(
        redis,
        kind="list",
        user_id=user.id,
        offset=offset,
        condition_params={
            "q": q or "",
            "tags": tag_filters,
            "source": source.value if source is not None else "",
            "sort": sort,
        },
        load_response=load_response,
    )

    _record_paper_search_event(
        session,
        user_id=user.id,
        q=q,
        tag_filters=tag_filters,
        source=source,
        sort=sort,
        limit=limit,
        offset=offset,
    )

    return response


@router.get(
    "/feed",
    summary="메인 화면 피드 조회 (추천 시스템 기반)",
    response_model=PagedPapersResponse,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        500: {"description": "Internal Server Error"},
    },
)
def get_feed(
    session: SessionDep,
    redis: RedisDep,
    user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    def load_response(internal_offset: int) -> PagedPapersResponse:
        outs, total = feed_paper_outs_page(
            session,
            user_id=user.id,
            limit=PAPER_PAGE_SIZE,
            offset=internal_offset,
        )
        return PagedPapersResponse(
            items=[PaperItem(paper=o) for o in outs],
            count=total,
        )

    return _get_cached_paper_response(
        redis,
        kind="feed",
        user_id=user.id,
        offset=offset,
        condition_params={},
        load_response=load_response,
    )


@router.delete(
    "/cache",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "AUTH_REQUIRED (?좏겙 ?놁쓬/留뚮즺/?좏슚?섏? ?딆쓬)"},
        500: {"description": "Internal Server Error"},
    },
)
def clear_paper_cache(redis: RedisDep, user: CurrentUser):
    _delete_user_paper_cache(redis, user_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
        404: {"description": "PAPER_NOT_FOUND"},
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
        return Response(status_code=status.HTTP_204_NO_CONTENT)

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
        404: {"description": "PAPER_NOT_FOUND"},
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
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    session.delete(existing)
    create_event(
        session,
        user_id=user.id,
        event_type=EventType.unsave,
        meta={"paper_id": paper_id, "source": "paper_unsave"},
    )
    session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{paper_id}/view",
    summary="읽음(조회) 기록 추가/갱신 (멱등)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        404: {"description": "PAPER_NOT_FOUND"},
        500: {"description": "Internal Server Error"},
    },
)
def mark_paper_viewed(session: SessionDep, user: CurrentUser, paper_id: int):
    _get_paper_or_404(session, paper_id)

    existing = session.exec(
        select(UserPaperView).where(
            UserPaperView.user_id == user.id,
            UserPaperView.paper_id == paper_id,
        )
    ).first()

    now = utcnow()
    if existing:
        existing.last_viewed_at = now
    else:
        session.add(
            UserPaperView(
                user_id=user.id,
                paper_id=paper_id,
                last_viewed_at=now,
            )
        )

    create_event(
        session,
        user_id=user.id,
        event_type=EventType.view,
        meta={"paper_id": paper_id, "source": "paper_view"},
    )

    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
