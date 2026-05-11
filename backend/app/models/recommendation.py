from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, Numeric, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Interaction(SQLModel, table=True):
    __tablename__ = "interactions"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", "paper_id", name="uq_interactions_user_request_paper"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    paper_id: int = Field(foreign_key="papers.id", index=True, nullable=False)

    # 0 = impression, 1 = view
    interaction_type: int = Field(
        default=0,
        sa_column=Column(SmallInteger, nullable=False, server_default="0"),
    )
    is_liked: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    is_scrapped: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )

    request_id: str = Field(
        sa_column=Column(String(length=255), nullable=False, index=True),
    )
    surface: str = Field(
        sa_column=Column(String(length=50), nullable=False),
    )
    position: int = Field(sa_column=Column(Integer, nullable=False))

    visible_ms: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    visible_ratio_max: float = Field(
        default=0,
        sa_column=Column(Numeric(6, 4), nullable=False, server_default="0"),
    )
    dwell_ms: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utcnow),
    )


class UserShortMemory(SQLModel, table=True):
    __tablename__ = "user_short_memories"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    recent_embedding: list[float] = Field(
        default_factory=list,
        sa_column=Column(
            ARRAY(Float),
            nullable=False,
            server_default=text("'{}'::double precision[]"),
        ),
    )
    category_score: dict[str, float] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    recent_seen_paper_ids: list[int] = Field(
        default_factory=list,
        sa_column=Column(
            ARRAY(Integer),
            nullable=False,
            server_default=text("'{}'::integer[]"),
        ),
    )
    last_updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
