from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import SessionDep
from app.models.event import Event

router = APIRouter()


# =========================
# Response Schemas
# =========================
class EventOut(BaseModel):
    id: int
    user_id: int
    event_type: str
    occurred_at: str
    meta: dict[str, Any]


class RecentEventsResponse(BaseModel):
    items: list[EventOut]
    count: int


# =========================
# Routes
# =========================
@router.get(
    "/recent",
    response_model=RecentEventsResponse,
    summary="최근 이벤트 조회 (디버그/테스트용)",
    description=(
        "- Auth: 없음\n"
        "- 전체 유저의 이벤트를 occurred_at 최신순(동률 시 id 최신순)으로 반환\n"
        "- 이벤트 기록(create_event) 동작 확인용"
    ),
    response_description="최근 이벤트 목록",
)
def get_recent_events(
    session: SessionDep,
    limit: int = Query(20, ge=1, le=200, description="반환 개수 (기본 20, 1~200)"),
) -> RecentEventsResponse:
    stmt = (
        select(Event)
        .order_by(Event.occurred_at.desc(), Event.id.desc())
        .limit(limit)
    )
    rows = session.exec(stmt).all()

    items = [
        EventOut(
            id=e.id,
            user_id=e.user_id,
            event_type=str(e.event_type),
            occurred_at=e.occurred_at.isoformat(),
            meta=e.meta or {},
        )
        for e in rows
        if e.id is not None
    ]

    return RecentEventsResponse(items=items, count=len(items))
