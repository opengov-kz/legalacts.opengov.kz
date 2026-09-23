"""document_versions: history of prior document versions via viewcardhistory

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_act_id", sa.Integer(), sa.ForeignKey("legal_acts.id"), nullable=False),
        sa.Column("external_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer()),
        sa.Column("title_ru", sa.String()),
        sa.Column("status", sa.String()),
        sa.Column("act_type_id", sa.Integer(), sa.ForeignKey("act_types.id")),
        sa.Column("government_body_id", sa.Integer(), sa.ForeignKey("government_bodies.id")),
        sa.Column("created_date", sa.String()),
        sa.Column("discussion_end_date", sa.String()),
        sa.Column("raw_html_ru", sa.Text()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("external_id", name="uq_document_versions_external_id"),
        sa.UniqueConstraint(
            "legal_act_id", "version_number",
            name="uq_document_version_legal_act_version_number",
        ),
    )
    op.create_index(
        "ix_document_versions_legal_act_id", "document_versions", ["legal_act_id"]
    )


def downgrade():
    op.drop_index("ix_document_versions_legal_act_id", table_name="document_versions")
    op.drop_table("document_versions")
