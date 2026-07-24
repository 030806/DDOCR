"""SQLAlchemy repositories for OCR pages and recognition results."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, delete, insert, select, update
from sqlalchemy.orm import Session

from app.models.schema import ocr_jobs, pages, results


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

    def update_revision(self, item: dict[str, Any]) -> None:
        with Session(self.engine) as db, db.begin():
            db.execute(update(results).where(results.c.id == item["id"]).values(
                current_revision=item["revision"],
                current_correction=item.get("current_correction"),
            ))

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
