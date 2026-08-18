import hashlib
import hmac
import math
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException
from openpyxl import Workbook
from PIL import Image, UnidentifiedImageError

from app.models.store import Store
from app.ocr.adapter import OcrAdapter
from app.ocr.contracts import OcrAdapterProtocol
from app.ocr.engine import TerminalOcrEngine
from app.repositories.auth import PasswordResetRepository, SessionRepository, TenantRepository, UserRepository
from app.repositories.correction_comment import CommentRepository, CorrectionRepository
from app.repositories.file_job import FileRepository, OCRJobRepository
from app.repositories.export_idempotency import ExportRepository, IdempotencyRepository
from app.repositories.page_result import OCRResultRepository, PageRepository
from app.repositories.region_job import RegionJobRepository
from app.schemas.contracts import (
    CorrectionCreate,
    ExportCreate,
    JobCreate,
    RegionJobCreate,
    UploadSessionCreate,
)
from app.utils.common import now, uid

MAX_FILE_SIZE_BYTES = 209_715_200


class MockOcrService:
    def __init__(
        self,
        store: Store,
        ocr_adapter: OcrAdapterProtocol | None = None,
        job_submitter: Callable[[str], object] | None = None,
    ) -> None:
        self.store = store
        self.ocr_adapter: OcrAdapterProtocol = (
            ocr_adapter
            if ocr_adapter is not None
            else OcrAdapter(TerminalOcrEngine())
        )
        self.job_submitter = job_submitter
        self.tenants = TenantRepository(store.engine)
        self.users = UserRepository(store.engine)
        self.sessions = SessionRepository(store.engine)
        self.password_resets = PasswordResetRepository(store.engine)
        self.files = FileRepository(store.engine)
        self.jobs = OCRJobRepository(store.engine)
        self.page_repository = PageRepository(store.engine)
        self.result_repository = OCRResultRepository(store.engine)
        self.region_jobs = RegionJobRepository(store.engine)
        self.correction_repository = CorrectionRepository(store.engine)
        self.comment_repository = CommentRepository(store.engine)
        self.export_repository = ExportRepository(store.engine)
        self.idempotency_repository = IdempotencyRepository(store.engine)

    @staticmethod
    def _password_hash(password: str, salt_hex: str | None = None) -> tuple[str, str]:
        salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
        return salt.hex(), digest.hex()

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < 8 or not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
            raise HTTPException(422, "Password must contain letters and numbers")

    @classmethod
    def _password_matches(cls, password: str, user: dict[str, Any]) -> bool:
        _, candidate = cls._password_hash(password, user["password_salt"])
        return hmac.compare_digest(candidate, user["password_hash"])

    @staticmethod
    def public_user(user: dict[str, Any]) -> dict[str, Any]:
        phone = user.get("phone", "")
        phone_masked = (
            f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else phone
        )
        excluded = {"password_hash", "password_salt", "phone", "deleted"}
        return {
            **{key: value for key, value in user.items() if key not in excluded},
            "phone_masked": phone_masked,
        }

    def register_user(self, values: dict[str, Any]) -> dict[str, Any]:
        self._validate_password(values["password"])
        email = (values.get("email") or "").strip().lower()
        phone = values["phone"].strip()
        if email and self.users.find_by_email(email):
            raise HTTPException(409, "Email is already registered")
        if self.users.find_by_phone(phone):
            raise HTTPException(409, "Phone is already registered")
        if self.users.find_by_employee_no(values["employee_no"]):
            raise HTTPException(409, "Employee number is already registered")
        salt, password_hash = self._password_hash(values.pop("password"))
        user_id = uid()
        user = {
            "id": user_id,
            **values,
            "email": email,
            "phone": phone,
            "password_salt": salt,
            "password_hash": password_hash,
            "role_names": ["质量检测工程师"],
            "permissions": ["ocr:read", "ocr:create", "profile:update"],
            "avatar_url": None,
            "created_at": now(),
            "last_login_at": None,
            "deleted": False,
        }
        tenant_id = self.tenants.ensure_default()
        self.users.create(tenant_id, user)
        return self.create_session(user)

    def login_user(self, phone: str, password: str) -> dict[str, Any]:
        normalized = phone.strip()
        user = self.users.find_by_phone(normalized)
        if not user or not self._password_matches(password, user):
            raise HTTPException(401, "Invalid phone or password")
        return self.create_session(user)

    def create_session(self, user: dict[str, Any]) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        user["last_login_at"] = now()
        self.users.update(user["id"], {"last_login_at": user["last_login_at"]})
        self.sessions.create(token, user["id"], now())
        return {"access_token": token, "token_type": "bearer", "user": self.public_user(user)}

    def session_user(self, token: str) -> dict[str, Any]:
        user_id = self.sessions.user_id_for_active_token(token)
        if not user_id:
            raise HTTPException(401, "Invalid or expired session")
        user = self.users.get(user_id)
        if not user or user.get("deleted"):
            raise HTTPException(401, "User not found")
        return user

    def revoke_session(self, token: str) -> None:
        self.sessions.revoke(token)

    def update_user(self, user: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        user.update({key: value for key, value in values.items() if value is not None})
        user["updated_at"] = now()
        self.users.update(user["id"], values)
        return self.public_user(user)

    def change_password(self, user: dict[str, Any], current: str, new: str) -> None:
        if not self._password_matches(current, user):
            raise HTTPException(409, "Current password is incorrect")
        self._validate_password(new)
        salt, password_hash = self._password_hash(new)
        user["password_salt"] = salt
        user["password_hash"] = password_hash
        user["updated_at"] = now()
        self.users.update(user["id"], {
            "password_salt": salt,
            "password_hash": password_hash,
        })

    @staticmethod
    def _reset_code_hash(code: str, salt_hex: str | None = None) -> str:
        salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", code.encode(), salt, 120_000)
        return f"{salt.hex()}${digest.hex()}"

    def request_password_reset(self, phone: str, employee_no: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "message": "如果账号信息匹配，重置验证码已生成",
            "expires_in": 600,
        }
        user = self.users.find_by_phone(phone.strip())
        if not user or user.get("deleted") or user.get("employee_no") != employee_no.strip():
            return result
        code = f"{secrets.randbelow(1_000_000):06d}"
        self.password_resets.create(
            uid(), user["id"], self._reset_code_hash(code), datetime.now(UTC) + timedelta(minutes=10),
        )
        if os.getenv("DDOCR_EXPOSE_PASSWORD_RESET_CODE", "false").lower() in {"1", "true", "yes"}:
            result["development_code"] = code
        return result

    def reset_password(self, phone: str, code: str, new_password: str) -> None:
        user = self.users.find_by_phone(phone.strip())
        token = self.password_resets.latest_active(user["id"]) if user and not user.get("deleted") else None
        invalid = HTTPException(400, "验证码无效或已过期")
        if not user or not token or token["attempt_count"] >= 5:
            raise invalid
        expires_at = token["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        salt_hex, expected = token["code_hash"].split("$", 1)
        actual = self._reset_code_hash(code, salt_hex).split("$", 1)[1]
        if expires_at <= datetime.now(UTC) or not hmac.compare_digest(actual, expected):
            self.password_resets.increment_attempts(token["id"])
            raise invalid
        self._validate_password(new_password)
        salt, password_hash = self._password_hash(new_password)
        self.users.update(user["id"], {"password_salt": salt, "password_hash": password_hash})
        self.password_resets.mark_used(token["id"])
        self.sessions.revoke_all_for_user(user["id"])

    def create_upload(
        self,
        body: UploadSessionCreate,
        base_url: str,
        owner_id: str,
    ) -> dict[str, Any]:
        file_id = uid()
        item = {
            "id": file_id,
            "owner_id": owner_id,
            "file_name": body.file_name,
            "size_bytes": body.size_bytes,
            "media_type": body.media_type,
            "sha256": body.sha256,
            "status": "uploading",
            "page_count": None,
            "failure_reason": None,
            "storage_path": f"uploads/{file_id}",
            "created_at": now(),
            "deleted": False,
        }
        self.files.create(item)
        return {
            "file_id": file_id,
            "upload_url": f"{base_url}api/v1/files/{file_id}/content",
            "upload_headers": {"content-type": body.media_type},
            "expires_at": now(),
            "max_size_bytes": MAX_FILE_SIZE_BYTES,
        }

    def file(
        self,
        file_id: str,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        item = self.files.get(file_id)
        if not item or item.get("deleted"):
            raise HTTPException(404, "File not found")
        if owner_id is not None and item.get("owner_id") != owner_id:
            raise HTTPException(404, "File not found")
        return item

    def save_content(
        self,
        file_id: str,
        content: bytes,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        item = self.file(file_id, owner_id)
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(413, "File too large")

        upload_path = self.content_path(item)
        upload_path.write_bytes(content)
        item["actual_size_bytes"] = len(content)
        item["status"] = "validating"
        self.files.update(item)
        return item

    def complete(
        self,
        file_id: str,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        item = self.file(file_id, owner_id)
        upload_path = self.content_path(item)
        if not upload_path.exists():
            raise HTTPException(422, "Upload content is missing")

        width_px, height_px = self._image_size(upload_path, item["media_type"])
        item.update(
            status="ready",
            page_count=1,
            actual_media_type=item["media_type"],
            width_px=width_px,
            height_px=height_px,
            failure_reason=None,
        )
        return self.files.update(item)

    def content_path(self, item: dict[str, Any]) -> Path:
        storage_path = item.get("storage_path")
        if storage_path:
            relative_path = str(storage_path).replace("\\", "/")
            expected_prefix = "uploads/"
            if not relative_path.startswith(expected_prefix):
                raise HTTPException(500, "Invalid stored file path")
            return self.store.uploads / relative_path.removeprefix(expected_prefix)
        return self.store.uploads / item["id"]

    @staticmethod
    def _image_size(path: Path, media_type: str) -> tuple[int, int]:
        if not media_type.startswith("image/"):
            return 1200, 1600
        try:
            with Image.open(path) as image:
                return image.size
        except (UnidentifiedImageError, OSError):
            return 1200, 1600

    def create_job(
        self,
        body: JobCreate,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        uploaded_file = self.file(body.file_id, owner_id)
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
        job = {
            "id": job_id,
            "owner_id": owner_id,
            "name": body.name,
            "file_id": body.file_id,
            "file_name": uploaded_file["file_name"],
            "model_id": body.model_id,
            "model_version": body.model_version,
            "status": "queued", "stage": "queued", "progress": 0,
            "created_at": created_at,
            "started_at": None, "finished_at": None,
            "page_ids": [page_id],
            "page_count": 1,
            "completed_pages": 0,
            "failed_pages": 0,
            "result_count": 0, "review_count": 0,
            "options": body.options,
            "deleted": False,
        }
        self.jobs.create(job)
        page = self._build_page(
            job_id,
            page_id,
            [],
            uploaded_file.get("width_px", 1200),
            uploaded_file.get("height_px", 1600),
            status="queued", review_count=0, processing_ms=0, roi_errors={},
        )
        self.page_repository.create(page)
        if self.job_submitter is None:
            raise HTTPException(503, "OCR worker is not available")
        self.job_submitter(job_id)
        response_fields = ("id", "status", "stage", "progress", "created_at")
        return {field: job[field] for field in response_fields}

    @staticmethod
    def _region_bbox(
        bbox: tuple[float, float, float, float], width: int, height: int,
    ) -> list[float]:
        values = [float(value) for value in bbox]
        if not all(math.isfinite(value) for value in values):
            raise HTTPException(422, "Region bbox coordinates must be finite")
        x1, y1, x2, y2 = values
        if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
            raise HTTPException(422, "Region bbox must be inside the source image")
        if x2 - x1 < 16 or y2 - y1 < 16:
            raise HTTPException(422, "Region bbox must be at least 16x16 pixels")
        return values

    def create_region_job(
        self,
        body: RegionJobCreate,
        owner_id: str,
    ) -> dict[str, Any]:
        if bool(body.file_id) == bool(body.source_job_id):
            raise HTTPException(422, "Exactly one of file_id and source_job_id is required")

        source_job = None
        file_id = body.file_id
        if body.source_job_id:
            source_job = self.job(body.source_job_id, owner_id)
            if source_job["status"] not in {"succeeded", "partial_success"}:
                raise HTTPException(409, "Source OCR job must be completed")
            file_id = source_job["file_id"]
        assert file_id is not None
        uploaded_file = self.file(file_id, owner_id)
        if uploaded_file["status"] != "ready" or not self.content_path(uploaded_file).exists():
            raise HTTPException(409, {"code": "SOURCE_FILE_UNAVAILABLE"})
        if not (uploaded_file.get("actual_media_type") or uploaded_file["media_type"]).startswith("image/"):
            raise HTTPException(422, "Region OCR currently supports images only")
        if body.model_id != "mock" or body.model_version != "1.0.0":
            raise HTTPException(422, "Unknown model version")
        if len(body.pages) != 1 or body.pages[0].page_no != 1:
            raise HTTPException(422, "Region OCR currently supports page 1 only")

        width = int(uploaded_file.get("width_px", 1200))
        height = int(uploaded_file.get("height_px", 1600))
        client_ids: set[str] = set()
        normalized_regions: list[dict[str, Any]] = []
        seen_boxes: set[tuple[float, ...]] = set()
        for order, region in enumerate(body.pages[0].regions, 1):
            if region.client_id in client_ids:
                raise HTTPException(422, "Region client_id values must be unique")
            client_ids.add(region.client_id)
            bbox = self._region_bbox(region.bbox, width, height)
            bbox_key = tuple(bbox)
            if bbox_key in seen_boxes:
                raise HTTPException(422, "Duplicate region bbox")
            seen_boxes.add(bbox_key)
            normalized_regions.append({
                "id": uid(), "job_id": "", "page_no": 1,
                "client_id": region.client_id, "bbox": bbox, "reading_order": order,
            })

        job_id = uid()
        page_id = uid()
        created_at = now()
        job = {
            "id": job_id, "owner_id": owner_id, "name": body.name,
            "file_id": file_id, "file_name": uploaded_file["file_name"],
            "model_id": body.model_id, "model_version": body.model_version,
            "status": "queued", "stage": "queued", "progress": 0,
            "created_at": created_at, "started_at": None, "finished_at": None,
            "page_ids": [page_id], "page_count": 1, "completed_pages": 0,
            "failed_pages": 0, "result_count": 0, "review_count": 0,
            "options": {"recognition_scope": "regions"}, "deleted": False,
        }
        self.jobs.create(job)
        self.page_repository.create(self._build_page(
            job_id, page_id, [], width, height,
            status="queued", review_count=0, processing_ms=0, roi_errors={},
        ))
        for region in normalized_regions:
            region["job_id"] = job_id
        self.region_jobs.create(
            job_id=job_id, source_job_id=body.source_job_id,
            file_id=file_id, created_by=owner_id, regions=normalized_regions,
        )
        if self.job_submitter is None:
            raise HTTPException(503, "OCR worker is not available")
        self.job_submitter(job_id)
        return {key: job[key] for key in ("id", "status", "stage", "progress", "created_at")}

    def region_job_context(self, job_id: str, owner_id: str) -> dict[str, Any]:
        self.job(job_id, owner_id)
        context = self.region_jobs.context(job_id)
        if context is None:
            raise HTTPException(404, "Region OCR job not found")
        return {
            **context,
            "pages": [{
                "page_no": 1,
                "regions": [region for region in context["regions"] if region["page_no"] == 1],
            }],
        }

    @staticmethod
    def _build_page(
        job_id: str,
        page_id: str,
        result_ids: list[str],
        width_px: int,
        height_px: int,
        *,
        status: str,
        review_count: int,
        processing_ms: int,
        roi_errors: dict[str, str],
    ) -> dict[str, Any]:
        return {
            "id": page_id,
            "job_id": job_id,
            "page_no": 1,
            "label": "第 1 页",
            "status": status,
            "image": {
                "url": None,
                "thumbnail_url": None,
                "width_px": width_px,
                "height_px": height_px,
                "rotation": 0,
                "render_dpi": 300,
            },
            "result_ids": result_ids,
            "result_count": len(result_ids),
            "review_count": review_count,
            "processing_ms": processing_ms,
            "error": (
                {"code": "OCR_PARTIAL_FAILURE", "roi_errors": roi_errors}
                if roi_errors
                else None
            ),
        }

    def job(
        self,
        job_id: str,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        job = self.jobs.get(job_id)
        if not job or job.get("deleted"):
            raise HTTPException(404, "Job not found")
        if owner_id is not None and job.get("owner_id") != owner_id:
            raise HTTPException(404, "Job not found")
        return job

    def all_jobs(self) -> list[dict[str, Any]]:
        return self.jobs.all()

    def update_file(self, item: dict[str, Any]) -> dict[str, Any]:
        return self.files.update(item)

    def pages(
        self,
        job_id: str,
        owner_id: str | None = None,
    ) -> list[dict[str, Any]]:
        job = self.job(job_id, owner_id)
        uploaded_file = self.file(job["file_id"], owner_id)
        pages = [self.page_repository.get(page_id) for page_id in job["page_ids"]]
        public_pages = [
            self._public_page(page) for page in pages if page is not None
        ]
        content_path = self.content_path(uploaded_file)
        is_image = uploaded_file.get("media_type", "").startswith("image/")
        image_url = (
            f"/files/{uploaded_file['id']}/content"
            if is_image and content_path.exists()
            else None
        )
        for page in public_pages:
            page["image"]["url"] = image_url
            page["image"]["thumbnail_url"] = image_url
        return public_pages

    @staticmethod
    def _public_page(page: dict[str, Any]) -> dict[str, Any]:
        excluded_fields = {"result_ids", "job_id"}
        return {
            key: value
            for key, value in page.items()
            if key not in excluded_fields
        }

    def result(
        self,
        result_id: str,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        result = self.result_repository.get(result_id)
        if not result:
            raise HTTPException(404, "OCR result not found")
        if owner_id is not None:
            self.job(result["job_id"], owner_id)
        return result

    def page(self, page_id: str) -> dict[str, Any] | None:
        return self.page_repository.get(page_id)

    def comments(self, result_id: str) -> list[dict[str, Any]]:
        return self.comment_repository.list_for_result(result_id)

    def corrections(self, result_id: str) -> list[dict[str, Any]]:
        return self.correction_repository.list_for_result(result_id)

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

    def update_result_review_status(
        self, result_ids: list[str], review_status: str, owner_id: str,
    ) -> list[dict[str, str]]:
        unique_ids = list(dict.fromkeys(result_ids))
        for result_id in unique_ids:
            self.result(result_id, owner_id)
        self.result_repository.update_review_status(unique_ids, review_status)
        return [{"id": result_id, "review_status": review_status} for result_id in unique_ids]

    @staticmethod
    def _validated_bbox(bbox: Any, width: float, height: float) -> list[float]:
        values = [float(value) for value in bbox]
        x1, y1, x2, y2 = values
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise HTTPException(422, "BBox must be inside the page and have positive size")
        if x2 - x1 < 4 or y2 - y1 < 4:
            raise HTTPException(422, "BBox minimum size is 4 x 4 pixels")
        return values

    @classmethod
    def _validated_geometry(
        cls, bbox: Any, polygon: Any, width: float, height: float,
    ) -> tuple[list[float], list[list[float]]]:
        if polygon is None:
            values = cls._validated_bbox(bbox, width, height)
            return values, [
                [values[0], values[1]], [values[2], values[1]],
                [values[2], values[3]], [values[0], values[3]],
            ]
        points = [[float(point[0]), float(point[1])] for point in polygon]
        if any(not (0 <= point[0] <= width and 0 <= point[1] <= height) for point in points):
            raise HTTPException(422, "Polygon points must be inside the page")
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        compatible_bbox = cls._validated_bbox(
            [min(xs), min(ys), max(xs), max(ys)], width, height,
        )
        twice_area = abs(sum(
            point[0] * points[(index + 1) % 4][1]
            - points[(index + 1) % 4][0] * point[1]
            for index, point in enumerate(points)
        ))
        if twice_area < 32:
            raise HTTPException(422, "Polygon area is too small")
        return compatible_bbox, points

    def save_result_edits(
        self, job_id: str, page_no: int, body: Any, owner_id: str,
    ) -> dict[str, Any]:
        job = self.job(job_id, owner_id)
        page = None
        for page_id in job["page_ids"]:
            candidate = self.page(page_id)
            if candidate and candidate["page_no"] == page_no:
                page = candidate
                break
        if page is None:
            raise HTTPException(404, "Page not found")
        image = page["image"]
        width, height = float(image["width_px"]), float(image["height_px"])
        updates = []
        for item in body.updates:
            bbox, polygon = self._validated_geometry(item.bbox, item.polygon, width, height)
            updates.append({**item.model_dump(), "bbox": bbox, "polygon": polygon, "revision_id": uid()})
        creates = []
        for item in body.creates:
            bbox, polygon = self._validated_geometry(item.bbox, item.polygon, width, height)
            creates.append({
                **item.model_dump(), "id": uid(), "bbox": bbox, "polygon": polygon,
                "revision_id": uid(), "text": item.text.strip(),
            })
        if any(not item["text"] for item in creates):
            raise HTTPException(422, "Manual result text is required")
        deletes = [{**item.model_dump(), "revision_id": uid()} for item in body.deletes]
        try:
            return self.result_repository.apply_edits(
                page=page, updates=updates, creates=creates, deletes=deletes, user_id=owner_id,
            )
        except KeyError as exc:
            raise HTTPException(404, "OCR result not found") from exc
        except ValueError as exc:
            raise HTTPException(409, {"code": "GEOMETRY_REVISION_CONFLICT", "result_id": str(exc)}) from exc

    def add_correction(
        self,
        result_id: str,
        body: CorrectionCreate,
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        result = self.result(result_id, actor["id"])
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
            "created_by": {"id": actor["id"], "name": actor["name"]},
            "created_at": now(),
        }
        self.correction_repository.create(correction, actor["id"], body.base_revision)
        result["revision"] = correction["revision"]
        result["current_correction"] = correction
        self.result_repository.update_revision(result)
        return correction

    def add_comment(
        self,
        result_id: str,
        content: str,
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        self.result(result_id, actor["id"])
        comment = {
            "id": uid(),
            "result_id": result_id,
            "content": content,
            "author": {"id": actor["id"], "name": actor["name"]},
            "created_at": now(),
            "updated_at": None,
            "deleted": False,
        }
        self.comment_repository.create(comment, actor["id"])
        comment_count = len(self.comments(result_id))
        return {**comment, "comment_count": comment_count}

    def update_comment(
        self,
        result_id: str,
        comment_id: str,
        content: str,
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        self.result(result_id, actor["id"])
        comment = self.comment_repository.get(comment_id)
        if not comment or comment["result_id"] != result_id or comment.get("deleted"):
            raise HTTPException(404, "Comment not found")
        if comment["author"]["id"] != actor["id"]:
            raise HTTPException(403, "Only the comment author can edit it")
        updated = self.comment_repository.update(comment_id, content)
        return {**updated, "comment_count": len(self.comments(result_id))}

    def delete_comment(
        self,
        result_id: str,
        comment_id: str,
        actor: dict[str, Any],
    ) -> None:
        self.result(result_id, actor["id"])
        comment = self.comment_repository.get(comment_id)
        if not comment or comment["result_id"] != result_id:
            raise HTTPException(404, "Comment not found")
        if comment["author"]["id"] != actor["id"]:
            raise HTTPException(403, "Only the comment author can delete it")
        self.comment_repository.delete(comment_id)

    def export(
        self,
        job_id: str,
        body: ExportCreate,
        base_url: str,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        job = self.job(job_id, owner_id)
        export_id = uid()
        export_path = self.store.exports / f"{export_id}.xlsx"
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "精简结果" if body.mode == "simple" else "完整结果"
        if body.mode == "simple":
            worksheet.append(["编号", "端子排最终识别结果"])
        else:
            worksheet.append([
                "page_no",
                "reading_order",
                "original_text",
                "display_text",
                "confidence",
                "bbox",
                "comments",
            ])
        self._append_export_rows(worksheet, job, body.mode)
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
        self.export_repository.create(export, owner_id)
        return export

    def get_export(
        self,
        job_id: str,
        export_id: str,
        owner_id: str,
    ) -> dict[str, Any]:
        self.job(job_id, owner_id)
        export = self.export_repository.get(export_id)
        if not export or export["job_id"] != job_id:
            raise HTTPException(404, "Export not found")
        return export

    def idempotent_response(
        self,
        user_id: str,
        route: str,
        key: str,
    ) -> dict[str, Any] | None:
        return self.idempotency_repository.get(user_id, route, key)

    def save_idempotent_response(
        self,
        user_id: str,
        route: str,
        key: str,
        request_payload: str,
        response_body: dict[str, Any],
    ) -> None:
        self.idempotency_repository.create(
            user_id, route, key, request_payload, response_body
        )

    def _append_export_rows(
        self,
        worksheet: Any,
        job: dict[str, Any],
        mode: str,
    ) -> None:
        item_index = 0
        for page_id in job["page_ids"]:
            page = self.page_repository.get(page_id)
            if page is None:
                continue
            for result_id in page["result_ids"]:
                result = self.public_result(self.result(result_id))
                if result.get("review_status") in {"deleted", "false_positive"}:
                    continue
                item_index += 1
                if mode == "simple":
                    worksheet.append([str(item_index).zfill(2), result["display_text"]])
                    continue
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
