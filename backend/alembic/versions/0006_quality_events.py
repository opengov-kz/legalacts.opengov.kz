"""quality_events: record-level data quality anomaly log

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quality_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_act_id", sa.Integer(), sa.ForeignKey("legal_acts.id"), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("quality_events")
