"""Single-process background executor for OCR jobs."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import TYPE_CHECKING

from PIL import Image

from app.ocr.errors import OcrError
from app.ocr.contracts import OcrRegion
from app.utils.common import now, uid

if TYPE_CHECKING:
    from app.services.core import MockOcrService


class OcrTaskWorker:
    """Run OCR outside request threads with one shared engine instance."""

    def __init__(self, service: MockOcrService) -> None:
        self._service = service
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ddocr-ocr")
        self._terminal_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ddocr-yolox")
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
        terminal_future = None
        terminal_result: dict = {}
        try:
            service.jobs.update_state(
                job_id, status="running", stage="recognizing", progress=20,
            )
            uploaded_file = service.file(job["file_id"])
            source_path = service.content_path(uploaded_file)
            is_image = (uploaded_file.get("actual_media_type") or uploaded_file.get("media_type") or "").startswith("image/")
            if is_image:
                if service.terminal_detector is not None:
                    terminal_future = self._terminal_executor.submit(
                        service.terminal_detector.detect,
                        source_path,
                        int(uploaded_file.get("width_px") or 1200),
                        int(uploaded_file.get("height_px") or 1600),
                    )
                else:
                    terminal_result["terminal_error"] = {
                        "code": "YOLOX_NOT_CONFIGURED", "message": "端子检测服务未配置",
                    }
            region_context = service.region_jobs.context(job_id)
            ocr_error = None
            try:
                if region_context:
                    regions = [
                        OcrRegion(roi_id=item["id"], bbox=tuple(item["bbox"]))
                        for item in region_context["regions"]
                    ]
                    with Image.open(source_path) as opened_image:
                        opened_image.load()
                        result = service.ocr_adapter.recognize_image(
                            opened_image.convert("RGB"), regions=regions,
                        )
                else:
                    result = service.ocr_adapter.recognize_file(
                        source_path, options=job.get("options", {}),
                    )
            except Exception as exc:
                ocr_error = {
                    "code": exc.code if isinstance(exc, OcrError) else "OCR_TASK_FAILED",
                    "message": f"{type(exc).__name__}: {exc}",
                }
                result = None
            if terminal_future is not None:
                try:
                    points = terminal_future.result()
                    terminal_result = {
                        "terminal_model_points": points,
                        "terminal_points": points,
                        "terminal_error": None,
                    }
                except Exception as exc:
                    terminal_result = {
                        "terminal_error": {
                            "code": "YOLOX_INFERENCE_FAILED",
                            "message": f"{type(exc).__name__}: {exc}",
                        },
                    }
            if result is None and terminal_result.get("terminal_points") is None:
                raise RuntimeError(ocr_error["message"] if ocr_error else "Both models failed")
            service.jobs.update_state(job_id, status="running", stage="persisting", progress=90)
            review_count = sum(1 for item in result.detections if item.review_required) if result else 0
            status = "partial_success" if (
                ocr_error or (result and result.roi_errors)
                or (terminal_future is not None and terminal_result.get("terminal_error"))
            ) else "succeeded"
            detections = (
                sorted(
                    result.detections,
                    key=lambda item: (
                        item.bbox[1], item.bbox[0], item.bbox[3], item.bbox[2],
                    ),
                )
                if region_context else result.detections
            ) if result else []
            items = []
            for order, detection in enumerate(detections, 1):
                attributes = dict(detection.attributes)
                if region_context:
                    attributes.update({
                        "source": "region_ocr",
                        "source_job_id": region_context.get("source_job_id"),
                    })
                items.append({
                    "id": uid(), "job_id": job_id, "page_id": page_id,
                    "page_no": 1, "reading_order": order, "type": "text_line",
                    "text": detection.text, "confidence": detection.confidence,
                    "bbox": list(detection.bbox),
                    "polygon": [list(point) for point in detection.polygon],
                    "attributes": attributes,
                })
            page_error = ocr_error or (
                {"code": "OCR_PARTIAL_FAILURE", "roi_errors": result.roi_errors}
                if result and result.roi_errors else None
            )
            service.result_repository.replace_page_results(
                job_id=job_id, page_id=page_id, items=items, status=status,
                review_count=review_count, processing_ms=result.processing_ms if result else 0,
                page_error=page_error, finished_at=now(), terminal_result=terminal_result,
            )
            if result is not None:
                service.hide_rerun_source(job_id)
        except Exception as exc:
            code = exc.code if isinstance(exc, OcrError) else "OCR_TASK_FAILED"
            message = f"{type(exc).__name__}: {exc}"
            service.page_repository.update_state(
                page_id, status="failed", processing_ms=0,
                error={"code": code, "message": message},
                **terminal_result,
            )
            service.jobs.update_state(
                job_id, status="failed", stage="failed", progress=100,
                completed_pages=0, failed_pages=1, finished_at=now(),
                error_code=code, error_message=message,
            )

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=False)
        self._terminal_executor.shutdown(wait=wait, cancel_futures=False)
