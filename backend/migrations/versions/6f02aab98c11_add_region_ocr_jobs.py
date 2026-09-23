"""add region OCR jobs

Revision ID: 6f02aab98c11
Revises: a62d731c90ef
Create Date: 2026-08-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "6f02aab98c11"
down_revision: Union[str, None] = "a62d731c90ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ocr_region_job_scopes",
        sa.Column("job_id", sa.String(36), sa.ForeignKey("ocr_jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("source_job_id", sa.String(36), sa.ForeignKey("ocr_jobs.id", ondelete="SET NULL")),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("region_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("region_count > 0", name="ck_region_job_scopes_count"),
    )
    op.create_index("ix_region_job_scopes_source", "ocr_region_job_scopes", ["source_job_id"])
    op.create_table(
        "ocr_job_regions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("ocr_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(100), nullable=False),
        sa.Column("bbox", sa.JSON(), nullable=False),
        sa.Column("reading_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("job_id", "client_id", name="uq_ocr_job_regions_client"),
        sa.UniqueConstraint("job_id", "page_no", "reading_order", name="uq_ocr_job_regions_order"),
        sa.CheckConstraint("page_no > 0", name="ck_ocr_job_regions_page_no"),
    )
    op.create_index("ix_ocr_job_regions_job_page", "ocr_job_regions", ["job_id", "page_no"])


def downgrade() -> None:
    op.drop_index("ix_ocr_job_regions_job_page", table_name="ocr_job_regions")
    op.drop_table("ocr_job_regions")
    op.drop_index("ix_region_job_scopes_source", table_name="ocr_region_job_scopes")
    op.drop_table("ocr_region_job_scopes")
