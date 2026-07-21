import hashlib
import hmac
import secrets
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from openpyxl import Workbook
from PIL import Image, UnidentifiedImageError

from app.models.store import Store
from app.schemas.contracts import (
    CorrectionCreate,
    ExportCreate,
    JobCreate,
    UploadSessionCreate,
)
from app.utils.common import now, uid

MAX_FILE_SIZE_BYTES = 104_857_600


class MockOcrService:
    def __init__(self, store: Store) -> None:
        self.store = store

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
        if email and any(user.get("email") == email for user in self.store.all("user")):
            raise HTTPException(409, "Email is already registered")
        if any(user.get("phone") == phone for user in self.store.all("user")):
            raise HTTPException(409, "Phone is already registered")
        if any(user["employee_no"] == values["employee_no"] for user in self.store.all("user")):
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
        self.store.put("user", user_id, user)
        return self.create_session(user)

    def login_user(self, phone: str, password: str) -> dict[str, Any]:
        normalized = phone.strip()
        user = next(
            (item for item in self.store.all("user") if item.get("phone") == normalized and not item.get("deleted")),
            None,
        )
        if not user or not self._password_matches(password, user):
            raise HTTPException(401, "Invalid phone or password")
        return self.create_session(user)

    def create_session(self, user: dict[str, Any]) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        user["last_login_at"] = now()
        self.store.put("user", user["id"], user)
        self.store.put("session", token, {
            "token": token,
            "user_id": user["id"],
            "created_at": now(),
            "revoked": False,
        })
        return {"access_token": token, "token_type": "bearer", "user": self.public_user(user)}

    def session_user(self, token: str) -> dict[str, Any]:
        session = self.store.get("session", token)
        if not session or session.get("revoked"):
            raise HTTPException(401, "Invalid or expired session")
        user = self.store.get("user", session["user_id"])
        if not user or user.get("deleted"):
            raise HTTPException(401, "User not found")
        return user

    def revoke_session(self, token: str) -> None:
        session = self.store.get("session", token)
        if session:
            session["revoked"] = True
            self.store.put("session", token, session)

    def update_user(self, user: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        user.update({key: value for key, value in values.items() if value is not None})
        user["updated_at"] = now()
        self.store.put("user", user["id"], user)
        return self.public_user(user)

    def change_password(self, user: dict[str, Any], current: str, new: str) -> None:
        if not self._password_matches(current, user):
            raise HTTPException(409, "Current password is incorrect")
        self._validate_password(new)
        salt, password_hash = self._password_hash(new)
        user["password_salt"] = salt
        user["password_hash"] = password_hash
        user["updated_at"] = now()
        self.store.put("user", user["id"], user)

    def ensure_demo_job(self) -> None:
        """Seed one API-backed task when the mock backend starts empty."""
        if self.store.all("job"):
            return

        file_id = "demo-terminal-file"
        if not self.store.get("file", file_id):
            self.store.put(
                "file",
                file_id,
                {
                    "id": file_id,
                    "file_name": "terminal_demo.png",
                    "size_bytes": 0,
                    "media_type": "image/png",
                    "status": "ready",
                    "page_count": 1,
                    "failure_reason": None,
                    "created_at": now(),
                    "deleted": False,
                },
            )

        self.create_job(
            JobCreate(
                name="端子排 OCR 联调示例",
                file_id=file_id,
                model_id="mock",
                model_version="1.0.0",
            )
        )

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
        self.store.put("file", file_id, item)
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
        item = self.store.get("file", file_id)
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
        self.store.put("file", file_id, item)
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
        return self.store.put("file", file_id, item)

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
        # TODO(integration): Replace fixed results with the real OCR adapter. The
        # API response contract and bbox format should remain unchanged.
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
        page = self._build_page(
            job_id,
            page_id,
            result_ids,
            uploaded_file.get("width_px", 1200),
            uploaded_file.get("height_px", 1600),
        )
        self.store.put("page", page_id, page)

        job = {
            "id": job_id,
            "owner_id": owner_id,
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
        width_px: int,
        height_px: int,
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
                "width_px": width_px,
                "height_px": height_px,
                "rotation": 0,
                "render_dpi": 300,
            },
            "result_ids": result_ids,
            "result_count": len(result_ids),
            "review_count": 1,
            "processing_ms": 20,
            "error": None,
        }

    def job(
        self,
        job_id: str,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        job = self.store.get("job", job_id)
        if not job or job.get("deleted"):
            raise HTTPException(404, "Job not found")
        if owner_id is not None and job.get("owner_id") != owner_id:
            raise HTTPException(404, "Job not found")
        return job

    def pages(
        self,
        job_id: str,
        owner_id: str | None = None,
    ) -> list[dict[str, Any]]:
        job = self.job(job_id, owner_id)
        uploaded_file = self.file(job["file_id"], owner_id)
        pages = [
            self.store.get("page", page_id) for page_id in job["page_ids"]
        ]
        public_pages = [
            self._public_page(page) for page in pages if page is not None
        ]
        content_path = self.content_path(uploaded_file)
        is_image = uploaded_file.get("media_type", "").startswith("image/")
        image_url = (
            f"/api/v1/files/{uploaded_file['id']}/content"
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
        result = self.store.get("result", result_id)
        if not result:
            raise HTTPException(404, "OCR result not found")
        if owner_id is not None:
            self.job(result["job_id"], owner_id)
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
        self.store.put("correction", correction["id"], correction)
        result["revision"] = correction["revision"]
        result["current_correction"] = correction
        self.store.put("result", result_id, result)
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
        self.store.put("comment", comment["id"], comment)
        comment_count = len(self.comments(result_id))
        return {**comment, "comment_count": comment_count}

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
