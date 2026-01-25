# from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .user import User
    from .paper import Paper


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FolderPaper(SQLModel, table=True):
    __tablename__ = "folder_papers"

    folder_id: int = Field(foreign_key="folders.id", primary_key=True)
    paper_id: int = Field(foreign_key="papers.id", primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    folder: "Folder" = Relationship(back_populates="folder_papers")
    paper: "Paper" = Relationship(back_populates="folder_papers")


class Folder(SQLModel, table=True):
    __tablename__ = "folders"
    __table_args__ = (UniqueConstraint(
        "user_id", "name", name="uq_folder_user_name"
    ),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None, nullable=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)

    user: "User" = Relationship(back_populates="folders")
    folder_papers: list["FolderPaper"] = Relationship(back_populates="folder")
    papers: list["Paper"] = Relationship(back_populates="folders", link_model=FolderPaper)