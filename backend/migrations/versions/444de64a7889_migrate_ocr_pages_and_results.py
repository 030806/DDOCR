"""migrate OCR pages and results

Revision ID: 444de64a7889
Revises: 3670a613f7e1
Create Date: 2026-07-22 10:19:49.844641
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '444de64a7889'
down_revision: Union[str, None] = '3670a613f7e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("ocr_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("image", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("result_ids", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("result_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("review_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processing_ms", sa.Integer()),
        sa.Column("error", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("job_id", "page_no", name="uq_pages_job_page_no"),
    )
    op.create_index("ix_pages_job_page_no", "pages", ["job_id", "page_no"])

    op.rename_table("ocr_results", "results")
    op.drop_index("ix_ocr_results_page_order", table_name="results")
    op.add_column("results", sa.Column("job_id", sa.String(36)))
    op.add_column("results", sa.Column("page_id", sa.String(36)))
    op.add_column("results", sa.Column("page_no", sa.Integer()))
    op.add_column("results", sa.Column("type", sa.String(32), server_default="text_line", nullable=False))
    op.add_column("results", sa.Column("bbox", postgresql.JSONB()))
    op.add_column("results", sa.Column("current_correction", postgresql.JSONB()))
    op.create_foreign_key("fk_results_job_id", "results", "ocr_jobs", ["job_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_results_page_id", "results", "pages", ["page_id"], ["id"], ondelete="CASCADE")

    op.execute(sa.text("""
        INSERT INTO pages (
            id, job_id, page_no, label, status, image, result_ids,
            result_count, review_count, processing_ms, error
        )
        SELECT
            o.id, j.id,
            COALESCE(NULLIF(o.data->>'page_no', '')::integer, 1),
            COALESCE(NULLIF(o.data->>'label', ''), '第 1 页'),
            COALESCE(NULLIF(o.data->>'status', ''), 'succeeded'),
            COALESCE(o.data->'image', '{}'::json)::jsonb,
            COALESCE(o.data->'result_ids', '[]'::json)::jsonb,
            COALESCE(NULLIF(o.data->>'result_count', '')::integer, 0),
            COALESCE(NULLIF(o.data->>'review_count', '')::integer, 0),
            NULLIF(o.data->>'processing_ms', '')::integer,
            o.data->'error'
        FROM objects AS o
        JOIN ocr_jobs AS j ON j.id = o.data->>'job_id'
        WHERE o.kind = 'page'
        ON CONFLICT (id) DO UPDATE SET
            status = EXCLUDED.status,
            image = EXCLUDED.image,
            result_ids = EXCLUDED.result_ids,
            result_count = EXCLUDED.result_count,
            review_count = EXCLUDED.review_count,
            processing_ms = EXCLUDED.processing_ms,
            error = EXCLUDED.error
    """))
    op.execute(sa.text("""
        INSERT INTO results (
            id, job_id, page_id, page_no, type, text, confidence,
            bbox_x1, bbox_y1, bbox_x2, bbox_y2, bbox, polygon,
            reading_order, attributes, current_revision, current_correction
        )
        SELECT
            o.id, j.id, p.id,
            COALESCE(NULLIF(o.data->>'page_no', '')::integer, p.page_no),
            COALESCE(NULLIF(o.data->>'type', ''), 'text_line'),
            COALESCE(o.data->>'text', ''),
            COALESCE(NULLIF(o.data->>'confidence', '')::double precision, 0),
            (o.data->'bbox'->>0)::double precision,
            (o.data->'bbox'->>1)::double precision,
            (o.data->'bbox'->>2)::double precision,
            (o.data->'bbox'->>3)::double precision,
            o.data->'bbox', o.data->'polygon',
            COALESCE(NULLIF(o.data->>'reading_order', '')::integer, 0),
            '{}'::jsonb,
            COALESCE(NULLIF(o.data->>'revision', '')::integer, 0),
            o.data->'current_correction'
        FROM objects AS o
        JOIN ocr_jobs AS j ON j.id = o.data->>'job_id'
        JOIN pages AS p ON p.id = o.data->>'page_id'
        WHERE o.kind = 'result'
        ON CONFLICT (id) DO UPDATE SET
            text = EXCLUDED.text,
            confidence = EXCLUDED.confidence,
            bbox_x1 = EXCLUDED.bbox_x1,
            bbox_y1 = EXCLUDED.bbox_y1,
            bbox_x2 = EXCLUDED.bbox_x2,
            bbox_y2 = EXCLUDED.bbox_y2,
            bbox = EXCLUDED.bbox,
            polygon = EXCLUDED.polygon,
            reading_order = EXCLUDED.reading_order,
            current_revision = EXCLUDED.current_revision,
            current_correction = EXCLUDED.current_correction
    """))
    op.alter_column("results", "job_page_id", existing_type=sa.String(36), nullable=True)
    op.alter_column("results", "job_id", existing_type=sa.String(36), nullable=False)
    op.alter_column("results", "page_id", existing_type=sa.String(36), nullable=False)
    op.alter_column("results", "page_no", existing_type=sa.Integer(), nullable=False)
    op.alter_column("results", "bbox", existing_type=postgresql.JSONB(), nullable=False)
    op.create_index("ix_results_page_order", "results", ["page_id", "reading_order"])


def downgrade() -> None:
    op.drop_index("ix_results_page_order", table_name="results")
    op.drop_constraint("fk_results_page_id", "results", type_="foreignkey")
    op.drop_constraint("fk_results_job_id", "results", type_="foreignkey")
    op.drop_column("results", "current_correction")
    op.drop_column("results", "bbox")
    op.drop_column("results", "type")
    op.drop_column("results", "page_no")
    op.drop_column("results", "page_id")
    op.drop_column("results", "job_id")
    op.alter_column("results", "job_page_id", existing_type=sa.String(36), nullable=False)
    op.rename_table("results", "ocr_results")
    op.create_index("ix_ocr_results_page_order", "ocr_results", ["job_page_id", "reading_order"])
    op.drop_index("ix_pages_job_page_no", table_name="pages")
    op.drop_table("pages")
