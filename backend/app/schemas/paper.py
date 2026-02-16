# app/schemas/paper.py
from __future__ import annotations

from typing import Optional
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
    citation_count: int = 0
    recommend_score: Optional[float] = None
    trending_score: Optional[float] = None
    freshness_score: Optional[float] = None

class PaperItem(BaseModel):
    paper: PaperOut

class PagedPapersResponse(BaseModel):
    items: list[PaperItem]
    count: int
