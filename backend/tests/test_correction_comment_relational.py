from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app.main import create_app
from app.models.schema import comments, corrections
from app.models.store import StoredObject


def test_corrections_and_comments_use_relational_tables(tmp_path: Path) -> None:
    app = create_app(str(tmp_path), f"sqlite:///{(tmp_path / 'milestone5.db').as_posix()}")
    client = TestClient(app)
    auth = client.post("/api/v1/auth/register", json={
        "name": "复核用户", "phone": "13800135555",
        "password": "Review123", "employee_no": "REVIEW-001",
    }).json()["data"]
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    image = BytesIO()
    Image.new("RGB", (800, 600), "white").save(image, format="PNG")
    content = image.getvalue()
    file_id = client.post("/api/v1/files/upload-sessions", headers=headers, json={
        "file_name": "review.png", "size_bytes": len(content), "media_type": "image/png",
    }).json()["data"]["file_id"]
    client.put(f"/api/v1/files/{file_id}/content", headers=headers, content=content)
    client.post(f"/api/v1/files/{file_id}/complete", headers=headers)
    job_id = client.post("/api/v1/ocr/jobs", headers=headers, json={
        "name": "review job", "file_id": file_id,
        "model_id": "mock", "model_version": "1.0.0",
    }).json()["data"]["id"]
    result_id = client.get(
        f"/api/v1/ocr/jobs/{job_id}/pages/1/results", headers=headers
    ).json()["data"]["items"][0]["id"]

    correction = client.post(
        f"/api/v1/ocr/results/{result_id}/corrections", headers=headers,
        json={"corrected_text": "XT-102", "base_revision": 0},
    )
    assert correction.status_code == 201
    assert correction.json()["data"]["created_by"]["id"] == auth["user"]["id"]
    created = client.post(
        f"/api/v1/ocr/results/{result_id}/comments", headers=headers,
        json={"content": "请复核"},
    ).json()["data"]
    updated = client.patch(
        f"/api/v1/ocr/results/{result_id}/comments/{created['id']}", headers=headers,
        json={"content": "已经复核"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["content"] == "已经复核"

    with app.state.service.store.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(corrections)) == 1
        assert connection.scalar(select(func.count()).select_from(comments)) == 1
        legacy = connection.scalar(
            select(func.count()).select_from(StoredObject).where(
                StoredObject.kind.in_(["correction", "comment"])
            )
        )
        assert legacy == 0

    assert client.delete(
        f"/api/v1/ocr/results/{result_id}/comments/{created['id']}", headers=headers
    ).status_code == 204
    assert client.get(
        f"/api/v1/ocr/results/{result_id}/comments", headers=headers
    ).json()["data"]["items"] == []
