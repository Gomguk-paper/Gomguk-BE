# from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import Column, text, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.core.enums import EventType


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(SQLModel, table=True):
    __tablename__ = "events"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    event_type: EventType = Field(
        sa_column=Column(Text, nullable=False, index=True),
    )
    occurred_at: datetime = Field(default_factory=utcnow, nullable=False)
    meta: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )