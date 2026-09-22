import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_serializer


class DocumentListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: int
    section: str
    url: str
    title_ru: Optional[str] = None
    title_kk: Optional[str] = None
    status: Optional[str] = None
    doc_type: Optional[str] = None
    government_body: Optional[str] = None
    created_date: Optional[str] = None
    discussion_end_date: Optional[str] = None
    comments_total: Optional[int] = None
    likes_count: Optional[int] = None
    dislikes_count: Optional[int] = None
    first_seen_at: datetime.datetime
    last_checked_at: datetime.datetime

    @field_serializer("first_seen_at", "last_checked_at")
    def _serialize_datetime(self, value: datetime.datetime) -> str:
        return value.isoformat()


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_comment_id: int
    parent_external_comment_id: Optional[int] = None
    author_name: Optional[str] = None
    body: str
    article_ref: Optional[str] = None
    status: Optional[str] = None
    commented_at_raw: Optional[str] = None
    first_seen_at: datetime.datetime

    @field_serializer("first_seen_at")
    def _serialize_first_seen_at(self, value: datetime.datetime) -> str:
        return value.isoformat()


class DocumentDetailOut(DocumentListItemOut):
    comments: list[CommentOut]
