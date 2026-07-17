from typing import Any

from fastapi import HTTPException
from openpyxl import Workbook

from app.models.store import Store
from app.schemas.contracts import (
    CorrectionCreate,
    ExportCreate,
    JobCreate,
    UploadSessionCreate,
)
from app.utils.common import now, uid

USER = {"id": "mock-user", "name": "林工"}
MAX_FILE_SIZE_BYTES = 104_857_600


class MockOcrService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def create_upload(
        self,
        body: UploadSessionCreate,
        base_url: str,
    ) -> dict[str, Any]:
        file_id = uid()
        item = {
            "id": file_id,
            "file_name": body.file_name,
            "size_bytes": body.size_bytes,
            "media_type": body.media_type,
            "sha256": body.sha256,
            "status": "uploading",
            "page_count": None,
            "failure_reason": None,
            "created_at": now(),
            "deleted": False,
        }
        self.store.put("file", file_id, item)
        return {
            "file_id": file_id,
            "upload_url": f"{base_url}api/v1/files/{file_id}/content",
            "upload_headers": {"content-type": body.media_type},
            "expires_at": now(),
            "max_size_bytes": MAX_FILE_SIZE_BYTES,
        }

    def file(self, file_id: str) -> dict[str, Any]:
        item = self.store.get("file", file_id)
        if not item or item.get("deleted"):
            raise HTTPException(404, "File not found")
        return item

    def save_content(
        self,
        file_id: str,
        content: bytes,
    ) -> dict[str, Any]:
        item = self.file(file_id)
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(413, "File too large")

        upload_path = self.store.uploads / file_id
        upload_path.write_bytes(content)
        item["actual_size_bytes"] = len(content)
        item["status"] = "validating"
        self.store.put("file", file_id, item)
        return item

    def complete(self, file_id: str) -> dict[str, Any]:
        item = self.file(file_id)
        upload_path = self.store.uploads / file_id
        if not upload_path.exists():
            raise HTTPException(422, "Upload content is missing")

        item.update(
            status="ready",
            page_count=1,
            actual_media_type=item["media_type"],
            failure_reason=None,
        )
        return self.store.put("file", file_id, item)

    def create_job(self, body: JobCreate) -> dict[str, Any]:
        uploaded_file = self.file(body.file_id)
        if uploaded_file["status"] != "ready":
            raise HTTPException(409, "File is not ready")

        is_mock_model = (
            body.model_id == "mock" and body.model_version == "1.0.0"
        )
        if not is_mock_model:
            raise HTTPException(422, "Unknown model version")

        job_id = uid()
        page_id = uid()
        created_at = now()
        mock_results = [
            ("XT-101", 0.98, [180, 240, 520, 320]),
            ("QF10I", 0.884, [620, 240, 940, 320]),
            ("24V DC", 0.96, [180, 410, 520, 490]),
        ]
        result_ids = self._create_mock_results(
            job_id,
            page_id,
            mock_results,
        )
        page = self._build_page(job_id, page_id, result_ids)
        self.store.put("page", page_id, page)

        job = {
            "id": job_id,
            "name": body.name,
            "file_id": body.file_id,
            "file_name": uploaded_file["file_name"],
            "model_id": body.model_id,
            "model_version": body.model_version,
            "status": "succeeded",
            "stage": "completed",
            "progress": 100,
            "created_at": created_at,
            "started_at": created_at,
            "finished_at": now(),
            "page_ids": [page_id],
            "page_count": 1,
            "completed_pages": 1,
            "failed_pages": 0,
            "result_count": len(mock_results),
            "review_count": 1,
            "deleted": False,
        }
        self.store.put("job", job_id, job)
        response_fields = ("id", "status", "stage", "progress", "created_at")
        return {field: job[field] for field in response_fields}

    def _create_mock_results(
        self,
        job_id: str,
        page_id: str,
        mock_results: list[tuple[str, float, list[int]]],
    ) -> list[str]:
        result_ids = []
        for reading_order, mock_result in enumerate(mock_results, 1):
            text, confidence, bbox = mock_result
            result_id = uid()
            result_ids.append(result_id)
            polygon = [
                [bbox[0], bbox[1]],
                [bbox[2], bbox[1]],
                [bbox[2], bbox[3]],
                [bbox[0], bbox[3]],
            ]
            result = {
                "id": result_id,
                "job_id": job_id,
                "page_id": page_id,
                "page_no": 1,
                "reading_order": reading_order,
                "type": "text_line",
                "text": text,
                "confidence": confidence,
                "bbox": bbox,
                "polygon": polygon,
                "revision": 0,
                "current_correction": None,
            }
            self.store.put("result", result_id, result)
        return result_ids

    @staticmethod
    def _build_page(
        job_id: str,
        page_id: str,
        result_ids: list[str],
    ) -> dict[str, Any]:
        return {
            "id": page_id,
            "job_id": job_id,
            "page_no": 1,
            "label": "第 1 页",
            "status": "succeeded",
            "image": {
                "url": None,
                "thumbnail_url": None,
                "width_px": 1200,
                "height_px": 1600,
                "rotation": 0,
                "render_dpi": 300,
            },
            "result_ids": result_ids,
            "result_count": len(result_ids),
            "review_count": 1,
            "processing_ms": 20,
            "error": None,
        }

    def job(self, job_id: str) -> dict[str, Any]:
        job = self.store.get("job", job_id)
        if not job or job.get("deleted"):
            raise HTTPException(404, "Job not found")
        return job

    def pages(self, job_id: str) -> list[dict[str, Any]]:
        job = self.job(job_id)
        pages = [
            self.store.get("page", page_id) for page_id in job["page_ids"]
        ]
        return [self._public_page(page) for page in pages if page is not None]

    @staticmethod
    def _public_page(page: dict[str, Any]) -> dict[str, Any]:
        excluded_fields = {"result_ids", "job_id"}
        return {
            key: value
            for key, value in page.items()
            if key not in excluded_fields
        }

    def result(self, result_id: str) -> dict[str, Any]:
        result = self.store.get("result", result_id)
        if not result:
            raise HTTPException(404, "OCR result not found")
        return result

    def comments(self, result_id: str) -> list[dict[str, Any]]:
        all_comments = self.store.all("comment")
        comments = [
            comment
            for comment in all_comments
            if comment["result_id"] == result_id and not comment.get("deleted")
        ]
        return sorted(comments, key=lambda comment: comment["created_at"])

    def public_result(self, result: dict[str, Any]) -> dict[str, Any]:
        correction = result.get("current_correction")
        comments = self.comments(result["id"])
        excluded_fields = {"job_id", "page_id", "page_no"}
        public_fields = {
            key: value
            for key, value in result.items()
            if key not in excluded_fields
        }
        display_text = (
            correction["corrected_text"] if correction else result["text"]
        )
        return {
            **public_fields,
            "display_text": display_text,
            "is_corrected": bool(correction),
            "current_correction": correction,
            "comment_count": len(comments),
            "comments": comments,
        }

    def add_correction(
        self,
        result_id: str,
        body: CorrectionCreate,
    ) -> dict[str, Any]:
        result = self.result(result_id)
        if result["revision"] != body.base_revision:
            public_result = self.public_result(result)
            conflict_details = {
                "code": "CORRECTION_REVISION_CONFLICT",
                "current_revision": result["revision"],
                "current_display_text": public_result["display_text"],
            }
            raise HTTPException(409, detail=conflict_details)

        correction = {
            "id": uid(),
            "result_id": result_id,
            "corrected_text": body.corrected_text,
            "revision": result["revision"] + 1,
            "created_by": USER,
            "created_at": now(),
        }
        self.store.put("correction", correction["id"], correction)
        result["revision"] = correction["revision"]
        result["current_correction"] = correction
        self.store.put("result", result_id, result)
        return correction

    def add_comment(self, result_id: str, content: str) -> dict[str, Any]:
        self.result(result_id)
        comment = {
            "id": uid(),
            "result_id": result_id,
            "content": content,
            "author": USER,
            "created_at": now(),
            "updated_at": None,
            "deleted": False,
        }
        self.store.put("comment", comment["id"], comment)
        comment_count = len(self.comments(result_id))
        return {**comment, "comment_count": comment_count}

    def export(
        self,
        job_id: str,
        body: ExportCreate,
        base_url: str,
    ) -> dict[str, Any]:
        job = self.job(job_id)
        export_id = uid()
        export_path = self.store.exports / f"{export_id}.xlsx"
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "OCR Results"
        worksheet.append(
            [
                "page_no",
                "reading_order",
                "original_text",
                "display_text",
                "confidence",
                "bbox",
                "comments",
            ]
        )
        self._append_export_rows(worksheet, job)
        workbook.save(export_path)

        export = {
            "id": export_id,
            "job_id": job_id,
            "format": body.format,
            "mode": body.mode,
            "scope": body.scope,
            "status": "succeeded",
            "created_at": now(),
            "completed_at": now(),
            "download_url": (
                f"{base_url}api/v1/ocr/jobs/{job_id}/exports/"
                f"{export_id}/download"
            ),
        }
        self.store.put("export", export_id, export)
        return export

    def _append_export_rows(
        self,
        worksheet: Any,
        job: dict[str, Any],
    ) -> None:
        for page_id in job["page_ids"]:
            page = self.store.get("page", page_id)
            if page is None:
                continue
            for result_id in page["result_ids"]:
                result = self.public_result(self.result(result_id))
                comments = " | ".join(
                    comment["content"] for comment in result["comments"]
                )
                row = [
                    page["page_no"],
                    result["reading_order"],
                    result["text"],
                    result["display_text"],
                    result["confidence"],
                    str(result["bbox"]),
                    comments,
                ]
                worksheet.append(row)
