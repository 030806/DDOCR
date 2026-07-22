"""SQLAlchemy repositories for OCR corrections and comments."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, insert, select, update
from sqlalchemy.orm import Session

from app.models.schema import comments, corrections, users


def _api_time(value: datetime | str | None) -> str | None:
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _correction_dict(row: Any) -> dict[str, Any]:
    m = row._mapping
    return {
        "id": m["id"], "result_id": m["result_id"],
        "corrected_text": m["corrected_text"], "revision": m["revision"],
        "created_by": {"id": m["user_id"], "name": m["author_name"]},
        "created_at": _api_time(m["created_at"]),
    }


def _comment_dict(row: Any) -> dict[str, Any]:
    m = row._mapping
    return {
        "id": m["id"], "result_id": m["result_id"], "content": m["content"],
        "author": {"id": m["user_id"], "name": m["author_name"]},
        "created_at": _api_time(m["created_at"]),
        "updated_at": _api_time(m["updated_at"]),
        "deleted": m["deleted_at"] is not None,
    }


class CorrectionRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _query() -> Any:
        return select(
            corrections,
            users.c.name.label("author_name"),
        ).join(users, users.c.id == corrections.c.user_id)

    def create(self, item: dict[str, Any], user_id: str, base_revision: int) -> dict[str, Any]:
        with Session(self.engine) as db, db.begin():
            db.execute(insert(corrections).values(
                id=item["id"], result_id=item["result_id"], revision=item["revision"],
                base_revision=base_revision, corrected_text=item["corrected_text"],
                user_id=user_id, created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
            ))
        return item

    def list_for_result(self, result_id: str) -> list[dict[str, Any]]:
        with Session(self.engine) as db:
            rows = db.execute(
                self._query().where(corrections.c.result_id == result_id)
                .order_by(corrections.c.revision)
            ).all()
            return [_correction_dict(row) for row in rows]


class CommentRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _query() -> Any:
        return select(
            comments,
            users.c.name.label("author_name"),
        ).join(users, users.c.id == comments.c.user_id)

    def create(self, item: dict[str, Any], user_id: str) -> dict[str, Any]:
        created_at = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        with Session(self.engine) as db, db.begin():
            db.execute(insert(comments).values(
                id=item["id"], result_id=item["result_id"], content=item["content"],
                user_id=user_id, created_at=created_at, updated_at=created_at,
            ))
        return item

    def get(self, comment_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            row = db.execute(self._query().where(comments.c.id == comment_id)).first()
            return _comment_dict(row) if row else None

    def list_for_result(self, result_id: str) -> list[dict[str, Any]]:
        with Session(self.engine) as db:
            rows = db.execute(
                self._query().where(
                    comments.c.result_id == result_id,
                    comments.c.deleted_at.is_(None),
                ).order_by(comments.c.created_at)
            ).all()
            return [_comment_dict(row) for row in rows]

    def update(self, comment_id: str, content: str) -> dict[str, Any] | None:
        with Session(self.engine) as db, db.begin():
            db.execute(update(comments).where(comments.c.id == comment_id).values(
                content=content, updated_at=datetime.now(UTC),
            ))
        return self.get(comment_id)

    def delete(self, comment_id: str) -> None:
        with Session(self.engine) as db, db.begin():
            db.execute(update(comments).where(comments.c.id == comment_id).values(
                deleted_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            ))
