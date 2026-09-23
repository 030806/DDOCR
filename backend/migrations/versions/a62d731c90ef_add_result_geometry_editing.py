"""add result geometry editing

Revision ID: a62d731c90ef
Revises: f14c26a89b01
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a62d731c90ef"
down_revision: Union[str, None] = "f14c26a89b01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("results") as batch_op:
        batch_op.add_column(sa.Column("geometry_revision", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "result_geometry_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("result_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("previous_bbox", sa.JSON(), nullable=True),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["result_id"], ["results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("result_id", "revision", name="uq_result_geometry_revision"),
    )
    op.create_index("ix_result_geometry_result_created", "result_geometry_revisions", ["result_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_result_geometry_result_created", table_name="result_geometry_revisions")
    op.drop_table("result_geometry_revisions")
    with op.batch_alter_table("results") as batch_op:
        batch_op.drop_column("geometry_revision")
