"""quality checks aggregate: nullable QualityEvent.legal_act_id, known_status_values, list_page_totals

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("quality_events", "legal_act_id", nullable=True)
    op.create_table(
        "known_status_values",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("value", name="uq_known_status_values_value"),
    )
    op.create_table(
        "list_page_totals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("total_pages", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("url", name="uq_list_page_totals_url"),
    )


def downgrade():
    op.drop_table("list_page_totals")
    op.drop_table("known_status_values")
    op.alter_column("quality_events", "legal_act_id", nullable=False)
