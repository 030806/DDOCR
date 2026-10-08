"""Add soft deletion to terminal strip tasks."""
from alembic import op
import sqlalchemy as sa

revision = "c83e4a610b7d"
down_revision = "f280_terminal_tasks"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("terminal_tasks", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("terminal_tasks", "deleted_at")
