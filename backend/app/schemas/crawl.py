import datetime
from typing import Optional

from pydantic import BaseModel, field_serializer


class CrawlStatusCountOut(BaseModel):
    page_type: str
    status: str
    count: int


class CrawlErrorOut(BaseModel):
    url: str
    page_type: str
    last_error: Optional[str] = None
    processed_at: Optional[datetime.datetime] = None

    @field_serializer("processed_at")
    def _serialize_processed_at(self, value: Optional[datetime.datetime]) -> Optional[str]:
        return value.astimezone(datetime.timezone.utc).isoformat() if value is not None else None


class CrawlStatusOut(BaseModel):
    counts: list[CrawlStatusCountOut]
    last_processed_at: Optional[datetime.datetime] = None
    recent_errors: list[CrawlErrorOut]

    @field_serializer("last_processed_at")
    def _serialize_last_processed_at(self, value: Optional[datetime.datetime]) -> Optional[str]:
        return value.astimezone(datetime.timezone.utc).isoformat() if value is not None else None
