from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from tests.ocr_fakes import FakeOcrAdapter, wait_for_job


def client(tmp_path: Path) -> TestClient:
    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    app = create_app(str(tmp_path), database_url, FakeOcrAdapter())
    return TestClient(app)


def workflow(test_client: TestClient) -> tuple[str, dict[str, str]]:
    headers = register_headers(test_client)
    image_buffer = BytesIO()
    Image.new("RGB", (1200, 1600), "white").save(image_buffer, format="PNG")
    image_content = image_buffer.getvalue()
    upload_response = test_client.post(
        "/api/v1/files/upload-sessions",
        headers=headers,
        json={
            "file_name": "terminal.png",
            "size_bytes": len(image_content),
            "media_type": "image/png",
        },
    )
    upload = upload_response.json()["data"]
    file_id = upload["file_id"]

    content_response = test_client.put(
        f"/api/v1/files/{file_id}/content",
        content=image_content,
        headers=headers,
    )
    assert content_response.status_code == 200

    complete_response = test_client.post(
        f"/api/v1/files/{file_id}/complete",
        headers=headers,
    )
    assert complete_response.json()["data"]["status"] == "ready"

    job_response = test_client.post(
        "/api/v1/ocr/jobs",
        headers=headers,
        json={
            "name": "demo",
            "file_id": file_id,
            "model_id": "mock",
            "model_version": "1.0.0",
        },
    )
    assert job_response.status_code == 202
    job_id = job_response.json()["data"]["id"]
    wait_for_job(test_client, job_id, headers)
    return job_id, headers


def get_first_result(
    test_client: TestClient,
    job_id: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    response = test_client.get(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/results",
        headers=headers,
    )
    return response.json()["data"]["items"][0]


def register_headers(
    test_client: TestClient,
    phone: str = "13700137000",
    employee_no: str = "QC-REVIEW",
) -> dict[str, str]:
    response = test_client.post(
        "/api/v1/auth/register",
        json={
            "name": "复核员", "phone": phone,
            "password": "Review123", "employee_no": employee_no,
        },
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_empty_backend_seeds_api_demo_results(
    tmp_path: Path,
) -> None:
    test_client = client(tmp_path)
    assert test_client.get("/api/v1/ocr/jobs").status_code == 401
    headers = register_headers(test_client)
    jobs_response = test_client.get("/api/v1/ocr/jobs", headers=headers)
    jobs = jobs_response.json()["data"]["items"]
    assert jobs == []


def test_register_login_profile_password_and_logout(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    registration = test_client.post(
        "/api/v1/auth/register",
        json={
            "name": "张工", "email": "zhang@example.com",
            "password": "Terminal123", "employee_no": "QC-100",
            "department": "质量部", "phone": "13800138000",
        },
    )
    assert registration.status_code == 201
    session = registration.json()["data"]
    assert session["user"]["phone_masked"] == "138****8000"
    assert "password_hash" not in session["user"]
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    assert test_client.get("/api/v1/users/me", headers=headers).json()["data"]["employee_no"] == "QC-100"

    profile = test_client.patch(
        "/api/v1/users/me", headers=headers,
        json={"name": "张工程师", "department": "智能制造部"},
    )
    assert profile.json()["data"]["name"] == "张工程师"
    assert test_client.post(
        "/api/v1/auth/change-password", headers=headers,
        json={"current_password": "Terminal123", "new_password": "Updated456"},
    ).status_code == 204
    assert test_client.post(
        "/api/v1/auth/login",
        json={"phone": "13800138000", "password": "Terminal123"},
    ).status_code == 401
    assert test_client.post(
        "/api/v1/auth/login",
        json={"phone": "13800138000", "password": "Updated456"},
    ).status_code == 200
    assert test_client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert test_client.get("/api/v1/users/me", headers=headers).status_code == 401


def test_registration_rejects_duplicate_identity(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    body = {
        "name": "林工", "phone": "13900139000",
        "password": "Terminal123", "employee_no": "QC-101",
    }
    assert test_client.post("/api/v1/auth/register", json=body).status_code == 201
    assert test_client.post("/api/v1/auth/register", json=body).status_code == 409


def test_forgot_password_reset_revokes_sessions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DDOCR_EXPOSE_PASSWORD_RESET_CODE", "true")
    test_client = client(tmp_path)
    registration = test_client.post(
        "/api/v1/auth/register",
        json={
            "name": "找回用户", "phone": "13800138888",
            "password": "Original123", "employee_no": "QC-RESET",
        },
    ).json()["data"]
    old_headers = {"Authorization": f"Bearer {registration['access_token']}"}

    requested = test_client.post(
        "/api/v1/auth/forgot-password",
        json={"phone": "13800138888", "employee_no": "QC-RESET"},
    )
    assert requested.status_code == 202
    reset_data = requested.json()["data"]
    assert reset_data["expires_in"] == 600
    assert len(reset_data["development_code"]) == 6

    reset = test_client.post(
        "/api/v1/auth/reset-password",
        json={
            "phone": "13800138888", "code": reset_data["development_code"],
            "new_password": "Replacement456",
        },
    )
    assert reset.status_code == 204
    assert test_client.get("/api/v1/users/me", headers=old_headers).status_code == 401
    assert test_client.post(
        "/api/v1/auth/login", json={"phone": "13800138888", "password": "Original123"},
    ).status_code == 401
    assert test_client.post(
        "/api/v1/auth/login", json={"phone": "13800138888", "password": "Replacement456"},
    ).status_code == 200
    assert test_client.post(
        "/api/v1/auth/reset-password",
        json={"phone": "13800138888", "code": reset_data["development_code"], "new_password": "Again7890"},
    ).status_code == 400


def test_forgot_password_does_not_reveal_identity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DDOCR_EXPOSE_PASSWORD_RESET_CODE", "true")
    test_client = client(tmp_path)
    response = test_client.post(
        "/api/v1/auth/forgot-password",
        json={"phone": "13999999999", "employee_no": "UNKNOWN"},
    )
    assert response.status_code == 202
    assert response.json()["data"] == {
        "message": "如果账号信息匹配，重置验证码已生成",
        "expires_in": 600,
    }


def test_upload_job_and_results(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    job_id, headers = workflow(test_client)

    job_response = test_client.get(f"/api/v1/ocr/jobs/{job_id}", headers=headers)
    job = job_response.json()["data"]
    assert job["status"] == "succeeded"
    assert job["progress"] == 100

    file_response = test_client.get(f"/api/v1/files/{job['file_id']}", headers=headers)
    uploaded_file = file_response.json()["data"]
    assert uploaded_file["storage_path"].startswith("uploads/")
    assert uploaded_file["width_px"] == 1200
    assert uploaded_file["height_px"] == 1600

    content_response = test_client.get(
        f"/api/v1/files/{job['file_id']}/content",
        headers=headers,
    )
    assert content_response.status_code == 200
    assert content_response.headers["content-type"] == "image/png"

    results_response = test_client.get(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/results",
        headers=headers,
    )
    items = results_response.json()["data"]["items"]
    assert len(items) == 3
    assert len(items[0]["bbox"]) == 4
    assert 0 <= items[0]["confidence"] <= 1

    pages_response = test_client.get(f"/api/v1/ocr/jobs/{job_id}/pages", headers=headers)
    image = pages_response.json()["data"]["items"][0]["image"]
    assert image["url"] == f"/files/{job['file_id']}/content"
    assert image["width_px"] == 1200
    assert image["height_px"] == 1600


def test_correction_comment_and_export(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    job_id, headers = workflow(test_client)
    result_id = get_first_result(test_client, job_id, headers)["id"]

    correction_response = test_client.post(
        f"/api/v1/ocr/results/{result_id}/corrections",
        json={"corrected_text": "XT-102", "base_revision": 0},
        headers=headers,
    )
    assert correction_response.status_code == 201
    assert correction_response.json()["data"]["created_by"]["name"] == "复核员"

    conflict_response = test_client.post(
        f"/api/v1/ocr/results/{result_id}/corrections",
        json={"corrected_text": "bad", "base_revision": 0},
        headers=headers,
    )
    assert conflict_response.status_code == 409

    comment_response = test_client.post(
        f"/api/v1/ocr/results/{result_id}/comments",
        json={"content": "请复核"},
        headers=headers,
    )
    comment = comment_response.json()["data"]
    assert comment["comment_count"] == 1
    assert comment["author"]["name"] == "复核员"

    update_response = test_client.patch(
        f"/api/v1/ocr/results/{result_id}/comments/{comment['id']}",
        json={"content": "已经复核"},
        headers=headers,
    )
    assert update_response.json()["data"]["content"] == "已经复核"

    other_headers = register_headers(test_client, "13600136000", "QC-OTHER")
    forbidden = test_client.delete(
        f"/api/v1/ocr/results/{result_id}/comments/{comment['id']}",
        headers=other_headers,
    )
    # Cross-owner access is hidden as 404 before comment-author checks.
    assert forbidden.status_code == 404
    assert test_client.delete(
        f"/api/v1/ocr/results/{result_id}/comments/{comment['id']}",
        headers=headers,
    ).status_code == 204

    unauthenticated = test_client.post(
        f"/api/v1/ocr/results/{result_id}/comments",
        json={"content": "未登录"},
    )
    assert unauthenticated.status_code == 401

    export_response = test_client.post(
        f"/api/v1/ocr/jobs/{job_id}/exports",
        headers=headers,
        json={
            "format": "xlsx",
            "mode": "full",
            "scope": "all_pages",
        },
    )
    export_id = export_response.json()["data"]["id"]
    download_response = test_client.get(
        f"/api/v1/ocr/jobs/{job_id}/exports/{export_id}/download",
        headers=headers,
    )
    assert download_response.status_code == 200


def test_ocr_resources_are_isolated_by_owner(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    job_id, owner_headers = workflow(test_client)
    job = test_client.get(
        f"/api/v1/ocr/jobs/{job_id}", headers=owner_headers
    ).json()["data"]
    result_id = get_first_result(test_client, job_id, owner_headers)["id"]
    other_headers = register_headers(test_client, "13500135000", "QC-ISOLATED")

    assert test_client.get(
        "/api/v1/ocr/jobs", headers=other_headers
    ).json()["data"]["items"] == []
    assert test_client.get(
        f"/api/v1/files/{job['file_id']}", headers=other_headers
    ).status_code == 404
    assert test_client.get(
        f"/api/v1/files/{job['file_id']}/content", headers=other_headers
    ).status_code == 404
    assert test_client.get(
        f"/api/v1/ocr/jobs/{job_id}", headers=other_headers
    ).status_code == 404
    assert test_client.get(
        f"/api/v1/ocr/jobs/{job_id}/pages", headers=other_headers
    ).status_code == 404
    assert test_client.get(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/results", headers=other_headers
    ).status_code == 404
    assert test_client.get(
        f"/api/v1/ocr/results/{result_id}/comments", headers=other_headers
    ).status_code == 404
