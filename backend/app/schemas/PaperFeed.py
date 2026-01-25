from pydantic import BaseModel, ConfigDict
from datetime import datetime

from app.core.enums import Site, SummaryStyle, TagType


class PaperFeedItem(BaseModel):
    id: int
    title: str

    # 카드에 보이는 짧은 요약(1~2줄)
    teaser: str | None = None

    # 요약 스타일(기본값은 default)
    style: SummaryStyle = SummaryStyle.default

    # 썸네일(카드 이미지)
    thumbnail_url: str | None = None

    # 링크들
    raw_url: str
    pdf_url: str | None = None   # 없으면 raw_url로 대체 가능
    site: Site

    # 태그 칩
    tags: list[TagType] = []

    # 메타 정보(카드 하단 작은 글씨용)
    authors: list[str] = []           # ["Kirillov, A.", "Mintun, E.", ...]
    venue: str | None = None          # "ICCV" 같은 컨퍼런스/저널
    published_at: datetime | None = None
    citation_count: int | None = None

    # 집계/상태(피드에서 바로 눌러야 하니까)
    like_count: int = 0
    scrap_count: int = 0
    is_liked: bool = False
    is_scrapped: bool = False

    model_config = ConfigDict(from_attributes=True)


class PaperFeed(BaseModel):
    items: list[PaperFeedItem]
    next_cursor: str | None = None