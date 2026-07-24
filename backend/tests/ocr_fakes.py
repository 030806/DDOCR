from pathlib import Path
from time import monotonic, sleep
from typing import Any

from fastapi.testclient import TestClient

from app.ocr.contracts import AdapterDetection, AdapterPageResult


class FakeOcrAdapter:
    def recognize_file(self, source_path: Path, *, options: dict[str, Any] | None = None) -> AdapterPageResult:
        del source_path, options
        values = (("XT-101", 0.98, (180., 240., 520., 320.)), ("QF10I", 0.884, (620., 240., 940., 320.)), ("24V DC", 0.96, (180., 410., 520., 490.)))
        return AdapterPageResult(tuple(
            AdapterDetection(text, score, ((box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])), box, "page_1", index == 2, {})
            for index, (text, score, box) in enumerate(values)
        ), {}, 20)


def wait_for_job(client: TestClient, job_id: str, headers: dict[str, str], timeout: float = 5.0) -> dict[str, Any]:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        response = client.get(f"/api/v1/ocr/jobs/{job_id}", headers=headers)
        job = response.json()["data"]
        if job["status"] in {"succeeded", "partial_success", "failed"}:
            return job
        sleep(0.01)
    raise AssertionError(f"OCR job did not finish: {job_id}")
