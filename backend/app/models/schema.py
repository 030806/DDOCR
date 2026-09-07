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

# Dataset publication is separate from individual OCR result review flags.
dataset_reviews = Table(
    "dataset_reviews", Base.metadata,
    Column("job_id", String(36), ForeignKey("ocr_jobs.id", ondelete="CASCADE"), primary_key=True),
    Column("reviewed_version", Integer, nullable=False),
    Column("reviewed_by", String(36), nullable=False),
    Column("reviewed_at", String(40), nullable=False),
    Column("snapshot", JSON_VALUE, nullable=False),
    Column("source_sha256", String(64), nullable=False),
    Column("image_revision", Integer, nullable=False, server_default="0"),
    Column("saved_version", Integer),
    Column("last_error", Text),
)

dataset_images = Table(
    "dataset_images", Base.metadata,
    Column("sequence", Integer, primary_key=True, autoincrement=True),
    Column("image_id", String(40), unique=True),
    Column("owner_id", String(36), nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("revision", Integer, nullable=False, server_default="0"),
    Column("job_id", String(36)),
    Column("saved_version", Integer),
    UniqueConstraint("owner_id", "sha256", name="uq_dataset_image_owner_hash"),
)


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
    Column("role_names", JSON_VALUE, nullable=False, server_default="[]"),
    Column("permissions", JSON_VALUE, nullable=False, server_default="[]"),
    Column("avatar_url", Text),
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

sessions = Table(
    "sessions", Base.metadata,
    Column("token", String(255), primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("expires_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
)
Index("ix_sessions_user_id", sessions.c.user_id)
Index("ix_sessions_expires_at", sessions.c.expires_at)

password_reset_tokens = Table(
    "password_reset_tokens", Base.metadata,
    id_column(),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("code_hash", String(255), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("attempt_count", Integer, nullable=False, server_default="0"),
    Column("used_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
Index("ix_password_reset_tokens_user_created", password_reset_tokens.c.user_id, password_reset_tokens.c.created_at)
Index("ix_password_reset_tokens_expires_at", password_reset_tokens.c.expires_at)

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

files = Table(
    "files", Base.metadata,
    id_column(),
    Column("tenant_id", String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("file_name", String(500), nullable=False),
    Column("declared_mime_type", String(255), nullable=False),
    Column("actual_mime_type", String(255)),
    Column("size_bytes", BigInteger, nullable=False),
    Column("sha256", String(64)),
    Column("object_key", Text, nullable=False),
    Column("page_count", Integer),
    Column("status", String(32), nullable=False, server_default="uploading"),
    Column("failure_reason", Text),
    Column("actual_size_bytes", BigInteger),
    Column("width_px", Integer),
    Column("height_px", Integer),
    Column("deleted_at", DateTime(timezone=True)),
    *timestamps(),
    CheckConstraint("size_bytes >= 0", name="ck_file_objects_size"),
)
Index("ix_files_tenant_user_created", files.c.tenant_id, files.c.user_id, files.c.created_at)

document_pages = Table(
    "document_pages", Base.metadata,
    id_column(),
    Column("file_id", String(36), ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
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
    Column("user_id", String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("file_id", String(36), ForeignKey("files.id", ondelete="RESTRICT"), nullable=False),
    Column("model_version_id", String(36), ForeignKey("model_versions.id", ondelete="RESTRICT")),
    Column("file_name", String(500), nullable=False),
    Column("model_id", String(100), nullable=False),
    Column("model_version", String(100), nullable=False),
    Column("page_ids", JSON_VALUE, nullable=False, server_default="[]"),
    Column("review_count", Integer, nullable=False, server_default="0"),
    Column("name", String(500), nullable=False),
    Column("options_snapshot", JSON_VALUE, nullable=False, server_default="{}"),
    Column("result_version", Integer, nullable=False, server_default="0"),
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
Index("ix_ocr_jobs_user_created", ocr_jobs.c.user_id, ocr_jobs.c.created_at)

ocr_region_job_scopes = Table(
    "ocr_region_job_scopes", Base.metadata,
    Column("job_id", String(36), ForeignKey("ocr_jobs.id", ondelete="CASCADE"), primary_key=True),
    Column("source_job_id", String(36), ForeignKey("ocr_jobs.id", ondelete="SET NULL")),
    Column("file_id", String(36), ForeignKey("files.id", ondelete="RESTRICT"), nullable=False),
    Column("region_count", Integer, nullable=False),
    Column("created_by", String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("region_count > 0", name="ck_region_job_scopes_count"),
)
Index("ix_region_job_scopes_source", ocr_region_job_scopes.c.source_job_id)

ocr_job_regions = Table(
    "ocr_job_regions", Base.metadata,
    id_column(),
    Column("job_id", String(36), ForeignKey("ocr_jobs.id", ondelete="CASCADE"), nullable=False),
    Column("page_no", Integer, nullable=False),
    Column("client_id", String(100), nullable=False),
    Column("bbox", JSON_VALUE, nullable=False),
    Column("reading_order", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("job_id", "client_id", name="uq_ocr_job_regions_client"),
    UniqueConstraint("job_id", "page_no", "reading_order", name="uq_ocr_job_regions_order"),
    CheckConstraint("page_no > 0", name="ck_ocr_job_regions_page_no"),
)
Index("ix_ocr_job_regions_job_page", ocr_job_regions.c.job_id, ocr_job_regions.c.page_no)

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

pages = Table(
    "pages", Base.metadata,
    id_column(),
    Column("job_id", String(36), ForeignKey("ocr_jobs.id", ondelete="CASCADE"), nullable=False),
    Column("page_no", Integer, nullable=False),
    Column("label", String(100), nullable=False),
    Column("status", String(32), nullable=False),
    Column("image", JSON_VALUE, nullable=False, server_default="{}"),
    Column("result_ids", JSON_VALUE, nullable=False, server_default="[]"),
    Column("result_count", Integer, nullable=False, server_default="0"),
    Column("review_count", Integer, nullable=False, server_default="0"),
    Column("processing_ms", Integer),
    Column("error", JSON_VALUE),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("job_id", "page_no", name="uq_pages_job_page_no"),
)
Index("ix_pages_job_page_no", pages.c.job_id, pages.c.page_no)

results = Table(
    "results", Base.metadata,
    id_column(),
    Column("job_page_id", String(36), ForeignKey("job_pages.id", ondelete="CASCADE")),
    Column("job_id", String(36), ForeignKey("ocr_jobs.id", ondelete="CASCADE"), nullable=False),
    Column("page_id", String(36), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False),
    Column("page_no", Integer, nullable=False),
    Column("type", String(32), nullable=False, server_default="text_line"),
    Column("text", Text, nullable=False),
    Column("confidence", Float, nullable=False),
    Column("bbox_x1", Float, nullable=False),
    Column("bbox_y1", Float, nullable=False),
    Column("bbox_x2", Float, nullable=False),
    Column("bbox_y2", Float, nullable=False),
    Column("polygon", JSON_VALUE),
    Column("bbox", JSON_VALUE, nullable=False),
    Column("angle", Float),
    Column("reading_order", Integer, nullable=False),
    Column("attributes", JSON_VALUE, nullable=False, server_default="{}"),
    Column("current_revision", Integer, nullable=False, server_default="0"),
    Column("current_correction", JSON_VALUE),
    Column("review_status", String(32), nullable=False, server_default="unreviewed"),
    Column("geometry_revision", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_ocr_results_confidence"),
    CheckConstraint("bbox_x2 >= bbox_x1 AND bbox_y2 >= bbox_y1", name="ck_ocr_results_bbox"),
    CheckConstraint("review_status IN ('unreviewed', 'confirmed', 'false_positive', 'deleted')", name="ck_results_review_status"),
)
Index("ix_results_page_order", results.c.page_id, results.c.reading_order)

result_geometry_revisions = Table(
    "result_geometry_revisions", Base.metadata,
    id_column(),
    Column("result_id", String(36), ForeignKey("results.id", ondelete="CASCADE"), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("base_revision", Integer, nullable=False),
    Column("previous_bbox", JSON_VALUE),
    Column("bbox", JSON_VALUE),
    Column("operation", String(32), nullable=False),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("result_id", "revision", name="uq_result_geometry_revision"),
)
Index("ix_result_geometry_result_created", result_geometry_revisions.c.result_id, result_geometry_revisions.c.created_at)

corrections = Table(
    "corrections", Base.metadata,
    id_column(),
    Column("result_id", String(36), ForeignKey("results.id", ondelete="CASCADE"), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("base_revision", Integer, nullable=False),
    Column("corrected_text", Text, nullable=False),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("reverts_correction_id", String(36), ForeignKey("corrections.id", ondelete="SET NULL")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("result_id", "revision", name="uq_ocr_corrections_result_revision"),
)
Index("ix_corrections_result_created", corrections.c.result_id, corrections.c.created_at)

comments = Table(
    "comments", Base.metadata,
    id_column(),
    Column("result_id", String(36), ForeignKey("results.id", ondelete="CASCADE"), nullable=False),
    Column("content", Text, nullable=False),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("deleted_at", DateTime(timezone=True)),
    *timestamps(),
)
Index("ix_comments_result_created", comments.c.result_id, comments.c.created_at)

exports = Table(
    "exports", Base.metadata,
    id_column(),
    Column("job_id", String(36), ForeignKey("ocr_jobs.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("format", String(20), nullable=False),
    Column("mode", String(32), nullable=False),
    Column("scope", String(32), nullable=False),
    Column("status", String(32), nullable=False, server_default="queued"),
    Column("object_key", Text),
    Column("expires_at", DateTime(timezone=True)),
    Column("error_code", String(100)),
    Column("error_message", Text),
    Column("finished_at", DateTime(timezone=True)),
    Column("download_url", Text),
    *timestamps(),
)
Index("ix_exports_job_created", exports.c.job_id, exports.c.created_at)

idempotency_records = Table(
    "idempotency_records", Base.metadata,
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
Index("ix_idempotency_records_expires_at", idempotency_records.c.expires_at)

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
