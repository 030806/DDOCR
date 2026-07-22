"""retire generic business store

Revision ID: cae54d372859
Revises: e78094b5441f
Create Date: 2026-07-22 11:12:29.154088
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'cae54d372859'
down_revision: Union[str, None] = 'e78094b5441f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("export_jobs", "exports")
    op.alter_column("exports", "created_by", new_column_name="user_id")
    op.drop_index("ix_export_jobs_job_created", table_name="exports")
    op.create_index("ix_exports_job_created", "exports", ["job_id", "created_at"])
    op.add_column("exports", sa.Column("download_url", sa.Text()))

    op.rename_table("idempotency_keys", "idempotency_records")
    op.drop_index("ix_idempotency_expires_at", table_name="idempotency_records")
    op.create_index(
        "ix_idempotency_records_expires_at",
        "idempotency_records",
        ["expires_at"],
    )

    op.execute(sa.text("""
        INSERT INTO exports (
            id, job_id, user_id, format, mode, scope, status,
            object_key, finished_at, download_url, created_at, updated_at
        )
        SELECT
            o.id, j.id, j.user_id,
            COALESCE(NULLIF(o.data->>'format', ''), 'xlsx'),
            COALESCE(NULLIF(o.data->>'mode', ''), 'full'),
            COALESCE(NULLIF(o.data->>'scope', ''), 'all_pages'),
            COALESCE(NULLIF(o.data->>'status', ''), 'succeeded'),
            'exports/' || o.id || '.xlsx',
            NULLIF(o.data->>'completed_at', '')::timestamptz,
            NULLIF(o.data->>'download_url', ''),
            COALESCE(NULLIF(o.data->>'created_at', '')::timestamptz, now()),
            COALESCE(NULLIF(o.data->>'completed_at', '')::timestamptz,
                     NULLIF(o.data->>'created_at', '')::timestamptz, now())
        FROM objects AS o
        JOIN ocr_jobs AS j ON j.id = o.data->>'job_id'
        WHERE o.kind = 'export'
        ON CONFLICT (id) DO UPDATE SET
            status = EXCLUDED.status,
            object_key = EXCLUDED.object_key,
            finished_at = EXCLUDED.finished_at,
            download_url = EXCLUDED.download_url,
            updated_at = EXCLUDED.updated_at
    """))
    op.execute(sa.text("""
        INSERT INTO idempotency_records (
            id, user_id, route, key, request_hash,
            response_status, response_body, expires_at, created_at
        )
        SELECT
            md5(o.id),
            u.id,
            '/ocr/results/' || split_part(o.id, ':', 3) || '/corrections',
            split_part(o.id, ':', 4),
            md5(o.id) || md5(o.id),
            201,
            o.data::jsonb,
            now() + interval '24 hours',
            now()
        FROM objects AS o
        JOIN users AS u ON u.id = split_part(o.id, ':', 2)
        WHERE o.kind = 'idempotency'
          AND split_part(o.id, ':', 1) = 'correction'
          AND split_part(o.id, ':', 4) <> ''
        ON CONFLICT (id) DO UPDATE SET
            response_body = EXCLUDED.response_body,
            expires_at = EXCLUDED.expires_at
    """))


def downgrade() -> None:
    op.drop_index("ix_idempotency_records_expires_at", table_name="idempotency_records")
    op.create_index("ix_idempotency_expires_at", "idempotency_records", ["expires_at"])
    op.rename_table("idempotency_records", "idempotency_keys")
    op.drop_column("exports", "download_url")
    op.drop_index("ix_exports_job_created", table_name="exports")
    op.alter_column("exports", "user_id", new_column_name="created_by")
    op.create_index("ix_export_jobs_job_created", "exports", ["job_id", "created_at"])
    op.rename_table("exports", "export_jobs")
