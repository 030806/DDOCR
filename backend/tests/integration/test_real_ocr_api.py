"""Opt-in end-to-end API acceptance test using the real PaddleOCR models."""

from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
from time import monotonic

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app.main import create_app
from app.models.schema import ocr_jobs, pages, results
from app.vendor.terminal_ocr_demo.config import RESOURCE_ROOT
from tests.ocr_fakes import wait_for_job


pytestmark = pytest.mark.skipif(
    os.getenv("DDOCR_RUN_REAL_OCR_API") != "1",
    reason="set DDOCR_RUN_REAL_OCR_API=1 to run the real OCR API test",
)


def _source_image_bytes() -> bytes:
    """Return the model-provider's validated terminal ROI as a standalone PNG."""

    repository_root = Path(__file__).resolve().parents[3]
    source_path = repository_root / "samples" / "电缆端子2.png"
    assert source_path.is_file(), f"real OCR sample is missing: {source_path}"
    with Image.open(source_path) as source:
        # This ROI is documented by the model provider and contains terminal IDs.
        cropped = source.convert("RGB").crop((540, 180, 1100, 1180))
        output = BytesIO()
        cropped.save(output, format="PNG")
    return output.getvalue()


def _register(client: TestClient) -> dict[str, str]:
    """Create the owner required by the authenticated OCR API."""

    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "真实 OCR 验收员",
            "phone": "13800138888",
            "password": "RealOcr123",
            "employee_no": "REAL-OCR-001",
        },
    )
    assert response.status_code == 201
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_real_ocr_upload_job_database_and_results_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise upload -> real OCR -> relational persistence -> result query."""

    repository_root = Path(__file__).resolve().parents[3]
    model_cache = repository_root / "backend" / "data" / "paddlex-cache"
    monkeypatch.setenv("DDOCR_OCR_MODEL_CACHE", str(model_cache.resolve()))
    monkeypatch.setenv(
        "DDOCR_OCR_CODE_LIBRARY",
        str((RESOURCE_ROOT / "terminal_id_library.csv").resolve()),
    )
    # One orientation is sufficient for this validated crop and keeps the
    # synchronous acceptance test bounded. Production defaults remain unchanged.
    monkeypatch.setenv("DDOCR_OCR_ROTATIONS", "0")
    monkeypatch.setenv("DDOCR_OCR_SCALE", "2.0")

    database_path = tmp_path / "real-ocr-api.db"
    app = create_app(
        str(tmp_path / "data"),
        f"sqlite:///{database_path.as_posix()}",
    )
    image_content = _source_image_bytes()

    with TestClient(app) as client:
        headers = _register(client)

        upload_response = client.post(
            "/api/v1/files/upload-sessions",
            headers=headers,
            json={
                "file_name": "terminal-roi.png",
                "size_bytes": len(image_content),
                "media_type": "image/png",
            },
        )
        assert upload_response.status_code == 201
        file_id = upload_response.json()["data"]["file_id"]

        content_response = client.put(
            f"/api/v1/files/{file_id}/content",
            headers=headers,
            content=image_content,
        )
        assert content_response.status_code == 200

        complete_response = client.post(
            f"/api/v1/files/{file_id}/complete",
            headers=headers,
        )
        assert complete_response.status_code == 200
        completed_file = complete_response.json()["data"]
        assert completed_file["status"] == "ready"
        assert completed_file["width_px"] == 560
        assert completed_file["height_px"] == 1000

        submitted_at = monotonic()
        create_job_response = client.post(
            "/api/v1/ocr/jobs",
            headers=headers,
            json={
                "name": "真实 OCR API 验收",
                "file_id": file_id,
                # The API compatibility identifier is intentionally unchanged.
                "model_id": "mock",
                "model_version": "1.0.0",
                "options": {},
            },
        )
        submit_duration = monotonic() - submitted_at
        assert create_job_response.status_code == 202
        assert submit_duration < 10.0
        created_job = create_job_response.json()["data"]
        assert created_job["status"] == "queued"
        assert created_job["stage"] == "queued"
        assert created_job["progress"] == 0
        job_id = created_job["id"]
        wait_for_job(client, job_id, headers, timeout=300.0)

        job_response = client.get(
            f"/api/v1/ocr/jobs/{job_id}",
            headers=headers,
        )
        assert job_response.status_code == 200
        job = job_response.json()["data"]
        assert job["status"] == "succeeded"
        assert job["completed_pages"] == 1
        assert job["failed_pages"] == 0
        assert job["result_count"] > 0

        pages_response = client.get(
            f"/api/v1/ocr/jobs/{job_id}/pages",
            headers=headers,
        )
        assert pages_response.status_code == 200
        page_items = pages_response.json()["data"]["items"]
        assert len(page_items) == 1
        page = page_items[0]
        assert page["status"] == "succeeded"
        assert page["page_no"] == 1
        assert page["result_count"] > 0

        results_response = client.get(
            f"/api/v1/ocr/jobs/{job_id}/pages/1/results",
            headers=headers,
        )
        assert results_response.status_code == 200
        result_items = results_response.json()["data"]["items"]
        assert len(result_items) == job["result_count"]
        assert len(result_items) == page["result_count"]
        assert len(result_items) > 0

        # These are exactly the fields consumed by src/api/ocr.ts::mapApiResult.
        frontend_required_fields = {
            "id",
            "text",
            "confidence",
            "bbox",
            "display_text",
            "is_corrected",
            "comments",
            "revision",
        }
        for item in result_items:
            assert frontend_required_fields <= item.keys()
            assert item["text"] is not None
            assert 0.0 <= item["confidence"] <= 1.0
            assert item["revision"] == 0
            assert item["comments"] == []
            assert item["display_text"] == item["text"]
            assert item["is_corrected"] is False

            bbox = item["bbox"]
            assert isinstance(bbox, list) and len(bbox) == 4
            x1, y1, x2, y2 = bbox
            assert 0.0 <= x1 < x2 <= completed_file["width_px"]
            assert 0.0 <= y1 < y2 <= completed_file["height_px"]

            polygon = item["polygon"]
            assert isinstance(polygon, list) and len(polygon) >= 2
            for point in polygon:
                assert isinstance(point, list) and len(point) >= 2
                assert 0.0 <= point[0] <= completed_file["width_px"]
                assert 0.0 <= point[1] <= completed_file["height_px"]

    with app.state.service.store.engine.connect() as connection:
        job_rows = connection.scalar(select(func.count()).select_from(ocr_jobs))
        page_rows = connection.scalar(select(func.count()).select_from(pages))
        result_rows = connection.scalar(select(func.count()).select_from(results))

        assert job_rows == 1
        assert page_rows == 1
        assert result_rows == job["result_count"]
        assert result_rows > 0

        stored_job = connection.execute(
            select(ocr_jobs).where(ocr_jobs.c.id == job_id)
        ).mappings().one()
        assert stored_job["status"] == "succeeded"
        assert stored_job["result_count"] == result_rows

        stored_page = connection.execute(
            select(pages).where(pages.c.job_id == job_id)
        ).mappings().one()
        assert stored_page["status"] == "succeeded"
        assert stored_page["result_count"] == result_rows

        stored_results = connection.execute(
            select(results).where(results.c.job_id == job_id)
        ).mappings().all()
        assert len(stored_results) == result_rows
        assert all(row["current_revision"] == 0 for row in stored_results)
        assert all(0.0 <= row["confidence"] <= 1.0 for row in stored_results)
