"""categories: category/topic taxonomy and legal_act <-> category membership

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.UniqueConstraint("external_id", name="uq_categories_external_id"),
    )
    op.create_table(
        "legal_act_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_act_id", sa.Integer(), sa.ForeignKey("legal_acts.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "legal_act_id", "category_id",
            name="uq_legal_act_categories_legal_act_id_category_id",
        ),
    )


def downgrade():
    op.drop_table("legal_act_categories")
    op.drop_table("categories")
