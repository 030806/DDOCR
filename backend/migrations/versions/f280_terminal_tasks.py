"""Terminal strip side associations, reviews and immutable export snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "f280_terminal_tasks"
down_revision = "e71e7f702135"
branch_labels = None
depends_on = None


def upgrade():
    j = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table("terminal_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("links", j, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False))
    op.create_table("terminal_sides",
        sa.Column("task_id", sa.String(36), sa.ForeignKey("terminal_tasks.id"), primary_key=True),
        sa.Column("side", sa.String(5), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("ocr_jobs.id"), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.CheckConstraint("side IN ('left','right')", name="ck_terminal_side"),
        sa.CheckConstraint("page_no > 0", name="ck_terminal_page"))
    op.create_table("terminal_reviews",
        sa.Column("task_id", sa.String(36), sa.ForeignKey("terminal_tasks.id"), primary_key=True),
        sa.Column("row_id", sa.String(64), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(4000), nullable=False),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False))
    op.create_table("terminal_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("terminal_tasks.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("snapshot", j, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False))
    op.create_index("ix_terminal_tasks_user_created", "terminal_tasks", ["user_id", "created_at"])
    op.create_index("ix_terminal_events_task_created", "terminal_events", ["task_id", "created_at"])


def downgrade():
    for name in ("terminal_events", "terminal_reviews", "terminal_sides", "terminal_tasks"):
        op.drop_table(name)
