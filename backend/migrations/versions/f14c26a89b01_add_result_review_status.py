"""add result review status

Revision ID: f14c26a89b01
Revises: b173a24d92f0
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f14c26a89b01"
down_revision: Union[str, None] = "b173a24d92f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Batch mode rebuilds the table on SQLite, where ALTER TABLE cannot add a
    # named CHECK constraint. PostgreSQL still uses normal ALTER statements.
    with op.batch_alter_table("results") as batch_op:
        batch_op.add_column(
            sa.Column("review_status", sa.String(length=32), nullable=False, server_default="unreviewed"),
        )
        batch_op.create_check_constraint(
            "ck_results_review_status",
            "review_status IN ('unreviewed', 'confirmed', 'false_positive', 'deleted')",
        )


def downgrade() -> None:
    with op.batch_alter_table("results") as batch_op:
        batch_op.drop_constraint("ck_results_review_status", type_="check")
        batch_op.drop_column("review_status")
