from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class GovernmentBody(Base):
    __tablename__ = "government_bodies"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)


class ActType(Base):
    __tablename__ = "act_types"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)


class LegalAct(Base):
    __tablename__ = "legal_acts"

    id = Column(Integer, primary_key=True)
    external_id = Column(Integer, nullable=False, unique=True)
    section = Column(String, nullable=False)
    url = Column(String, nullable=False)
    title_ru = Column(String)
    title_kk = Column(String)
    status = Column(String)
    act_type_id = Column(Integer, ForeignKey("act_types.id"))
    government_body_id = Column(Integer, ForeignKey("government_bodies.id"))
    created_date = Column(String)
    discussion_end_date = Column(String)
    comments_total = Column(Integer)
    likes_count = Column(Integer)
    dislikes_count = Column(Integer)
    content_sha256_ru = Column(String(64))
    content_sha256_kk = Column(String(64))
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_checked_at = Column(DateTime(timezone=True), nullable=False)

    act_type_ref = relationship("ActType")
    government_body_ref = relationship("GovernmentBody")
    doc_type = association_proxy("act_type_ref", "name")
    government_body = association_proxy("government_body_ref", "name")

    comments = relationship("Comment", back_populates="legal_act", order_by="Comment.id")
    snapshots = relationship(
        "LegalActSnapshot", back_populates="legal_act", order_by="LegalActSnapshot.captured_at"
    )
    document_versions = relationship(
        "DocumentVersion", back_populates="legal_act", order_by="DocumentVersion.version_number"
    )
    report = relationship("Report", back_populates="legal_act", uselist=False)


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint(
            "legal_act_id", "external_comment_id", "comment_channel",
            name="uq_comment_legal_act_external_id_channel",
        ),
    )

    id = Column(Integer, primary_key=True)
    legal_act_id = Column(Integer, ForeignKey("legal_acts.id"), nullable=False)
    external_comment_id = Column(Integer, nullable=False)
    parent_external_comment_id = Column(Integer)
    comment_channel = Column(Integer, nullable=False, default=6)
    author_name = Column(String)
    body = Column(Text, nullable=False)
    article_ref = Column(String)
    status = Column(String)
    commented_at_raw = Column(String)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)

    legal_act = relationship("LegalAct", back_populates="comments")


class LegalActSnapshot(Base):
    __tablename__ = "legal_act_snapshots"
    __table_args__ = (
        Index("ix_legal_act_snapshots_legal_act_id_captured_at", "legal_act_id", "captured_at"),
    )

    id = Column(Integer, primary_key=True)
    legal_act_id = Column(Integer, ForeignKey("legal_acts.id"), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    raw_html_ru = Column(Text)
    raw_html_kk = Column(Text)
    content_sha256_ru = Column(String(64))
    content_sha256_kk = Column(String(64))
    title_ru = Column(String)
    title_kk = Column(String)
    status = Column(String)
    act_type_id = Column(Integer, ForeignKey("act_types.id"))
    government_body_id = Column(Integer, ForeignKey("government_bodies.id"))
    created_date = Column(String)
    discussion_end_date = Column(String)
    comments_total = Column(Integer)
    likes_count = Column(Integer)
    dislikes_count = Column(Integer)

    legal_act = relationship("LegalAct", back_populates="snapshots")


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "legal_act_id", "version_number",
            name="uq_document_version_legal_act_version_number",
        ),
        Index("ix_document_versions_legal_act_id", "legal_act_id"),
    )

    id = Column(Integer, primary_key=True)
    legal_act_id = Column(Integer, ForeignKey("legal_acts.id"), nullable=False)
    external_id = Column(Integer, nullable=False, unique=True)
    version_number = Column(Integer)
    title_ru = Column(String)
    status = Column(String)
    act_type_id = Column(Integer, ForeignKey("act_types.id"))
    government_body_id = Column(Integer, ForeignKey("government_bodies.id"))
    created_date = Column(String)
    discussion_end_date = Column(String)
    raw_html_ru = Column(Text)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)

    legal_act = relationship("LegalAct", back_populates="document_versions")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    legal_act_id = Column(Integer, ForeignKey("legal_acts.id"), nullable=False, unique=True)
    raw_html_ru = Column(Text)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)

    legal_act = relationship("LegalAct", back_populates="report")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    external_id = Column(Integer, nullable=False, unique=True)
    name = Column(String, nullable=False)


class LegalActCategory(Base):
    __tablename__ = "legal_act_categories"
    __table_args__ = (
        UniqueConstraint(
            "legal_act_id", "category_id",
            name="uq_legal_act_categories_legal_act_id_category_id",
        ),
    )

    id = Column(Integer, primary_key=True)
    legal_act_id = Column(Integer, ForeignKey("legal_acts.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)


class CrawlQueueEntry(Base):
    __tablename__ = "crawl_queue"

    url = Column(String, primary_key=True)
    page_type = Column(String, nullable=False)
    section = Column(String)
    status = Column(String, nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    consecutive_errors = Column(Integer, nullable=False, default=0)
    last_error = Column(Text)
    discovered_at = Column(DateTime(timezone=True), nullable=False)
    processed_at = Column(DateTime(timezone=True))
