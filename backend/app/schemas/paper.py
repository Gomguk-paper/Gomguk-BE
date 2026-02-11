# app/schemas/paper.py
from __future__ import annotations

from pydantic import BaseModel, Field

class PaperOut(BaseModel):
    id: int
    title: str
    short: str
    authors: list[str]
    year: int
    image_url: str
    raw_url: str
    source: str
    tags: list[int] = Field(default_factory=list)
    is_liked: bool = False
    is_scrapped: bool = False
    like_count: int = 0
    scrap_count: int = 0

class PaperItem(BaseModel):
    paper: PaperOut

class PagedPapersResponse(BaseModel):
    items: list[PaperItem]
    count: int
