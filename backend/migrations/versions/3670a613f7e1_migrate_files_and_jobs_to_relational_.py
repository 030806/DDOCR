"""migrate files and jobs to relational tables

Revision ID: 3670a613f7e1
Revises: 622436c321e7
Create Date: 2026-07-21 20:46:26.324458
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '3670a613f7e1'
down_revision: Union[str, None] = '622436c321e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("file_objects", "files")
    op.alter_column("files", "owner_id", new_column_name="user_id")
    op.drop_index("ix_file_objects_tenant_owner_created", table_name="files")
    op.create_index("ix_files_tenant_user_created", "files", ["tenant_id", "user_id", "created_at"])
    op.add_column("files", sa.Column("actual_size_bytes", sa.BigInteger()))
    op.add_column("files", sa.Column("width_px", sa.Integer()))
    op.add_column("files", sa.Column("height_px", sa.Integer()))

    op.alter_column("ocr_jobs", "created_by", new_column_name="user_id")
    op.drop_index("ix_ocr_jobs_creator_created", table_name="ocr_jobs")
    op.create_index("ix_ocr_jobs_user_created", "ocr_jobs", ["user_id", "created_at"])
    op.alter_column("ocr_jobs", "model_version_id", existing_type=sa.String(36), nullable=True)
    op.add_column("ocr_jobs", sa.Column("file_name", sa.String(500)))
    op.add_column("ocr_jobs", sa.Column("model_id", sa.String(100)))
    op.add_column("ocr_jobs", sa.Column("model_version", sa.String(100)))
    op.add_column("ocr_jobs", sa.Column("page_ids", postgresql.JSONB(), server_default="[]", nullable=False))
    op.add_column("ocr_jobs", sa.Column("review_count", sa.Integer(), server_default="0", nullable=False))
    op.execute(sa.text("""
        UPDATE ocr_jobs AS j
        SET file_name = (SELECT f.file_name FROM files AS f WHERE f.id = j.file_id),
            model_id = COALESCE((
                SELECT m.id FROM model_versions AS mv
                JOIN models AS m ON m.id = mv.model_id
                WHERE mv.id = j.model_version_id
            ), 'mock'),
            model_version = COALESCE((
                SELECT mv.version FROM model_versions AS mv
                WHERE mv.id = j.model_version_id
            ), '1.0.0')
    """))
    op.alter_column("ocr_jobs", "file_name", existing_type=sa.String(500), nullable=False)
    op.alter_column("ocr_jobs", "model_id", existing_type=sa.String(100), nullable=False)
    op.alter_column("ocr_jobs", "model_version", existing_type=sa.String(100), nullable=False)

    op.execute(sa.text("""
        INSERT INTO files (
            id, tenant_id, user_id, file_name, declared_mime_type,
            actual_mime_type, size_bytes, actual_size_bytes, sha256, object_key,
            page_count, width_px, height_px, status, failure_reason,
            deleted_at, created_at, updated_at
        )
        SELECT
            o.id, u.tenant_id, u.id,
            COALESCE(NULLIF(o.data->>'file_name', ''), 'unnamed'),
            COALESCE(NULLIF(o.data->>'media_type', ''), 'application/octet-stream'),
            NULLIF(o.data->>'actual_media_type', ''),
            COALESCE(NULLIF(o.data->>'size_bytes', '')::bigint, 0),
            NULLIF(o.data->>'actual_size_bytes', '')::bigint,
            NULLIF(o.data->>'sha256', ''),
            COALESCE(NULLIF(o.data->>'storage_path', ''), 'uploads/' || o.id),
            NULLIF(o.data->>'page_count', '')::integer,
            NULLIF(o.data->>'width_px', '')::integer,
            NULLIF(o.data->>'height_px', '')::integer,
            COALESCE(NULLIF(o.data->>'status', ''), 'uploading'),
            NULLIF(o.data->>'failure_reason', ''),
            CASE WHEN COALESCE((o.data->>'deleted')::boolean, false) THEN now() END,
            COALESCE(NULLIF(o.data->>'created_at', '')::timestamptz, now()),
            COALESCE(NULLIF(o.data->>'updated_at', '')::timestamptz,
                     NULLIF(o.data->>'created_at', '')::timestamptz, now())
        FROM objects AS o
        JOIN users AS u ON u.id = o.data->>'owner_id'
        WHERE o.kind = 'file'
        ON CONFLICT (id) DO UPDATE SET
            file_name = EXCLUDED.file_name,
            actual_mime_type = EXCLUDED.actual_mime_type,
            actual_size_bytes = EXCLUDED.actual_size_bytes,
            page_count = EXCLUDED.page_count,
            width_px = EXCLUDED.width_px,
            height_px = EXCLUDED.height_px,
            status = EXCLUDED.status,
            failure_reason = EXCLUDED.failure_reason,
            deleted_at = EXCLUDED.deleted_at,
            updated_at = EXCLUDED.updated_at
    """))
    op.execute(sa.text("""
        INSERT INTO ocr_jobs (
            id, tenant_id, user_id, file_id, file_name, model_id, model_version,
            name, options_snapshot, status, stage, review_status, progress,
            page_total, page_succeeded, page_failed, result_count, review_count,
            page_ids, started_at, finished_at, deleted_at, created_at, updated_at
        )
        SELECT
            o.id, u.tenant_id, u.id, f.id, f.file_name,
            COALESCE(NULLIF(o.data->>'model_id', ''), 'mock'),
            COALESCE(NULLIF(o.data->>'model_version', ''), '1.0.0'),
            COALESCE(NULLIF(o.data->>'name', ''), 'OCR Job'),
            '{}'::jsonb,
            COALESCE(NULLIF(o.data->>'status', ''), 'queued'),
            COALESCE(NULLIF(o.data->>'stage', ''), 'queued'),
            'unreviewed',
            COALESCE(NULLIF(o.data->>'progress', '')::integer, 0),
            COALESCE(NULLIF(o.data->>'page_count', '')::integer, 0),
            COALESCE(NULLIF(o.data->>'completed_pages', '')::integer, 0),
            COALESCE(NULLIF(o.data->>'failed_pages', '')::integer, 0),
            COALESCE(NULLIF(o.data->>'result_count', '')::integer, 0),
            COALESCE(NULLIF(o.data->>'review_count', '')::integer, 0),
            COALESCE(o.data->'page_ids', '[]'::json)::jsonb,
            NULLIF(o.data->>'started_at', '')::timestamptz,
            NULLIF(o.data->>'finished_at', '')::timestamptz,
            CASE WHEN COALESCE((o.data->>'deleted')::boolean, false) THEN now() END,
            COALESCE(NULLIF(o.data->>'created_at', '')::timestamptz, now()),
            COALESCE(NULLIF(o.data->>'updated_at', '')::timestamptz,
                     NULLIF(o.data->>'created_at', '')::timestamptz, now())
        FROM objects AS o
        JOIN users AS u ON u.id = o.data->>'owner_id'
        JOIN files AS f ON f.id = o.data->>'file_id'
        WHERE o.kind = 'job'
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            status = EXCLUDED.status,
            stage = EXCLUDED.stage,
            progress = EXCLUDED.progress,
            page_total = EXCLUDED.page_total,
            page_succeeded = EXCLUDED.page_succeeded,
            page_failed = EXCLUDED.page_failed,
            result_count = EXCLUDED.result_count,
            review_count = EXCLUDED.review_count,
            page_ids = EXCLUDED.page_ids,
            finished_at = EXCLUDED.finished_at,
            deleted_at = EXCLUDED.deleted_at,
            updated_at = EXCLUDED.updated_at
    """))


def downgrade() -> None:
    op.drop_column("ocr_jobs", "review_count")
    op.drop_column("ocr_jobs", "page_ids")
    op.drop_column("ocr_jobs", "model_version")
    op.drop_column("ocr_jobs", "model_id")
    op.drop_column("ocr_jobs", "file_name")
    op.alter_column("ocr_jobs", "model_version_id", existing_type=sa.String(36), nullable=False)
    op.drop_index("ix_ocr_jobs_user_created", table_name="ocr_jobs")
    op.alter_column("ocr_jobs", "user_id", new_column_name="created_by")
    op.create_index("ix_ocr_jobs_creator_created", "ocr_jobs", ["created_by", "created_at"])
    op.drop_column("files", "height_px")
    op.drop_column("files", "width_px")
    op.drop_column("files", "actual_size_bytes")
    op.drop_index("ix_files_tenant_user_created", table_name="files")
    op.alter_column("files", "user_id", new_column_name="owner_id")
    op.create_index("ix_file_objects_tenant_owner_created", "files", ["tenant_id", "owner_id", "created_at"])
    op.rename_table("files", "file_objects")
