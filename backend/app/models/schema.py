"""Relational database schema described by docs/03_Backend.md."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.models.store import Base

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


def id_column() -> Column[str]:
    return Column("id", String(36), primary_key=True)


def timestamps() -> tuple[Column[DateTime], Column[DateTime]]:
    return (
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


tenants = Table(
    "tenants", Base.metadata,
    id_column(),
    Column("name", String(200), nullable=False),
    Column("slug", String(100), nullable=False, unique=True),
    Column("status", String(32), nullable=False, server_default="active"),
    Column("settings", JSON_VALUE, nullable=False, server_default="{}"),
    *timestamps(),
    CheckConstraint("status IN ('active','suspended','disabled')", name="ck_tenants_status"),
)

users = Table(
    "users", Base.metadata,
    id_column(),
    Column("tenant_id", String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
    Column("external_subject", String(255)),
    Column("name", String(100), nullable=False),
    Column("email", String(320)),
    Column("phone", String(32)),
    Column("employee_no", String(100)),
    Column("department", String(200)),
    Column("password_salt", String(64)),
    Column("password_hash", String(128)),
    Column("status", String(32), nullable=False, server_default="active"),
    Column("last_login_at", DateTime(timezone=True)),
    Column("deleted_at", DateTime(timezone=True)),
    *timestamps(),
    UniqueConstraint("tenant_id", "external_subject", name="uq_users_tenant_subject"),
    UniqueConstraint("tenant_id", "employee_no", name="uq_users_tenant_employee_no"),
    UniqueConstraint("tenant_id", "phone", name="uq_users_tenant_phone"),
    CheckConstraint("status IN ('active','locked','disabled')", name="ck_users_status"),
)
Index("ix_users_tenant_status", users.c.tenant_id, users.c.status)

user_preferences = Table(
    "user_preferences", Base.metadata,
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("preferences_version", Integer, nullable=False, server_default="1"),
    Column("settings", JSON_VALUE, nullable=False, server_default="{}"),
    *timestamps(),
)

models = Table(
    "models", Base.metadata,
    id_column(),
    Column("tenant_id", String(36), ForeignKey("tenants.id", ondelete="CASCADE")),
    Column("name", String(200), nullable=False),
    Column("description", Text),
    Column("capabilities", JSON_VALUE, nullable=False, server_default="[]"),
    Column("languages", JSON_VALUE, nullable=False, server_default="[]"),
    Column("status", String(32), nullable=False, server_default="available"),
    *timestamps(),
    CheckConstraint("status IN ('available','disabled','archived')", name="ck_models_status"),
)

model_versions = Table(
    "model_versions", Base.metadata,
    id_column(),
    Column("model_id", String(36), ForeignKey("models.id", ondelete="CASCADE"), nullable=False),
    Column("version", String(100), nullable=False),
    Column("runtime", String(64), nullable=False),
    Column("artifact_uri", Text, nullable=False),
    Column("artifact_sha256", String(64), nullable=False),
    Column("config", JSON_VALUE, nullable=False, server_default="{}"),
    Column("input_limits", JSON_VALUE, nullable=False, server_default="{}"),
    Column("status", String(32), nullable=False, server_default="available"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("model_id", "version", name="uq_model_versions_model_version"),
)

file_objects = Table(
    "file_objects", Base.metadata,
    id_column(),
    Column("tenant_id", String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
    Column("owner_id", String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("file_name", String(500), nullable=False),
    Column("declared_mime_type", String(255), nullable=False),
    Column("actual_mime_type", String(255)),
    Column("size_bytes", BigInteger, nullable=False),
    Column("sha256", String(64)),
    Column("object_key", Text, nullable=False),
    Column("page_count", Integer),
    Column("status", String(32), nullable=False, server_default="uploading"),
    Column("failure_reason", Text),
    Column("deleted_at", DateTime(timezone=True)),
    *timestamps(),
    CheckConstraint("size_bytes >= 0", name="ck_file_objects_size"),
)
Index("ix_file_objects_tenant_owner_created", file_objects.c.tenant_id, file_objects.c.owner_id, file_objects.c.created_at)

document_pages = Table(
    "document_pages", Base.metadata,
    id_column(),
    Column("file_id", String(36), ForeignKey("file_objects.id", ondelete="CASCADE"), nullable=False),
    Column("page_no", Integer, nullable=False),
    Column("image_object_key", Text, nullable=False),
    Column("thumbnail_object_key", Text),
    Column("width_px", Integer, nullable=False),
    Column("height_px", Integer, nullable=False),
    Column("dpi", Integer),
    Column("rotation", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("file_id", "page_no", name="uq_document_pages_file_page_no"),
    CheckConstraint("page_no > 0", name="ck_document_pages_page_no"),
    CheckConstraint("width_px > 0 AND height_px > 0", name="ck_document_pages_dimensions"),
)

ocr_jobs = Table(
    "ocr_jobs", Base.metadata,
    id_column(),
    Column("tenant_id", String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
    Column("created_by", String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("file_id", String(36), ForeignKey("file_objects.id", ondelete="RESTRICT"), nullable=False),
    Column("model_version_id", String(36), ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False),
    Column("name", String(500), nullable=False),
    Column("options_snapshot", JSON_VALUE, nullable=False, server_default="{}"),
    Column("status", String(32), nullable=False, server_default="queued"),
    Column("stage", String(64), nullable=False, server_default="queued"),
    Column("review_status", String(32), nullable=False, server_default="unreviewed"),
    Column("progress", Integer, nullable=False, server_default="0"),
    Column("page_total", Integer, nullable=False, server_default="0"),
    Column("page_succeeded", Integer, nullable=False, server_default="0"),
    Column("page_failed", Integer, nullable=False, server_default="0"),
    Column("result_count", Integer, nullable=False, server_default="0"),
    Column("error_code", String(100)),
    Column("error_message", Text),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("cancel_requested_at", DateTime(timezone=True)),
    Column("deleted_at", DateTime(timezone=True)),
    *timestamps(),
    CheckConstraint("progress BETWEEN 0 AND 100", name="ck_ocr_jobs_progress"),
)
Index("ix_ocr_jobs_tenant_status_created", ocr_jobs.c.tenant_id, ocr_jobs.c.status, ocr_jobs.c.created_at)
Index("ix_ocr_jobs_creator_created", ocr_jobs.c.created_by, ocr_jobs.c.created_at)

job_pages = Table(
    "job_pages", Base.metadata,
    id_column(),
    Column("job_id", String(36), ForeignKey("ocr_jobs.id", ondelete="CASCADE"), nullable=False),
    Column("page_id", String(36), ForeignKey("document_pages.id", ondelete="RESTRICT"), nullable=False),
    Column("status", String(32), nullable=False, server_default="queued"),
    Column("result_count", Integer, nullable=False, server_default="0"),
    Column("duration_ms", Integer),
    Column("retry_count", Integer, nullable=False, server_default="0"),
    Column("error_code", String(100)),
    Column("error_message", Text),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    *timestamps(),
    UniqueConstraint("job_id", "page_id", name="uq_job_pages_job_page"),
)

ocr_results = Table(
    "ocr_results", Base.metadata,
    id_column(),
    Column("job_page_id", String(36), ForeignKey("job_pages.id", ondelete="CASCADE"), nullable=False),
    Column("text", Text, nullable=False),
    Column("confidence", Float, nullable=False),
    Column("bbox_x1", Float, nullable=False),
    Column("bbox_y1", Float, nullable=False),
    Column("bbox_x2", Float, nullable=False),
    Column("bbox_y2", Float, nullable=False),
    Column("polygon", JSON_VALUE),
    Column("angle", Float),
    Column("reading_order", Integer, nullable=False),
    Column("attributes", JSON_VALUE, nullable=False, server_default="{}"),
    Column("current_revision", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_ocr_results_confidence"),
    CheckConstraint("bbox_x2 >= bbox_x1 AND bbox_y2 >= bbox_y1", name="ck_ocr_results_bbox"),
)
Index("ix_ocr_results_page_order", ocr_results.c.job_page_id, ocr_results.c.reading_order)

ocr_corrections = Table(
    "ocr_corrections", Base.metadata,
    id_column(),
    Column("result_id", String(36), ForeignKey("ocr_results.id", ondelete="CASCADE"), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("base_revision", Integer, nullable=False),
    Column("corrected_text", Text, nullable=False),
    Column("created_by", String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("reverts_correction_id", String(36), ForeignKey("ocr_corrections.id", ondelete="SET NULL")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("result_id", "revision", name="uq_ocr_corrections_result_revision"),
)
Index("ix_ocr_corrections_result_created", ocr_corrections.c.result_id, ocr_corrections.c.created_at)

ocr_comments = Table(
    "ocr_comments", Base.metadata,
    id_column(),
    Column("result_id", String(36), ForeignKey("ocr_results.id", ondelete="CASCADE"), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_by", String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("deleted_at", DateTime(timezone=True)),
    *timestamps(),
)
Index("ix_ocr_comments_result_created", ocr_comments.c.result_id, ocr_comments.c.created_at)

export_jobs = Table(
    "export_jobs", Base.metadata,
    id_column(),
    Column("job_id", String(36), ForeignKey("ocr_jobs.id", ondelete="CASCADE"), nullable=False),
    Column("created_by", String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("format", String(20), nullable=False),
    Column("mode", String(32), nullable=False),
    Column("scope", String(32), nullable=False),
    Column("status", String(32), nullable=False, server_default="queued"),
    Column("object_key", Text),
    Column("expires_at", DateTime(timezone=True)),
    Column("error_code", String(100)),
    Column("error_message", Text),
    Column("finished_at", DateTime(timezone=True)),
    *timestamps(),
)
Index("ix_export_jobs_job_created", export_jobs.c.job_id, export_jobs.c.created_at)

idempotency_keys = Table(
    "idempotency_keys", Base.metadata,
    id_column(),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("route", String(500), nullable=False),
    Column("key", String(255), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_status", Integer, nullable=False),
    Column("response_body", JSON_VALUE, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("user_id", "route", "key", name="uq_idempotency_user_route_key"),
)
Index("ix_idempotency_expires_at", idempotency_keys.c.expires_at)

audit_logs = Table(
    "audit_logs", Base.metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("tenant_id", String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
    Column("actor_id", String(36), ForeignKey("users.id", ondelete="SET NULL")),
    Column("action", String(100), nullable=False),
    Column("resource_type", String(100), nullable=False),
    Column("resource_id", String(255)),
    Column("request_id", String(100)),
    Column("ip_address", String(64)),
    Column("user_agent", Text),
    Column("metadata", JSON_VALUE, nullable=False, server_default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
Index("ix_audit_logs_tenant_created", audit_logs.c.tenant_id, audit_logs.c.created_at)
Index("ix_audit_logs_resource", audit_logs.c.resource_type, audit_logs.c.resource_id)
