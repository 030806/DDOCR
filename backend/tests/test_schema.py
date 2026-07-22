from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models import schema
from app.models.store import Base


def test_documented_core_tables_are_registered() -> None:
    expected = {
        "tenants", "users", "sessions", "user_preferences", "models", "model_versions",
        "files", "document_pages", "ocr_jobs", "job_pages", "pages",
        "results", "corrections", "comments", "exports",
        "idempotency_records", "audit_logs",
    }
    assert expected <= set(Base.metadata.tables)


def test_ocr_result_bbox_and_revision_constraints() -> None:
    result_checks = {
        constraint.name
        for constraint in schema.results.constraints
        if isinstance(constraint, CheckConstraint)
    }
    correction_uniques = {
        constraint.name
        for constraint in schema.corrections.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "ck_ocr_results_bbox" in result_checks
    assert "ck_ocr_results_confidence" in result_checks
    assert "uq_ocr_corrections_result_revision" in correction_uniques
