import logging
from datetime import datetime, timezone
from typing import Any, Optional, Union

from sqlmodel import Session

from app.core.enums import EventType
from app.models.event import Event  # 경로 맞춰줘

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_event(
    session: Session,
    *,
    user_id: int,
    event_type: Union[EventType, str],
    meta: Optional[dict[str, Any]] = None,
    occurred_at: Optional[datetime] = None,
) -> None:
    et = event_type.value if isinstance(event_type, EventType) else str(event_type).strip()

    try:
        et = EventType(et).value
    except Exception:
        logger.warning("Invalid event_type=%r (user_id=%s). Skip event.", et, user_id)
        return

    try:
        session.add(
            Event(
                user_id=user_id,
                event_type=et,
                occurred_at=occurred_at or utcnow(),
                meta=meta or {},
            )
        )
    except Exception:
        logger.exception("Failed to create event (user_id=%s, event_type=%s)", user_id, et)
