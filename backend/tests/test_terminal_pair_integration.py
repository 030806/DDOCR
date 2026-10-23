from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import create_app
from app.terminal_pair.client import TerminalPairClient
from tests.ocr_fakes import FakeOcrAdapter, wait_for_job
from tests.test_api import register_headers, upload_image, workflow


class FakeTerminalDetector:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[Path, int, int]] = []

    def detect(self, path: Path, width: int, height: int) -> list[dict]:
        self.calls.append((path, width, height))
        if self.fail:
            raise RuntimeError("detector unavailable")
        return [
            {"id": "model-1", "x": 50, "y": 100, "score": 0.9, "source": "model"},
            {"id": "model-2", "x": 50, "y": 200, "score": 0.8, "source": "model"},
        ]


def configured_client(tmp_path: Path, detector: FakeTerminalDetector) -> TestClient:
    return TestClient(create_app(
        str(tmp_path), f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        FakeOcrAdapter(), terminal_detector=detector,
    ))


def test_detection_and_manual_edit_are_saved_separately(tmp_path: Path) -> None:
    detector = FakeTerminalDetector()
    client = configured_client(tmp_path, detector)
    job_id, headers = workflow(client)
    assert detector.calls[0][1:] == (1200, 1600)
    page = client.get(f"/api/v1/ocr/jobs/{job_id}/pages", headers=headers).json()["data"]["items"][0]
    assert len(page["terminal_model_points"]) == len(page["terminal_points"]) == 2
    original = page["terminal_model_points"]
    points = page["terminal_points"] + [{"id": "draft-new", "x": 50, "y": 300}]
    updated = client.put(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/terminal-points",
        headers=headers, json={"base_revision": 0, "points": points},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["count"] == 3
    page = client.get(f"/api/v1/ocr/jobs/{job_id}/pages", headers=headers).json()["data"]["items"][0]
    assert page["terminal_model_points"] == original
    assert len(page["terminal_points"]) == 3
    assert page["terminal_points"][-1]["source"] == "manual"
    assert client.put(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/terminal-points",
        headers=headers, json={"base_revision": 0, "points": points},
    ).status_code == 409
    export = client.post(
        f"/api/v1/ocr/jobs/{job_id}/exports", headers=headers,
        json={"format": "xlsx", "mode": "simple", "scope": "all_pages"},
    )
    assert export.status_code == 202
    export_id = export.json()["data"]["id"]
    workbook = load_workbook(client.app.state.service.store.exports / f"{export_id}.xlsx")
    pair_rows = list(workbook["端子对照表"].values)
    assert {row[1] for row in pair_rows[1:] if row[1]} == {"1", "2", "3"}
    assert sum(bool(row[2]) for row in pair_rows[1:]) == 3
    cleared = client.put(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/terminal-points",
        headers=headers, json={"base_revision": 1, "points": []},
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["count"] == 0
    page = client.get(f"/api/v1/ocr/jobs/{job_id}/pages", headers=headers).json()["data"]["items"][0]
    assert page["terminal_points"] == []
    assert page["terminal_model_points"] == original


def test_duplicate_model_boxes_do_not_create_extra_terminal_numbers(tmp_path: Path) -> None:
    class DuplicatingDetector(FakeTerminalDetector):
        def detect(self, path: Path, width: int, height: int) -> list[dict]:
            points = super().detect(path, width, height)
            points[0]["bbox"] = [40, 90, 60, 110]
            points[1]["bbox"] = [40, 190, 60, 210]
            return [{**points[0], "id": "duplicate", "y": 102, "score": 0.7}, *points]

    client = configured_client(tmp_path, DuplicatingDetector())
    job_id, headers = workflow(client)
    page = client.get(f"/api/v1/ocr/jobs/{job_id}/pages", headers=headers).json()["data"]["items"][0]
    assert len(page["terminal_model_points"]) == 3
    assert [point["id"] for point in page["terminal_points"]] == ["model-1", "model-2"]


def test_yolox_failure_keeps_ocr_results(tmp_path: Path) -> None:
    client = configured_client(tmp_path, FakeTerminalDetector(fail=True))
    job_id, headers = workflow(client)
    page = client.get(f"/api/v1/ocr/jobs/{job_id}/pages", headers=headers).json()["data"]["items"][0]
    assert page["terminal_points"] is None
    assert page["terminal_error"]["code"] == "YOLOX_INFERENCE_FAILED"
    results = client.get(f"/api/v1/ocr/jobs/{job_id}/pages/1/results", headers=headers).json()["data"]["items"]
    assert len(results) == 3


def test_ocr_failure_keeps_terminal_points(tmp_path: Path) -> None:
    class FailingOcrAdapter(FakeOcrAdapter):
        def recognize_file(self, source_path, *, options=None):
            raise RuntimeError("OCR unavailable")

    detector = FakeTerminalDetector()
    client = TestClient(create_app(
        str(tmp_path), f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        FailingOcrAdapter(), terminal_detector=detector,
    ))
    job_id, headers = workflow(client)
    page = client.get(f"/api/v1/ocr/jobs/{job_id}/pages", headers=headers).json()["data"]["items"][0]
    assert page["error"]["code"] == "OCR_TASK_FAILED"
    assert len(page["terminal_points"]) == 2
    results = client.get(f"/api/v1/ocr/jobs/{job_id}/pages/1/results", headers=headers).json()["data"]["items"]
    assert results == []


def test_rerun_preserves_ocr_regions_but_detects_whole_image(tmp_path: Path) -> None:
    detector = FakeTerminalDetector()
    client = configured_client(tmp_path, detector)
    headers = register_headers(client)
    file_id = upload_image(client, headers)
    created = client.post("/api/v1/ocr/region-jobs", headers=headers, json={
        "name": "局部识别", "file_id": file_id, "model_id": "mock", "model_version": "1.0.0",
        "pages": [{"page_no": 1, "regions": [{"client_id": "roi-1", "bbox": [100, 120, 400, 300]}]}],
    })
    source_id = created.json()["data"]["id"]
    assert wait_for_job(client, source_id, headers)["status"] == "succeeded"
    rerun = client.post(f"/api/v1/ocr/jobs/{source_id}/rerun", headers=headers, json={
        "model_id": "mock", "model_version": "1.0.0",
    })
    assert rerun.status_code == 202
    rerun_id = rerun.json()["data"]["id"]
    assert wait_for_job(client, rerun_id, headers)["status"] == "succeeded"
    context = client.get(f"/api/v1/ocr/region-jobs/{rerun_id}/context", headers=headers).json()["data"]
    assert context["regions"][0]["bbox"] == [100.0, 120.0, 400.0, 300.0]
    assert len(detector.calls) == 2


def test_client_only_allows_loopback() -> None:
    for value in ("https://127.0.0.1:8765", "http://example.com:8765", "http://127.0.0.1:8765/proxy"):
        try:
            TerminalPairClient(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Unsafe YOLOX URL accepted: {value}")
    assert TerminalPairClient("http://127.0.0.1:8765").base_url == "http://127.0.0.1:8765"
