"""Add editable result table fields.

Revision ID: d0c26a9b4f10
Revises: b173a24d92f0
"""
from alembic import op
import sqlalchemy as sa

revision = "d0c26a9b4f10"
down_revision = "b173a24d92f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("results", sa.Column("terminal_number", sa.String(500), nullable=False, server_default=""))
    op.add_column("results", sa.Column("manual_confirmed", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("results", sa.Column("table_note", sa.String(1000), nullable=False, server_default=""))
    op.add_column("results", sa.Column("table_revision", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    for name in ("table_revision", "table_note", "manual_confirmed", "terminal_number"):
        op.drop_column("results", name)
