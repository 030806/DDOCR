"""migrate corrections and comments

Revision ID: e78094b5441f
Revises: 444de64a7889
Create Date: 2026-07-22 10:59:03.238418
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e78094b5441f'
down_revision: Union[str, None] = '444de64a7889'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("ocr_corrections", "corrections")
    op.alter_column("corrections", "created_by", new_column_name="user_id")
    op.drop_index("ix_ocr_corrections_result_created", table_name="corrections")
    op.create_index("ix_corrections_result_created", "corrections", ["result_id", "created_at"])

    op.rename_table("ocr_comments", "comments")
    op.alter_column("comments", "created_by", new_column_name="user_id")
    op.drop_index("ix_ocr_comments_result_created", table_name="comments")
    op.create_index("ix_comments_result_created", "comments", ["result_id", "created_at"])

    op.execute(sa.text("""
        INSERT INTO corrections (
            id, result_id, revision, base_revision, corrected_text,
            user_id, created_at
        )
        SELECT
            o.id, r.id,
            COALESCE(NULLIF(o.data->>'revision', '')::integer, 1),
            COALESCE(NULLIF(o.data->>'base_revision', '')::integer,
                     GREATEST(COALESCE(NULLIF(o.data->>'revision', '')::integer, 1) - 1, 0)),
            COALESCE(o.data->>'corrected_text', ''),
            u.id,
            COALESCE(NULLIF(o.data->>'created_at', '')::timestamptz, now())
        FROM objects AS o
        JOIN results AS r ON r.id = o.data->>'result_id'
        JOIN users AS u ON u.id = o.data->'created_by'->>'id'
        WHERE o.kind = 'correction'
        ON CONFLICT (id) DO UPDATE SET
            corrected_text = EXCLUDED.corrected_text,
            revision = EXCLUDED.revision,
            base_revision = EXCLUDED.base_revision,
            user_id = EXCLUDED.user_id
    """))
    op.execute(sa.text("""
        INSERT INTO comments (
            id, result_id, content, user_id,
            created_at, updated_at, deleted_at
        )
        SELECT
            o.id, r.id, COALESCE(o.data->>'content', ''), u.id,
            COALESCE(NULLIF(o.data->>'created_at', '')::timestamptz, now()),
            COALESCE(NULLIF(o.data->>'updated_at', '')::timestamptz,
                     NULLIF(o.data->>'created_at', '')::timestamptz, now()),
            CASE WHEN COALESCE((o.data->>'deleted')::boolean, false) THEN now() END
        FROM objects AS o
        JOIN results AS r ON r.id = o.data->>'result_id'
        JOIN users AS u ON u.id = o.data->'author'->>'id'
        WHERE o.kind = 'comment'
        ON CONFLICT (id) DO UPDATE SET
            content = EXCLUDED.content,
            user_id = EXCLUDED.user_id,
            updated_at = EXCLUDED.updated_at,
            deleted_at = EXCLUDED.deleted_at
    """))


def downgrade() -> None:
    op.drop_index("ix_comments_result_created", table_name="comments")
    op.alter_column("comments", "user_id", new_column_name="created_by")
    op.create_index("ix_ocr_comments_result_created", "comments", ["result_id", "created_at"])
    op.rename_table("comments", "ocr_comments")
    op.drop_index("ix_corrections_result_created", table_name="corrections")
    op.alter_column("corrections", "user_id", new_column_name="created_by")
    op.create_index("ix_ocr_corrections_result_created", "corrections", ["result_id", "created_at"])
    op.rename_table("corrections", "ocr_corrections")
