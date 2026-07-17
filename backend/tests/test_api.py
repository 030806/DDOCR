from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app


def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(str(tmp_path)))


def workflow(test_client: TestClient) -> str:
    upload_response = test_client.post(
        "/api/v1/files/upload-sessions",
        json={
            "file_name": "terminal.png",
            "size_bytes": 3,
            "media_type": "image/png",
        },
    )
    upload = upload_response.json()["data"]
    file_id = upload["file_id"]

    content_response = test_client.put(
        f"/api/v1/files/{file_id}/content",
        content=b"img",
    )
    assert content_response.status_code == 200

    complete_response = test_client.post(
        f"/api/v1/files/{file_id}/complete"
    )
    assert complete_response.json()["data"]["status"] == "ready"

    job_response = test_client.post(
        "/api/v1/ocr/jobs",
        json={
            "name": "demo",
            "file_id": file_id,
            "model_id": "mock",
            "model_version": "1.0.0",
        },
    )
    assert job_response.status_code == 202
    return job_response.json()["data"]["id"]


def get_first_result(
    test_client: TestClient,
    job_id: str,
) -> dict[str, Any]:
    response = test_client.get(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/results"
    )
    return response.json()["data"]["items"][0]


def test_upload_job_and_results(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    job_id = workflow(test_client)

    job_response = test_client.get(f"/api/v1/ocr/jobs/{job_id}")
    job = job_response.json()["data"]
    assert job["status"] == "succeeded"
    assert job["progress"] == 100

    results_response = test_client.get(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/results"
    )
    items = results_response.json()["data"]["items"]
    assert len(items) == 3
    assert len(items[0]["bbox"]) == 4
    assert 0 <= items[0]["confidence"] <= 1


def test_correction_comment_and_export(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    job_id = workflow(test_client)
    result_id = get_first_result(test_client, job_id)["id"]

    correction_response = test_client.post(
        f"/api/v1/ocr/results/{result_id}/corrections",
        json={"corrected_text": "XT-102", "base_revision": 0},
    )
    assert correction_response.status_code == 201

    conflict_response = test_client.post(
        f"/api/v1/ocr/results/{result_id}/corrections",
        json={"corrected_text": "bad", "base_revision": 0},
    )
    assert conflict_response.status_code == 409

    comment_response = test_client.post(
        f"/api/v1/ocr/results/{result_id}/comments",
        json={"content": "请复核"},
    )
    assert comment_response.json()["data"]["comment_count"] == 1

    export_response = test_client.post(
        f"/api/v1/ocr/jobs/{job_id}/exports",
        json={
            "format": "xlsx",
            "mode": "full",
            "scope": "all_pages",
        },
    )
    export_id = export_response.json()["data"]["id"]
    download_response = test_client.get(
        f"/api/v1/ocr/jobs/{job_id}/exports/{export_id}/download"
    )
    assert download_response.status_code == 200
