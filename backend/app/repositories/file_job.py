"""SQLAlchemy repositories for files and OCR jobs."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, insert, select, update
from sqlalchemy.orm import Session

from app.models.schema import files, ocr_jobs, users


def _db_time(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _api_time(value: datetime | str | None) -> str | None:
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _file_dict(row: Any) -> dict[str, Any]:
    m = row._mapping
    item = {
        "id": m["id"], "owner_id": m["user_id"], "file_name": m["file_name"],
        "size_bytes": m["size_bytes"], "media_type": m["declared_mime_type"],
        "sha256": m["sha256"], "status": m["status"], "page_count": m["page_count"],
        "failure_reason": m["failure_reason"], "storage_path": m["object_key"],
        "created_at": _api_time(m["created_at"]), "deleted": m["deleted_at"] is not None,
    }
    optional = {
        "actual_media_type": m["actual_mime_type"], "actual_size_bytes": m["actual_size_bytes"],
        "width_px": m["width_px"], "height_px": m["height_px"],
    }
    item.update({key: value for key, value in optional.items() if value is not None})
    return item


def _job_dict(row: Any) -> dict[str, Any]:
    m = row._mapping
    return {
        "id": m["id"], "owner_id": m["user_id"], "name": m["name"],
        "file_id": m["file_id"], "file_name": m["file_name"],
        "model_id": m["model_id"], "model_version": m["model_version"],
        "options": dict(m["options_snapshot"] or {}),
        "status": m["status"], "stage": m["stage"], "progress": m["progress"],
        "created_at": _api_time(m["created_at"]), "started_at": _api_time(m["started_at"]),
        "finished_at": _api_time(m["finished_at"]), "page_ids": m["page_ids"] or [],
        "page_count": m["page_total"], "completed_pages": m["page_succeeded"],
        "failed_pages": m["page_failed"], "result_count": m["result_count"],
        "review_count": m["review_count"], "deleted": m["deleted_at"] is not None,
    }


class FileRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, item: dict[str, Any]) -> dict[str, Any]:
        with Session(self.engine) as db, db.begin():
            tenant_id = db.scalar(select(users.c.tenant_id).where(users.c.id == item["owner_id"]))
            db.execute(insert(files).values(
                id=item["id"], tenant_id=tenant_id, user_id=item["owner_id"],
                file_name=item["file_name"], declared_mime_type=item["media_type"],
                size_bytes=item["size_bytes"], sha256=item.get("sha256"),
                object_key=item["storage_path"], status=item["status"],
                page_count=item.get("page_count"), failure_reason=item.get("failure_reason"),
                created_at=_db_time(item["created_at"]),
            ))
        return item

    def get(self, file_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            row = db.execute(select(files).where(files.c.id == file_id)).first()
            return _file_dict(row) if row else None

    def update(self, item: dict[str, Any]) -> dict[str, Any]:
        values = {
            "status": item["status"], "page_count": item.get("page_count"),
            "failure_reason": item.get("failure_reason"),
            "actual_mime_type": item.get("actual_media_type"),
            "actual_size_bytes": item.get("actual_size_bytes"),
            "width_px": item.get("width_px"), "height_px": item.get("height_px"),
            "deleted_at": datetime.now(UTC) if item.get("deleted") else None,
            "updated_at": datetime.now(UTC),
        }
        with Session(self.engine) as db, db.begin():
            db.execute(update(files).where(files.c.id == item["id"]).values(**values))
        return item


class OCRJobRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, item: dict[str, Any]) -> dict[str, Any]:
        with Session(self.engine) as db, db.begin():
            tenant_id = db.scalar(select(users.c.tenant_id).where(users.c.id == item["owner_id"]))
            db.execute(insert(ocr_jobs).values(
                id=item["id"], tenant_id=tenant_id, user_id=item["owner_id"],
                file_id=item["file_id"], file_name=item["file_name"], name=item["name"],
                model_id=item["model_id"], model_version=item["model_version"],
                options_snapshot=item.get("options", {}),
                page_ids=item["page_ids"], status=item["status"], stage=item["stage"],
                progress=item["progress"], page_total=item["page_count"],
                page_succeeded=item["completed_pages"], page_failed=item["failed_pages"],
                result_count=item["result_count"], review_count=item["review_count"],
                created_at=_db_time(item["created_at"]), started_at=_db_time(item["started_at"]),
                finished_at=_db_time(item["finished_at"]),
            ))
        return item

    def get(self, job_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            row = db.execute(select(ocr_jobs).where(ocr_jobs.c.id == job_id)).first()
            return _job_dict(row) if row else None

    def all(self) -> list[dict[str, Any]]:
        with Session(self.engine) as db:
            return [_job_dict(row) for row in db.execute(select(ocr_jobs)).all()]

    def update_state(self, job_id: str, **values: Any) -> dict[str, Any]:
        mapping = {
            "completed_pages": "page_succeeded", "failed_pages": "page_failed",
        }
        permitted = {
            "status", "stage", "progress", "started_at", "finished_at",
            "result_count", "review_count", "completed_pages", "failed_pages",
            "error_code", "error_message",
        }
        update_values = {
            mapping.get(key, key): _db_time(value) if key in {"started_at", "finished_at"} else value
            for key, value in values.items() if key in permitted
        }
        update_values["updated_at"] = datetime.now(UTC)
        with Session(self.engine) as db, db.begin():
            db.execute(update(ocr_jobs).where(ocr_jobs.c.id == job_id).values(**update_values))
        item = self.get(job_id)
        if item is None:
            raise KeyError(f"OCR job not found: {job_id}")
        return item
