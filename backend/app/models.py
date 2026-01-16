from datetime import date, datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import EmailStr, BaseModel
from sqlalchemy import Column, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, ENUM as PGEnum
from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthProvider(str, Enum):
    google = "google"
    github = "github"


class SummaryStyle(str, Enum):
    default = "default"
    short = "short"
    detailed = "detailed"


class Site(str, Enum):
    arxiv = "arxiv"
    github = "github"


class EventType(str, Enum):
    view = "view"
    like = "like"
    unlike = "unlike"
    save = "save"
    unsave = "unsave"
    search = "search"


class TagType(str, Enum):
    cs_ai = "cs.AI"
    cs_lg = "cs.LG"
    cs_cv = "cs.CV"
    cs_cl = "cs.CL"


class PaperTag(SQLModel, table=True):
    __tablename__ = "paper_tags"

    paper_id: int = Field(foreign_key="papers.id", primary_key=True)
    tag_id: int = Field(foreign_key="tags.id", primary_key=True)

    paper: "Paper" = Relationship(back_populates="paper_tags")
    tag: "Tag" = Relationship(back_populates="paper_tags")


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


class FolderPaper(SQLModel, table=True):
    __tablename__ = "folder_papers"

    folder_id: int = Field(foreign_key="folders.id", primary_key=True)
    paper_id: int = Field(foreign_key="papers.id", primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    folder: "Folder" = Relationship(back_populates="folder_papers")
    paper: "Paper" = Relationship(back_populates="folder_papers")


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: Optional[EmailStr] = Field(default=None, unique=True, index=True)
    nickname: str = Field(unique=True, index=True, nullable=False)
    profile_image: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    tag_likes: List[TagType] = Field(
        default_factory=list,
        sa_column=Column(
            ARRAY(PGEnum(TagType, name="tag_type", create_type=False)),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )

    meta: Dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )

    auth_identities: List["UserAuthIdentity"] = Relationship(back_populates="user")
    folders: List["Folder"] = Relationship(back_populates="user")
    events: List["Event"] = Relationship(back_populates="user")

    paper_likes: List[UserPaperLike] = Relationship(back_populates="user")
    paper_views: List[UserPaperView] = Relationship(back_populates="user")


class UserAuthIdentity(SQLModel, table=True):
    __tablename__ = "user_auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_provider_user"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)

    provider: AuthProvider = Field(
        sa_column=Column(
            PGEnum(AuthProvider, name="auth_provider", create_type=False),
            nullable=False,
        )
    )
    provider_user_id: str = Field(nullable=False)
    email: Optional[EmailStr] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    user: User = Relationship(back_populates="auth_identities")


class Paper(SQLModel, table=True):
    __tablename__ = "papers"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(nullable=False)
    short: str = Field(nullable=False, description="피드용")

    authors: List[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(Text), nullable=False, server_default=text("'{}'")),
    )

    published_at: Optional[date] = Field(default=None, nullable=True)
    raw_url: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    summaries: List["PaperSummary"] = Relationship(back_populates="paper")

    paper_tags: List[PaperTag] = Relationship(back_populates="paper")
    tags: List["Tag"] = Relationship(back_populates="papers", link_model=PaperTag)

    user_likes: List[UserPaperLike] = Relationship(back_populates="paper")
    user_views: List[UserPaperView] = Relationship(back_populates="paper")

    events: List["Event"] = Relationship(back_populates="paper")
    folder_papers: List[FolderPaper] = Relationship(back_populates="paper")
    folders: List["Folder"] = Relationship(back_populates="papers", link_model=FolderPaper)


class PaperSummary(SQLModel, table=True):
    __tablename__ = "paper_summaries"

    id: Optional[int] = Field(default=None, primary_key=True)
    paper_id: int = Field(foreign_key="papers.id", index=True, nullable=False)

    body: str = Field(nullable=False)

    style: SummaryStyle = Field(
        sa_column=Column(
            PGEnum(SummaryStyle, name="summary_style", create_type=False),
            nullable=False,
        )
    )
    mother: Site = Field(
        sa_column=Column(PGEnum(Site, name="site", create_type=False), nullable=False)
    )

    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    paper: Paper = Relationship(back_populates="summaries")


class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True, nullable=False)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    paper_tags: List[PaperTag] = Relationship(back_populates="tag")
    papers: List[Paper] = Relationship(back_populates="tags", link_model=PaperTag)


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    paper_id: Optional[int] = Field(default=None, foreign_key="papers.id")

    type: EventType = Field(
        sa_column=Column(PGEnum(EventType, name="event_type", create_type=False), nullable=False)
    )
    occurred_at: datetime = Field(default_factory=utcnow, nullable=False)

    meta: Dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )

    user: User = Relationship(back_populates="events")
    paper: Optional[Paper] = Relationship(back_populates="events")


class Folder(SQLModel, table=True):
    __tablename__ = "folders"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_folder_user_name"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)

    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)

    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)

    user: User = Relationship(back_populates="folders")

    folder_papers: List[FolderPaper] = Relationship(back_populates="folder")
    papers: List[Paper] = Relationship(back_populates="folders", link_model=FolderPaper)

class TokenPayload(BaseModel):
    sub: str | None = None
    exp: int | None = None