from typing import Optional

from pydantic import BaseModel


class CrawlStatusCountOut(BaseModel):
    page_type: str
    status: str
    count: int


class CrawlErrorOut(BaseModel):
    url: str
    page_type: str
    last_error: Optional[str] = None
    processed_at: Optional[str] = None


class CrawlStatusOut(BaseModel):
    counts: list[CrawlStatusCountOut]
    last_processed_at: Optional[str] = None
    recent_errors: list[CrawlErrorOut]
