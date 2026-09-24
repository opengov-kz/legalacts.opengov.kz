"""legal_acts: views_count column (source page-view counter)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("legal_acts", sa.Column("views_count", sa.Integer()))


def downgrade():
    op.drop_column("legal_acts", "views_count")
