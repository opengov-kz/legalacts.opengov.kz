"""baseline schema: government_bodies, act_types, legal_acts, comments, legal_act_snapshots, crawl_queue

Revision ID: 0001
Revises:
Create Date: 2026-09-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "government_bodies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.UniqueConstraint("name", name="uq_government_bodies_name"),
    )
    op.create_table(
        "act_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.UniqueConstraint("name", name="uq_act_types_name"),
    )
    op.create_table(
        "legal_acts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("title_ru", sa.String()),
        sa.Column("title_kk", sa.String()),
        sa.Column("status", sa.String()),
        sa.Column("act_type_id", sa.Integer(), sa.ForeignKey("act_types.id")),
        sa.Column("government_body_id", sa.Integer(), sa.ForeignKey("government_bodies.id")),
        sa.Column("created_date", sa.String()),
        sa.Column("discussion_end_date", sa.String()),
        sa.Column("comments_total", sa.Integer()),
        sa.Column("likes_count", sa.Integer()),
        sa.Column("dislikes_count", sa.Integer()),
        sa.Column("content_sha256_ru", sa.String(length=64)),
        sa.Column("content_sha256_kk", sa.String(length=64)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("external_id", name="uq_legal_acts_external_id"),
    )
    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_act_id", sa.Integer(), sa.ForeignKey("legal_acts.id"), nullable=False),
        sa.Column("external_comment_id", sa.Integer(), nullable=False),
        sa.Column("parent_external_comment_id", sa.Integer()),
        sa.Column("comment_channel", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("author_name", sa.String()),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("article_ref", sa.String()),
        sa.Column("status", sa.String()),
        sa.Column("commented_at_raw", sa.String()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "legal_act_id", "external_comment_id", "comment_channel",
            name="uq_comment_legal_act_external_id_channel",
        ),
    )
    op.create_table(
        "legal_act_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_act_id", sa.Integer(), sa.ForeignKey("legal_acts.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_html_ru", sa.Text()),
        sa.Column("raw_html_kk", sa.Text()),
        sa.Column("content_sha256_ru", sa.String(length=64)),
        sa.Column("content_sha256_kk", sa.String(length=64)),
        sa.Column("title_ru", sa.String()),
        sa.Column("title_kk", sa.String()),
        sa.Column("status", sa.String()),
        sa.Column("act_type_id", sa.Integer(), sa.ForeignKey("act_types.id")),
        sa.Column("government_body_id", sa.Integer(), sa.ForeignKey("government_bodies.id")),
        sa.Column("created_date", sa.String()),
        sa.Column("discussion_end_date", sa.String()),
        sa.Column("comments_total", sa.Integer()),
        sa.Column("likes_count", sa.Integer()),
        sa.Column("dislikes_count", sa.Integer()),
    )
    op.create_index(
        "ix_legal_act_snapshots_legal_act_id_captured_at",
        "legal_act_snapshots", ["legal_act_id", "captured_at"],
    )
    op.create_table(
        "crawl_queue",
        sa.Column("url", sa.String(), primary_key=True),
        sa.Column("page_type", sa.String(), nullable=False),
        sa.Column("section", sa.String()),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_table("crawl_queue")
    op.drop_index("ix_legal_act_snapshots_legal_act_id_captured_at", table_name="legal_act_snapshots")
    op.drop_table("legal_act_snapshots")
    op.drop_table("comments")
    op.drop_table("legal_acts")
    op.drop_table("act_types")
    op.drop_table("government_bodies")
