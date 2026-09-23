"""crawl_queue: consecutive_errors column for error retry policy

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "crawl_queue",
        sa.Column("consecutive_errors", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("crawl_queue", "consecutive_errors", server_default=None)


def downgrade():
    op.drop_column("crawl_queue", "consecutive_errors")
