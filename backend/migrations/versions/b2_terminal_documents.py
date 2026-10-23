"""Separate terminal business records from OCR evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = "b2_terminal_documents"
down_revision = "a1_terminal_pair_points"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("terminal_documents",
        sa.Column("page_id", sa.String(36), sa.ForeignKey("pages.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False))

def downgrade():
    op.drop_table("terminal_documents")
