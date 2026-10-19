"""Store YOLOX detections and effective terminal points.

Revision ID: a1_terminal_pair_points
Revises: c83e4a610b7d
"""
from alembic import op
import sqlalchemy as sa

revision = "a1_terminal_pair_points"
down_revision = "c83e4a610b7d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pages", sa.Column("terminal_model_points", sa.JSON(), nullable=True))
    op.add_column("pages", sa.Column("terminal_points", sa.JSON(), nullable=True))
    op.add_column("pages", sa.Column("terminal_error", sa.JSON(), nullable=True))
    op.add_column("pages", sa.Column("terminal_revision", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("pages", "terminal_revision")
    op.drop_column("pages", "terminal_error")
    op.drop_column("pages", "terminal_points")
    op.drop_column("pages", "terminal_model_points")
