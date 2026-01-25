# from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Any, TYPE_CHECKING
from sqlalchemy import Column, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

from app.core.enums import AuthProvider

if TYPE_CHECKING:
    from .paper import Paper
    from .folder import Folder

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserPaperLike(SQLModel, table=True):
    __tablename__ = "user_paper_likes"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    paper_id: int = Field(foreign_key="papers.id", primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    user: "User" = Relationship(back_populates="paper_likes")
    paper: "Paper" = Relationship(back_populates="user_likes")


class UserPaperView(SQLModel, table=True):
    __tablename__ = "user_paper_views"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    paper_id: int = Field(foreign_key="papers.id", primary_key=True)
    last_viewed_at: datetime = Field(default_factory=utcnow, nullable=False)

    user: "User" = Relationship(back_populates="paper_views")
    paper: "Paper" = Relationship(back_populates="user_views")


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("provider", "provider_sub", name="uq_provider_user"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: Optional[AuthProvider] = Field(default=None, index=True)
    provider_sub: str = Field(default=None, nullable=False, index=True)
    email: str = Field(default=None, unique=True)
    nickname: str = Field(unique=True, nullable=False)
    profile_image: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    meta: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )

    folders: list["Folder"] = Relationship(back_populates="user")
    paper_likes: list["UserPaperLike"] = Relationship(back_populates="user")
    paper_views: list["UserPaperView"] = Relationship(back_populates="user")
