from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

from app.core.enums import Site


class PaperRead(BaseModel):
    id: int
    title: str
    short: str
    authors: list[str] = Field(default_factory=list)
    published_at: datetime
    image_url: str
    raw_url: str
    source: Site
    tags: list[str] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)