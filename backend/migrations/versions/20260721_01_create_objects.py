"""Create persistent object store.

Revision ID: 20260721_01
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "20260721_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "objects",
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("kind", "id"),
    )
    op.create_index("ix_objects_kind", "objects", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_objects_kind", table_name="objects")
    op.drop_table("objects")
