"""reports: raw HTML of discussion result reports via /report

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_act_id", sa.Integer(), sa.ForeignKey("legal_acts.id"), nullable=False),
        sa.Column("raw_html_ru", sa.Text()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("legal_act_id", name="uq_reports_legal_act_id"),
    )


def downgrade():
    op.drop_table("reports")
