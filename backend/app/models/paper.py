# from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Column, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM as PGEnum
from sqlmodel import Field, Relationship, SQLModel

from app.core.enums import SummaryStyle, Site

if TYPE_CHECKING:
    from .user import UserPaperLike, UserPaperView, UserPaperScrap


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PaperTag(SQLModel, table=True):
    __tablename__ = "paper_tags"

    paper_id: int = Field(foreign_key="papers.id", primary_key=True)
    tag_id: int = Field(foreign_key="tags.id", primary_key=True)

    paper: "Paper" = Relationship(back_populates="paper_tags")
    tag: "Tag" = Relationship(back_populates="paper_tags")


class Paper(SQLModel, table=True):
    __tablename__ = "papers"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(nullable=False)
    short: str = Field(nullable=False)
    authors: list[str] = Field(
        default_factory=list,
        sa_column=Column(
            ARRAY(Text),
            nullable=False,
            server_default=text("'{}'::text[]")
        ),
    )
    published_at: datetime = Field(nullable=False)
    image_url: str = Field(nullable=False)
    raw_url: str = Field(nullable=False)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    source: Site = Field(
        sa_column=Column(
            PGEnum(Site,name="site",create_type=False),
            nullable=False
        )
    )

    summaries: list["PaperSummary"] = Relationship(back_populates="paper")
    paper_tags: list["PaperTag"] = Relationship(back_populates="paper")
    tags: list["Tag"] = Relationship(back_populates="papers", link_model=PaperTag)
    user_likes: list["UserPaperLike"] = Relationship(back_populates="paper")
    user_views: list["UserPaperView"] = Relationship(back_populates="paper")
    user_scraps: list["UserPaperScrap"] = Relationship(back_populates="paper")


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
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    paper: "Paper" = Relationship(back_populates="summaries")


class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, index=True)
    description: str = Field(default="", nullable=False)
    count: int = Field(default=0, nullable=False)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    paper_tags: list["PaperTag"] = Relationship(back_populates="tag")
    papers: list["Paper"] = Relationship(
        back_populates="tags", link_model=PaperTag
    )