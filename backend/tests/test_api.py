from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image
from openpyxl import load_workbook

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


def upload_image(test_client: TestClient, headers: dict[str, str]) -> str:
    image_buffer = BytesIO()
    Image.new("RGB", (1200, 1600), "white").save(image_buffer, format="PNG")
    content = image_buffer.getvalue()
    upload = test_client.post(
        "/api/v1/files/upload-sessions", headers=headers,
        json={"file_name": "region.png", "size_bytes": len(content), "media_type": "image/png"},
    ).json()["data"]
    test_client.put(f"/api/v1/files/{upload['file_id']}/content", headers=headers, content=content)
    test_client.post(f"/api/v1/files/{upload['file_id']}/complete", headers=headers)
    return upload["file_id"]


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


def test_region_job_from_uploaded_file_is_independent(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    headers = register_headers(test_client)
    file_id = upload_image(test_client, headers)
    response = test_client.post(
        "/api/v1/ocr/region-jobs", headers=headers,
        json={
            "name": "局部识别", "file_id": file_id,
            "model_id": "mock", "model_version": "1.0.0",
            "pages": [{"page_no": 1, "regions": [
                {"client_id": "roi-b", "bbox": [500, 600, 900, 820]},
                {"client_id": "roi-a", "bbox": [100, 120, 400, 300]},
            ]}],
        },
    )
    assert response.status_code == 202
    job_id = response.json()["data"]["id"]
    assert wait_for_job(test_client, job_id, headers)["status"] == "succeeded"
    context = test_client.get(
        f"/api/v1/ocr/region-jobs/{job_id}/context", headers=headers,
    ).json()["data"]
    assert context["source_job_id"] is None
    assert context["region_count"] == 2
    results = test_client.get(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/results", headers=headers,
    ).json()["data"]["items"]
    assert len(results) == 2
    assert results[0]["bbox"] == [102.0, 122.0, 398.0, 298.0]
    assert results[1]["bbox"] == [502.0, 602.0, 898.0, 818.0]
    assert results[0]["attributes"]["source"] == "region_ocr"


def test_region_job_can_derive_from_completed_job_without_changing_it(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    source_job_id, headers = workflow(test_client)
    source_before = test_client.get(
        f"/api/v1/ocr/jobs/{source_job_id}/pages/1/results", headers=headers,
    ).json()["data"]["items"]
    response = test_client.post(
        "/api/v1/ocr/region-jobs", headers=headers,
        json={
            "name": "派生区域识别", "source_job_id": source_job_id,
            "model_id": "mock", "model_version": "1.0.0",
            "pages": [{"page_no": 1, "regions": [
                {"client_id": "roi-derived", "bbox": [50, 50, 500, 500]},
            ]}],
        },
    )
    assert response.status_code == 202
    derived_job_id = response.json()["data"]["id"]
    wait_for_job(test_client, derived_job_id, headers)
    context = test_client.get(
        f"/api/v1/ocr/region-jobs/{derived_job_id}/context", headers=headers,
    ).json()["data"]
    assert context["source_job_id"] == source_job_id
    source_after = test_client.get(
        f"/api/v1/ocr/jobs/{source_job_id}/pages/1/results", headers=headers,
    ).json()["data"]["items"]
    assert source_after == source_before


def test_illumination_is_saved_for_region_job_and_inherited_on_rerun(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    headers = register_headers(test_client)
    file_id = upload_image(test_client, headers)
    response = test_client.post(
        "/api/v1/ocr/region-jobs", headers=headers,
        json={
            "name": "HE 选区", "file_id": file_id,
            "model_id": "mock", "model_version": "1.0.0", "illumination": "he",
            "pages": [{"page_no": 1, "regions": [
                {"client_id": "roi-1", "bbox": [100, 120, 400, 300]},
            ]}],
        },
    )
    assert response.status_code == 202
    source_id = response.json()["data"]["id"]
    wait_for_job(test_client, source_id, headers)
    source = test_client.get(f"/api/v1/ocr/jobs/{source_id}", headers=headers).json()["data"]
    assert source["options"]["illumination"] == "he"

    rerun = test_client.post(
        f"/api/v1/ocr/jobs/{source_id}/rerun", headers=headers,
        json={"model_id": "mock", "model_version": "1.0.0"},
    )
    assert rerun.status_code == 202
    rerun_id = rerun.json()["data"]["id"]
    wait_for_job(test_client, rerun_id, headers)
    rerun_job = test_client.get(f"/api/v1/ocr/jobs/{rerun_id}", headers=headers).json()["data"]
    assert rerun_job["options"]["illumination"] == "he"
    source_context = test_client.get(
        f"/api/v1/ocr/region-jobs/{source_id}/context", headers=headers,
    ).json()["data"]
    rerun_context = test_client.get(
        f"/api/v1/ocr/region-jobs/{rerun_id}/context", headers=headers,
    ).json()["data"]
    assert [region["bbox"] for region in rerun_context["regions"]] == [
        region["bbox"] for region in source_context["regions"]
    ]

    overridden = test_client.post(
        f"/api/v1/ocr/jobs/{rerun_id}/rerun", headers=headers,
        json={"model_id": "mock", "model_version": "1.0.0", "illumination": "clahe"},
    )
    assert overridden.status_code == 202
    override_id = overridden.json()["data"]["id"]
    wait_for_job(test_client, override_id, headers)
    override_job = test_client.get(f"/api/v1/ocr/jobs/{override_id}", headers=headers).json()["data"]
    assert override_job["options"]["illumination"] == "clahe"
    override_context = test_client.get(
        f"/api/v1/ocr/region-jobs/{override_id}/context", headers=headers,
    ).json()["data"]
    assert [region["bbox"] for region in override_context["regions"]] == [
        region["bbox"] for region in source_context["regions"]
    ]


def test_region_job_rejects_invalid_source_and_bbox(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    headers = register_headers(test_client)
    file_id = upload_image(test_client, headers)
    base = {
        "name": "非法区域", "file_id": file_id,
        "model_id": "mock", "model_version": "1.0.0",
    }
    too_small = test_client.post(
        "/api/v1/ocr/region-jobs", headers=headers,
        json={**base, "pages": [{"page_no": 1, "regions": [
            {"client_id": "small", "bbox": [10, 10, 20, 20]},
        ]}]},
    )
    assert too_small.status_code == 422
    both_sources = test_client.post(
        "/api/v1/ocr/region-jobs", headers=headers,
        json={**base, "source_job_id": "also-set", "pages": [{"page_no": 1, "regions": [
            {"client_id": "valid", "bbox": [10, 10, 100, 100]},
        ]}]},
    )
    assert both_sources.status_code == 422


def test_upload_session_advertises_200_mib_limit(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    headers = register_headers(test_client)
    response = test_client.post(
        "/api/v1/files/upload-sessions",
        headers=headers,
        json={"file_name": "large.png", "size_bytes": 150 * 1024 * 1024, "media_type": "image/png"},
    )
    assert response.status_code == 201
    assert response.json()["data"]["max_size_bytes"] == 200 * 1024 * 1024


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


def test_simplified_registration_and_single_use_captcha(tmp_path: Path) -> None:
    import base64
    import re

    test_client = client(tmp_path)
    registration = test_client.post("/api/v1/auth/register", json={
        "name": "精简注册用户", "phone": "13800139991", "password": "Simple123",
    })
    assert registration.status_code == 201
    assert registration.json()["data"]["user"]["employee_no"].startswith("USR-")

    captcha = test_client.get("/api/v1/auth/captcha")
    assert captcha.status_code == 200
    challenge = captcha.json()["data"]
    assert challenge["image"].startswith("data:image/svg+xml;base64,")
    svg = base64.b64decode(challenge["image"].split(",", 1)[1]).decode()
    code = re.search(r">([A-Z2-9]{4})</text>", svg).group(1)
    payload = {"captcha_id": challenge["captcha_id"], "code": code.lower()}
    assert test_client.post("/api/v1/auth/captcha/verify", json=payload).status_code == 200
    assert test_client.post("/api/v1/auth/captcha/verify", json=payload).status_code == 400


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
        json={"phone": "13800138888"},
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
        json={"phone": "13999999999"},
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


def test_review_status_is_persisted_and_excluded_from_export(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    job_id, headers = workflow(test_client)
    results_response = test_client.get(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/results", headers=headers,
    )
    items = results_response.json()["data"]["items"]
    assert all(item["review_status"] == "unreviewed" for item in items)

    false_positive_id, deleted_id = items[0]["id"], items[1]["id"]
    marked = test_client.post(
        "/api/v1/ocr/results/review-status", headers=headers,
        json={"result_ids": [false_positive_id], "review_status": "false_positive"},
    )
    deleted = test_client.post(
        "/api/v1/ocr/results/review-status", headers=headers,
        json={"result_ids": [deleted_id], "review_status": "deleted"},
    )
    assert marked.json()["data"]["updated_count"] == 1
    assert deleted.json()["data"]["updated_count"] == 1

    export = test_client.post(
        f"/api/v1/ocr/jobs/{job_id}/exports", headers=headers,
        json={"format": "xlsx", "mode": "simple", "scope": "all_pages"},
    ).json()["data"]
    download = test_client.get(
        f"/api/v1/ocr/jobs/{job_id}/exports/{export['id']}/download", headers=headers,
    )
    workbook = load_workbook(BytesIO(download.content), read_only=True)
    rows = list(workbook.active.iter_rows(values_only=True))
    assert len(rows) == 2  # header plus the one remaining effective result

    restored = test_client.post(
        "/api/v1/ocr/results/review-status", headers=headers,
        json={"result_ids": [false_positive_id, deleted_id], "review_status": "unreviewed"},
    )
    assert restored.json()["data"]["updated_count"] == 2


def test_result_table_fields_persist_and_reject_stale_revision(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    job_id, headers = workflow(test_client)
    url = f"/api/v1/ocr/jobs/{job_id}/pages/1/results"
    item = test_client.get(url, headers=headers).json()["data"]["items"][0]
    assert item["terminal_number"] == ""
    assert item["manual_confirmed"] is False
    path = f"/api/v1/ocr/results/{item['id']}/table"
    payload = {"terminal_number": "X1", "manual_confirmed": True, "table_note": "已核对", "base_revision": 0}
    saved = test_client.patch(path, headers=headers, json=payload)
    assert saved.status_code == 200
    assert saved.json()["data"]["table_revision"] == 1
    reloaded = test_client.get(url, headers=headers).json()["data"]["items"][0]
    assert (reloaded["terminal_number"], reloaded["manual_confirmed"], reloaded["table_note"]) == ("X1", True, "已核对")
    assert test_client.patch(path, headers=headers, json=payload).status_code == 409


def test_batch_result_geometry_edits_update_create_and_delete(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    job_id, headers = workflow(test_client)
    before = test_client.get(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/results", headers=headers,
    ).json()["data"]["items"]
    updated_id, deleted_id = before[0]["id"], before[1]["id"]
    response = test_client.post(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/result-edits", headers=headers,
        json={
            "updates": [{
                "result_id": updated_id, "bbox": [20, 30, 240, 100],
                "polygon": [[25, 30], [240, 35], [235, 100], [20, 95]], "base_revision": 0,
            }],
            "creates": [{
                "client_id": "draft-1", "bbox": [300, 300, 500, 360],
                "polygon": [[305, 300], [500, 305], [495, 360], [300, 355]], "text": "MANUAL-X1",
            }],
            "deletes": [{"result_id": deleted_id}],
        },
    )
    assert response.status_code == 200
    saved = response.json()["data"]
    assert saved["updated"][0]["bbox"] == [20.0, 30.0, 240.0, 100.0]
    assert saved["updated"][0]["polygon"] == [[25.0, 30.0], [240.0, 35.0], [235.0, 100.0], [20.0, 95.0]]
    assert saved["created"][0]["client_id"] == "draft-1"
    assert saved["deleted"] == [deleted_id]

    after = test_client.get(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/results", headers=headers,
    ).json()["data"]["items"]
    updated = next(item for item in after if item["id"] == updated_id)
    manual = next(item for item in after if item["text"] == "MANUAL-X1")
    deleted = next(item for item in after if item["id"] == deleted_id)
    assert updated["bbox"] == [20.0, 30.0, 240.0, 100.0]
    assert updated["polygon"] == [[25.0, 30.0], [240.0, 35.0], [235.0, 100.0], [20.0, 95.0]]
    assert updated["geometry_revision"] == 1
    assert manual["attributes"]["source"] == "manual"
    assert manual["polygon"] == [[305.0, 300.0], [500.0, 305.0], [495.0, 360.0], [300.0, 355.0]]
    assert deleted["review_status"] == "deleted"

    conflict = test_client.post(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/result-edits", headers=headers,
        json={"updates": [{"result_id": updated_id, "bbox": [25, 30, 245, 100], "base_revision": 0}]},
    )
    assert conflict.status_code == 409


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


def test_delete_job_persists_and_is_owner_scoped(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    job_id, owner_headers = workflow(test_client)
    other_headers = register_headers(test_client, "13500135001", "QC-DELETE")

    assert test_client.delete(
        f"/api/v1/ocr/jobs/{job_id}", headers=other_headers
    ).status_code == 404
    assert test_client.delete(
        f"/api/v1/ocr/jobs/{job_id}", headers=owner_headers
    ).status_code == 204

    assert test_client.get(
        f"/api/v1/ocr/jobs/{job_id}", headers=owner_headers
    ).status_code == 404
    listed = test_client.get("/api/v1/ocr/jobs", headers=owner_headers)
    assert all(item["id"] != job_id for item in listed.json()["data"]["items"])

    stored = test_client.app.state.service.jobs.get(job_id)
    assert stored is not None
    assert stored["deleted"] is True


def test_rerun_job_reuses_file_and_hides_source_from_default_list(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    source_job_id, owner_headers = workflow(test_client)
    other_headers = register_headers(test_client, "13500135002", "QC-RERUN")
    source_before = test_client.app.state.service.jobs.get(source_job_id)

    assert test_client.post(
        f"/api/v1/ocr/jobs/{source_job_id}/rerun",
        headers=other_headers,
        json={"model_id": "mock", "model_version": "1.0.0"},
    ).status_code == 404

    response = test_client.post(
        f"/api/v1/ocr/jobs/{source_job_id}/rerun",
        headers=owner_headers,
        json={"model_id": "mock", "model_version": "1.0.0"},
    )
    assert response.status_code == 202
    rerun_job_id = response.json()["data"]["id"]
    wait_for_job(test_client, rerun_job_id, owner_headers)

    source_after = test_client.app.state.service.jobs.get(source_job_id)
    rerun = test_client.app.state.service.jobs.get(rerun_job_id)
    assert source_after is not None and rerun is not None and source_before is not None
    assert rerun["file_id"] == source_before["file_id"]
    assert rerun["options"]["rerun_source_job_id"] == source_job_id
    assert source_after["options"]["superseded_by_job_id"] == rerun_job_id
    assert test_client.get(
        f"/api/v1/ocr/jobs/{source_job_id}", headers=owner_headers,
    ).status_code == 200

    listed = test_client.get("/api/v1/ocr/jobs", headers=owner_headers).json()["data"]["items"]
    assert [item["id"] for item in listed] == [rerun_job_id]
    assert test_client.post(
        f"/api/v1/ocr/jobs/{source_job_id}/rerun",
        headers=owner_headers,
        json={"model_id": "mock", "model_version": "1.0.0"},
    ).status_code == 409


def test_terminal_record_is_bound_editable_and_idempotent(tmp_path):
    test_client = client(tmp_path)
    job_id, headers = workflow(test_client)
    response = test_client.put(f"/api/v1/ocr/jobs/{job_id}/pages/1/terminal-points", headers=headers,
                               json={"base_revision": 0, "points": [{"id": "draft", "x": 100, "y": 100}]})
    assert response.status_code == 200
    point_id = response.json()["data"]["points"][0]["id"]
    url = f"/api/v1/ocr/jobs/{job_id}/pages/1/terminal-records/{point_id}"
    first = test_client.put(url, headers=headers)
    assert first.status_code == 200
    result_id = first.json()["data"]["id"]
    assert test_client.put(url, headers=headers).json()["data"]["id"] == result_id
    assert test_client.put(url.replace(point_id, "missing"), headers=headers).status_code == 404
    saved = test_client.patch(f"/api/v1/ocr/results/{result_id}/table", headers=headers,
                             json={"terminal_number": "X1", "table_note": "人工补录", "manual_confirmed": True, "base_revision": 0})
    assert saved.status_code == 200
    correction = test_client.post(f"/api/v1/ocr/results/{result_id}/corrections", headers=headers,
                                  json={"corrected_text": "CABLE-1", "base_revision": 0})
    assert correction.status_code == 201
    rows = test_client.get(f"/api/v1/ocr/jobs/{job_id}/pages/1/results", headers=headers).json()["data"]["items"]
    records = [r for r in rows if r["attributes"].get("terminal_point_id") == point_id]
    assert len(records) == 1
    assert records[0]["display_text"] == "CABLE-1"
    assert records[0]["table_note"] == "人工补录"


def test_terminal_document_isolates_values_and_atomically_corrects_source(tmp_path):
    from copy import deepcopy
    test_client = client(tmp_path)
    job_id, headers = workflow(test_client)
    prefix = f"/api/v1/ocr/jobs/{job_id}/pages/1"
    points = test_client.put(prefix + "/terminal-points", headers=headers,
                            json={"base_revision": 0, "points": [{"id": "draft", "x": 100, "y": 100}, {"id": "other", "x": 100, "y": 1200}]})
    assert points.status_code == 200
    original = test_client.get(prefix + "/results", headers=headers).json()["data"]["items"]
    document = test_client.get(prefix + "/terminal-document", headers=headers).json()["data"]
    assert len(document["records"]) >= 2
    baseline = deepcopy(document["records"])
    record = next(r for r in document["records"] if r["sourceResultId"])
    source = next(r for r in original if r["id"] == record["sourceResultId"])
    record["cable"] = "BUSINESS-ONLY"
    record["manual"] = True
    record["manualConfirmed"] = True
    saved = test_client.put(prefix + "/terminal-document", headers=headers,
                            json={"base_revision": 0, "records": document["records"]})
    assert saved.status_code == 200
    assert test_client.get(prefix + "/results", headers=headers).json()["data"]["items"] == original
    export = test_client.post(f"/api/v1/ocr/jobs/{job_id}/exports", headers=headers,
                             json={"format": "xlsx", "mode": "simple", "scope": "all_pages"}).json()["data"]
    download = test_client.get(f"/api/v1/ocr/jobs/{job_id}/exports/{export['id']}/download", headers=headers)
    workbook = load_workbook(BytesIO(download.content), read_only=True)
    assert any(row[2] == "BUSINESS-ONLY" for row in workbook["端子对照表"].iter_rows(min_row=2, values_only=True))
    independent = test_client.put(prefix + "/terminal-document", headers=headers, json={
        "base_revision": 1, "records": saved.json()["data"]["records"],
        "source": {"result_id": source["id"], "base_revision": source["revision"], "text": "SOURCE-ONLY"}})
    assert independent.status_code == 200
    assert next(r for r in independent.json()["data"]["records"] if r["id"] == record["id"])["cable"] == "BUSINESS-ONLY"
    synced = test_client.put(prefix + "/terminal-document", headers=headers, json={
        "base_revision": 2, "records": independent.json()["data"]["records"], "sync_record_id": record["id"],
        "source": {"result_id": source["id"], "base_revision": source["revision"] + 1, "text": "BOTH"}})
    assert synced.status_code == 200
    current = synced.json()["data"]
    row = next(r for r in current["records"] if r["id"] == record["id"])
    assert row["cable"] == "BOTH" and row["manualConfirmed"] is False
    bad = deepcopy(current["records"])
    bad[0]["cable"] = "MUST-ROLLBACK"
    conflict = test_client.put(prefix + "/terminal-document", headers=headers, json={
        "base_revision": 3, "records": bad,
        "source": {"result_id": source["id"], "base_revision": 0, "text": "BAD"}})
    assert conflict.status_code == 409
    reloaded = test_client.get(prefix + "/terminal-document", headers=headers).json()["data"]
    assert reloaded["revision"] == 3
    assert reloaded["records"][0]["cable"] != "MUST-ROLLBACK"
    # Undo a whole source operation with another versioned correction; history is retained.
    undone = test_client.put(prefix + "/terminal-document", headers=headers, json={
        "base_revision": 3, "records": independent.json()["data"]["records"],
        "source": {"result_id": source["id"], "base_revision": source["revision"] + 2, "text": "SOURCE-ONLY"}})
    assert undone.status_code == 200
    assert next(r for r in undone.json()["data"]["records"] if r["id"] == record["id"])["cable"] == "BUSINESS-ONLY"
    assert len(test_client.get(prefix + "/results", headers=headers).json()["data"]["items"]) == len(original)
    # Editing and undoing a previously empty business row never creates OCR evidence.
    restored = test_client.put(prefix + "/terminal-document", headers=headers,
                              json={"base_revision": 4, "records": baseline})
    assert restored.status_code == 200
    assert len(test_client.get(prefix + "/results", headers=headers).json()["data"]["items"]) == len(original)


def test_list_correction_follows_only_unedited_business_and_keeps_value_after_source_deletion(tmp_path):
    api = client(tmp_path)
    job, headers = workflow(api)
    prefix = f"/api/v1/ocr/jobs/{job}/pages/1"
    api.put(prefix + "/terminal-points", headers=headers, json={"base_revision": 0, "points": [{"id": "p", "x": 100, "y": 100}]})
    doc = api.get(prefix + "/terminal-document", headers=headers).json()["data"]
    source_id = doc["records"][0]["sourceResultId"]
    source = next(r for r in api.get(prefix + "/results", headers=headers).json()["data"]["items"] if r["id"] == source_id)
    response = api.post(f"/api/v1/ocr/results/{source_id}/corrections", headers=headers,
                        json={"base_revision": source["revision"], "corrected_text": "LIST-CORRECTED"})
    assert response.status_code == 201
    followed = api.get(prefix + "/terminal-document", headers=headers).json()["data"]
    assert followed["records"][0]["cable"] == "LIST-CORRECTED"
    assert followed["revision"] > doc["revision"]
    api.post("/api/v1/ocr/results/review-status", headers=headers,
              json={"result_ids": [source_id], "review_status": "deleted"})
    after = api.get(prefix + "/terminal-document", headers=headers).json()["data"]
    assert after["records"][0]["cable"] == "LIST-CORRECTED"
    assert after["records"][0]["sourceUnavailable"] is True


def test_business_cut_moves_source_association_and_undo_restores_it(tmp_path):
    from copy import deepcopy
    api = client(tmp_path)
    job, headers = workflow(api)
    prefix = f"/api/v1/ocr/jobs/{job}/pages/1"
    api.put(prefix + "/terminal-points", headers=headers, json={"base_revision": 0, "points": [
        {"id": "p", "x": 100, "y": 100}, {"id": "q", "x": 100, "y": 1500}]})
    doc = api.get(prefix + "/terminal-document", headers=headers).json()["data"]
    original = deepcopy(doc["records"])
    source = next(r for r in doc["records"] if r["sourceResultId"])
    target = next(r for r in doc["records"] if r["id"] != source["id"])
    source_id, target_id, ocr_id, cable = source["id"], target["id"], source["sourceResultId"], source["cable"]
    target.update(cable=cable, sourceResultId=ocr_id, sourceRevision=source["sourceRevision"], manual=True, manualConfirmed=False)
    source.update(cable="", sourceResultId=None, sourceRevision=0, manual=True, manualConfirmed=False)
    moved = api.put(prefix + "/terminal-document", headers=headers, json={"base_revision": doc["revision"], "records": doc["records"]})
    assert moved.status_code == 200
    saved = moved.json()["data"]
    assert next(r for r in saved["records"] if r["id"] == source_id)["sourceResultId"] is None
    assert next(r for r in saved["records"] if r["id"] == target_id)["sourceResultId"] == ocr_id
    undone = api.put(prefix + "/terminal-document", headers=headers, json={"base_revision": saved["revision"], "records": original})
    assert undone.status_code == 200
    assert next(r for r in undone.json()["data"]["records"] if r["id"] == source_id)["sourceResultId"] == ocr_id
    bad = deepcopy(undone.json()["data"])
    bad["records"][0]["sourceResultId"] = "other-page-result"
    assert api.put(prefix + "/terminal-document", headers=headers,
                   json={"base_revision": bad["revision"], "records": bad["records"]}).status_code == 422
