"""SQLAlchemy repositories for OCR pages and recognition results."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, delete, func, insert, select, update
from sqlalchemy.orm import Session

from app.models.schema import ocr_jobs, pages, result_geometry_revisions, results


def _page_dict(row: Any) -> dict[str, Any]:
    m = row._mapping
    return {
        "id": m["id"], "job_id": m["job_id"], "page_no": m["page_no"],
        "label": m["label"], "status": m["status"], "image": dict(m["image"]),
        "result_ids": list(m["result_ids"] or []), "result_count": m["result_count"],
        "review_count": m["review_count"], "processing_ms": m["processing_ms"],
        "error": m["error"],
    }


def _result_dict(row: Any) -> dict[str, Any]:
    m = row._mapping
    return {
        "id": m["id"], "job_id": m["job_id"], "page_id": m["page_id"],
        "page_no": m["page_no"], "reading_order": m["reading_order"],
        "type": m["type"], "text": m["text"], "confidence": m["confidence"],
        "bbox": list(m["bbox"]), "polygon": m["polygon"],
        "attributes": dict(m["attributes"] or {}),
        "review_status": m["review_status"],
        "geometry_revision": m["geometry_revision"],
        "terminal_number": m["terminal_number"],
        "manual_confirmed": m["manual_confirmed"],
        "table_note": m["table_note"],
        "table_revision": m["table_revision"],
        "revision": m["current_revision"], "current_correction": m["current_correction"],
    }


class PageRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, item: dict[str, Any]) -> dict[str, Any]:
        with Session(self.engine) as db, db.begin():
            db.execute(insert(pages).values(**item))
        return item

    def get(self, page_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            row = db.execute(select(pages).where(pages.c.id == page_id)).first()
            return _page_dict(row) if row else None

    def update_state(self, page_id: str, **values: Any) -> dict[str, Any]:
        permitted = {"status", "result_ids", "result_count", "review_count", "processing_ms", "error"}
        with Session(self.engine) as db, db.begin():
            db.execute(update(pages).where(pages.c.id == page_id).values(
                **{key: value for key, value in values.items() if key in permitted}
            ))
        item = self.get(page_id)
        if item is None:
            raise KeyError(f"OCR page not found: {page_id}")
        return item


class OCRResultRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, item: dict[str, Any]) -> dict[str, Any]:
        bbox = item["bbox"]
        with Session(self.engine) as db, db.begin():
            db.execute(insert(results).values(
                id=item["id"], job_id=item["job_id"], page_id=item["page_id"],
                page_no=item["page_no"], reading_order=item["reading_order"],
                type=item["type"], text=item["text"], confidence=item["confidence"],
                bbox=bbox, bbox_x1=bbox[0], bbox_y1=bbox[1],
                bbox_x2=bbox[2], bbox_y2=bbox[3], polygon=item.get("polygon"),
                current_revision=item["revision"], current_correction=item.get("current_correction"),
            ))
        return item

    def get(self, result_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            row = db.execute(select(results).where(results.c.id == result_id)).first()
            return _result_dict(row) if row else None

    def update_table_fields(self, result_id: str, base_revision: int, values: dict[str, Any]) -> dict[str, Any] | None:
        with Session(self.engine) as db, db.begin():
            updated = db.execute(
                update(results).where(results.c.id == result_id, results.c.table_revision == base_revision)
                .values(**values, table_revision=base_revision + 1)
            )
            if not updated.rowcount:
                return None
            job_id = db.execute(select(results.c.job_id).where(results.c.id == result_id)).scalar_one()
            db.execute(update(ocr_jobs).where(ocr_jobs.c.id == job_id).values(result_version=ocr_jobs.c.result_version + 1))
        return self.get(result_id)

    def update_revision(self, item: dict[str, Any]) -> None:
        with Session(self.engine) as db, db.begin():
            db.execute(update(ocr_jobs).where(ocr_jobs.c.id == item["job_id"]).values(result_version=ocr_jobs.c.result_version + 1))
            db.execute(update(results).where(results.c.id == item["id"]).values(
                current_revision=item["revision"],
                current_correction=item.get("current_correction"),
            ))

    def update_review_status(self, result_ids: list[str], review_status: str) -> int:
        with Session(self.engine) as db, db.begin():
            job_ids = select(results.c.job_id).where(results.c.id.in_(result_ids))
            db.execute(update(ocr_jobs).where(ocr_jobs.c.id.in_(job_ids)).values(result_version=ocr_jobs.c.result_version + 1))
            result = db.execute(
                update(results).where(results.c.id.in_(result_ids)).values(review_status=review_status)
            )
            return int(result.rowcount or 0)

    def apply_edits(
        self, *, page: dict[str, Any], updates: list[dict[str, Any]],
        creates: list[dict[str, Any]], deletes: list[dict[str, Any]], user_id: str,
    ) -> dict[str, Any]:
        updated_items: list[dict[str, Any]] = []
        created_items: list[dict[str, Any]] = []
        deleted_ids: list[str] = []
        with Session(self.engine) as db, db.begin():
            if updates or creates or deletes:
                db.execute(update(ocr_jobs).where(ocr_jobs.c.id == page["job_id"]).values(result_version=ocr_jobs.c.result_version + 1))
            for edit in updates:
                row = db.execute(select(results).where(results.c.id == edit["result_id"])).first()
                if not row or row._mapping["page_id"] != page["id"]:
                    raise KeyError(edit["result_id"])
                current_revision = int(row._mapping["geometry_revision"] or 0)
                if current_revision != edit["base_revision"]:
                    raise ValueError(edit["result_id"])
                bbox = list(edit["bbox"])
                revision = current_revision + 1
                db.execute(insert(result_geometry_revisions).values(
                    id=edit["revision_id"], result_id=edit["result_id"], revision=revision,
                    base_revision=current_revision, previous_bbox=list(row._mapping["bbox"]),
                    bbox=bbox, operation="updated", user_id=user_id,
                ))
                db.execute(update(results).where(results.c.id == edit["result_id"]).values(
                    bbox=bbox, bbox_x1=bbox[0], bbox_y1=bbox[1], bbox_x2=bbox[2], bbox_y2=bbox[3],
                    polygon=edit["polygon"],
                    geometry_revision=revision,
                ))
                updated_items.append({
                    "id": edit["result_id"], "bbox": bbox,
                    "polygon": edit["polygon"], "geometry_revision": revision,
                })

            max_order = db.scalar(select(func.max(results.c.reading_order)).where(results.c.page_id == page["id"])) or 0
            result_ids = list(page["result_ids"])
            for index, item in enumerate(creates, 1):
                bbox = list(item["bbox"])
                db.execute(insert(results).values(
                    id=item["id"], job_id=page["job_id"], page_id=page["id"], page_no=page["page_no"],
                    type="text_line", text=item["text"], confidence=1.0,
                    bbox=bbox, bbox_x1=bbox[0], bbox_y1=bbox[1], bbox_x2=bbox[2], bbox_y2=bbox[3],
                    polygon=item["polygon"],
                    reading_order=max_order + index, attributes={"source": "manual"},
                    current_revision=0, current_correction=None, review_status="unreviewed", geometry_revision=0,
                ))
                db.execute(insert(result_geometry_revisions).values(
                    id=item["revision_id"], result_id=item["id"], revision=0, base_revision=0,
                    previous_bbox=None, bbox=bbox, operation="created", user_id=user_id,
                ))
                result_ids.append(item["id"])
                created_items.append({
                    "client_id": item["client_id"], "id": item["id"],
                    "bbox": bbox, "polygon": item["polygon"],
                })

            for item in deletes:
                row = db.execute(select(results).where(results.c.id == item["result_id"])).first()
                if not row or row._mapping["page_id"] != page["id"]:
                    raise KeyError(item["result_id"])
                revision = int(row._mapping["geometry_revision"] or 0) + 1
                db.execute(insert(result_geometry_revisions).values(
                    id=item["revision_id"], result_id=item["result_id"], revision=revision,
                    base_revision=revision - 1, previous_bbox=list(row._mapping["bbox"]),
                    bbox=list(row._mapping["bbox"]), operation="deleted", user_id=user_id,
                ))
                db.execute(update(results).where(results.c.id == item["result_id"]).values(
                    review_status="deleted", geometry_revision=revision,
                ))
                deleted_ids.append(item["result_id"])
            db.execute(update(pages).where(pages.c.id == page["id"]).values(
                result_ids=result_ids, result_count=len(result_ids),
            ))
            job_result_count = db.scalar(select(func.count()).select_from(results).where(results.c.job_id == page["job_id"])) or 0
            db.execute(update(ocr_jobs).where(ocr_jobs.c.id == page["job_id"]).values(result_count=job_result_count))
        return {"updated": updated_items, "created": created_items, "deleted": deleted_ids}

    def replace_page_results(
        self,
        *,
        job_id: str,
        page_id: str,
        items: list[dict[str, Any]],
        status: str,
        review_count: int,
        processing_ms: int,
        page_error: dict[str, Any] | None,
        finished_at: Any,
    ) -> None:
        """Atomically replace results and finalize their page and job."""
        result_ids = [item["id"] for item in items]
        with Session(self.engine) as db, db.begin():
            db.execute(update(ocr_jobs).where(ocr_jobs.c.id == job_id).values(result_version=ocr_jobs.c.result_version + 1))
            db.execute(delete(results).where(results.c.page_id == page_id))
            for item in items:
                bbox = item["bbox"]
                db.execute(insert(results).values(
                    id=item["id"], job_id=job_id, page_id=page_id,
                    page_no=item["page_no"], reading_order=item["reading_order"],
                    type=item["type"], text=item["text"], confidence=item["confidence"],
                    bbox=bbox, bbox_x1=bbox[0], bbox_y1=bbox[1],
                    bbox_x2=bbox[2], bbox_y2=bbox[3], polygon=item.get("polygon"),
                    angle=item.get("angle"), attributes=item.get("attributes", {}),
                    current_revision=0, current_correction=None,
                ))
            db.execute(update(pages).where(pages.c.id == page_id).values(
                status=status, result_ids=result_ids, result_count=len(items),
                review_count=review_count, processing_ms=processing_ms, error=page_error,
            ))
            db.execute(update(ocr_jobs).where(ocr_jobs.c.id == job_id).values(
                status=status, stage="completed", progress=100,
                page_succeeded=1, page_failed=0, result_count=len(items),
                review_count=review_count,
                finished_at=(
                    datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                    if isinstance(finished_at, str) else finished_at
                ),
                updated_at=datetime.now(UTC),
            ))
