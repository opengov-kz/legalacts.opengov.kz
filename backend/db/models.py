from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    external_id = Column(Integer, nullable=False, unique=True)
    section = Column(String, nullable=False)
    url = Column(String, nullable=False)
    title_ru = Column(String)
    title_kk = Column(String)
    status = Column(String)
    doc_type = Column(String)
    government_body = Column(String)
    created_date = Column(String)
    discussion_end_date = Column(String)
    comments_total = Column(Integer)
    likes_count = Column(Integer)
    dislikes_count = Column(Integer)
    raw_html_ru = Column(Text)
    raw_html_kk = Column(Text)
    first_seen_at = Column(String, nullable=False)
    last_checked_at = Column(String, nullable=False)

    comments = relationship("Comment", back_populates="document", order_by="Comment.id")


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint("document_id", "external_comment_id", name="uq_comment_document_external_id"),
    )

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    external_comment_id = Column(Integer, nullable=False)
    parent_external_comment_id = Column(Integer)
    author_name = Column(String)
    body = Column(Text, nullable=False)
    article_ref = Column(String)
    status = Column(String)
    commented_at_raw = Column(String)
    first_seen_at = Column(String, nullable=False)

    document = relationship("Document", back_populates="comments")


class CrawlQueueEntry(Base):
    __tablename__ = "crawl_queue"

    url = Column(String, primary_key=True)
    page_type = Column(String, nullable=False)
    section = Column(String)
    status = Column(String, nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text)
    discovered_at = Column(String, nullable=False)
    processed_at = Column(String)
