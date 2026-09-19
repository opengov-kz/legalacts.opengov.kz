from typing import Optional

from pydantic import BaseModel


class SectionCount(BaseModel):
    section: str
    count: int


class StatusCount(BaseModel):
    status: Optional[str]
    count: int


class AnalyticsSummaryOut(BaseModel):
    documents_by_section: list[SectionCount]
    documents_by_status: list[StatusCount]
    total_documents: int
    total_comments: int


class TimeseriesPoint(BaseModel):
    bucket: str
    count: int
