# from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Column, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM as PGEnum
from sqlmodel import Field, Relationship, SQLModel

from app.core.enums import SummaryStyle, Site
from app.models.folder import FolderPaper

if TYPE_CHECKING:
    from .folder import Folder
    from .user import UserPaperLike, UserPaperView


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
    folder_papers: list["FolderPaper"] = Relationship(back_populates="paper")
    folders: list["Folder"] = Relationship(
        back_populates="papers", link_model=FolderPaper
    )


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
    name: str = Field(nullable=False)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    paper_tags: list["PaperTag"] = Relationship(back_populates="tag")
    papers: list["Paper"] = Relationship(
        back_populates="tags", link_model=PaperTag
    )