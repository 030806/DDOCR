"""SQLAlchemy repositories for exports and idempotent API responses."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, insert, select
from sqlalchemy.orm import Session

from app.models.schema import exports, idempotency_records


def _db_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _api_time(value: datetime | str | None) -> str | None:
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _export_dict(row: Any) -> dict[str, Any]:
    m = row._mapping
    return {
        "id": m["id"], "job_id": m["job_id"], "format": m["format"],
        "mode": m["mode"], "scope": m["scope"], "status": m["status"],
        "created_at": _api_time(m["created_at"]),
        "completed_at": _api_time(m["finished_at"]),
        "download_url": m["download_url"],
    }


class ExportRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, item: dict[str, Any], user_id: str) -> dict[str, Any]:
        with Session(self.engine) as db, db.begin():
            db.execute(insert(exports).values(
                id=item["id"], job_id=item["job_id"], user_id=user_id,
                format=item["format"], mode=item["mode"], scope=item["scope"],
                status=item["status"], object_key=f"exports/{item['id']}.xlsx",
                created_at=_db_time(item["created_at"]),
                updated_at=_db_time(item["completed_at"]),
                finished_at=_db_time(item["completed_at"]),
                download_url=item["download_url"],
            ))
        return item

    def get(self, export_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            row = db.execute(select(exports).where(exports.c.id == export_id)).first()
            return _export_dict(row) if row else None


class IdempotencyRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get(self, user_id: str, route: str, key: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            return db.scalar(select(idempotency_records.c.response_body).where(
                idempotency_records.c.user_id == user_id,
                idempotency_records.c.route == route,
                idempotency_records.c.key == key,
                idempotency_records.c.expires_at > datetime.now(UTC),
            ))

    def create(
        self,
        user_id: str,
        route: str,
        key: str,
        request_payload: str,
        response_body: dict[str, Any],
    ) -> None:
        with Session(self.engine) as db, db.begin():
            db.execute(insert(idempotency_records).values(
                id=str(uuid4()), user_id=user_id, route=route, key=key,
                request_hash=sha256(request_payload.encode()).hexdigest(),
                response_status=201, response_body=response_body,
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            ))
