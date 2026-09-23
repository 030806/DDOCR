"""Task review snapshots and dataset image identities."""
from alembic import op
import sqlalchemy as sa

revision = "d903_dataset_review"
down_revision = "6f02aab98c11"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ocr_jobs", sa.Column("result_version", sa.Integer(), nullable=False, server_default="0"))
    from sqlalchemy.dialects.postgresql import JSONB
    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table("dataset_images",
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("image_id", sa.String(40), unique=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("job_id", sa.String(36)),
        sa.Column("saved_version", sa.Integer()),
        sa.UniqueConstraint("owner_id", "sha256", name="uq_dataset_image_owner_hash"),
    )
    op.create_table("dataset_reviews",
        sa.Column("job_id", sa.String(36), sa.ForeignKey("ocr_jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("reviewed_version", sa.Integer(), nullable=False),
        sa.Column("reviewed_by", sa.String(36), nullable=False),
        sa.Column("reviewed_at", sa.String(40), nullable=False),
        sa.Column("snapshot", json_type, nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("image_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("saved_version", sa.Integer()),
        sa.Column("last_error", sa.Text()),
    )


def downgrade():
    op.drop_table("dataset_reviews")
    op.drop_table("dataset_images")
    op.drop_column("ocr_jobs", "result_version")
