"""Single-process background executor for OCR jobs."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import TYPE_CHECKING

from app.ocr.errors import OcrError
from app.utils.common import now, uid

if TYPE_CHECKING:
    from app.services.core import MockOcrService


class OcrTaskWorker:
    """Run OCR outside request threads with one shared engine instance."""

    def __init__(self, service: MockOcrService) -> None:
        self._service = service
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ddocr-ocr")
        self._futures: dict[str, Future[None]] = {}
        self._lock = Lock()

    def submit(self, job_id: str) -> Future[None]:
        with self._lock:
            existing = self._futures.get(job_id)
            if existing is not None and not existing.done():
                return existing
            future = self._executor.submit(self.run, job_id)
            self._futures[job_id] = future
            future.add_done_callback(lambda _future: self._forget(job_id))
            return future

    def _forget(self, job_id: str) -> None:
        with self._lock:
            self._futures.pop(job_id, None)

    def run(self, job_id: str) -> None:
        service = self._service
        job = service.jobs.get(job_id)
        if job is None or job["status"] != "queued":
            return
        page_id = job["page_ids"][0]
        service.jobs.update_state(
            job_id, status="running", stage="running", progress=5,
            started_at=now(), error_code=None, error_message=None,
        )
        service.page_repository.update_state(page_id, status="running", error=None)
        try:
            service.jobs.update_state(
                job_id, status="running", stage="recognizing", progress=20,
            )
            uploaded_file = service.file(job["file_id"])
            result = service.ocr_adapter.recognize_file(
                service.content_path(uploaded_file), options=job.get("options", {}),
            )
            service.jobs.update_state(job_id, status="running", stage="persisting", progress=90)
            review_count = sum(1 for item in result.detections if item.review_required)
            status = "partial_success" if result.roi_errors else "succeeded"
            items = []
            for order, detection in enumerate(result.detections, 1):
                items.append({
                    "id": uid(), "job_id": job_id, "page_id": page_id,
                    "page_no": 1, "reading_order": order, "type": "text_line",
                    "text": detection.text, "confidence": detection.confidence,
                    "bbox": list(detection.bbox),
                    "polygon": [list(point) for point in detection.polygon],
                    "attributes": detection.attributes,
                })
            page_error = (
                {"code": "OCR_PARTIAL_FAILURE", "roi_errors": result.roi_errors}
                if result.roi_errors else None
            )
            service.result_repository.replace_page_results(
                job_id=job_id, page_id=page_id, items=items, status=status,
                review_count=review_count, processing_ms=result.processing_ms,
                page_error=page_error, finished_at=now(),
            )
        except Exception as exc:
            code = exc.code if isinstance(exc, OcrError) else "OCR_TASK_FAILED"
            message = f"{type(exc).__name__}: {exc}"
            service.page_repository.update_state(
                page_id, status="failed", processing_ms=0,
                error={"code": code, "message": message},
            )
            service.jobs.update_state(
                job_id, status="failed", stage="failed", progress=100,
                completed_pages=0, failed_pages=1, finished_at=now(),
                error_code=code, error_message=message,
            )

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=False)
