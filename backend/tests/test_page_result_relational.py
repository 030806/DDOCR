from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app.main import create_app
from app.models.schema import pages, results
from app.models.store import StoredObject


def test_complete_ocr_pipeline_uses_relational_page_and_result_tables(tmp_path: Path) -> None:
    app = create_app(str(tmp_path), f"sqlite:///{(tmp_path / 'milestone4.db').as_posix()}")
    client = TestClient(app)
    registration = client.post("/api/v1/auth/register", json={
        "name": "OCR 用户", "phone": "13800136666",
        "password": "Pages123", "employee_no": "PAGE-001",
    })
    headers = {"Authorization": f"Bearer {registration.json()['data']['access_token']}"}
    image = BytesIO()
    Image.new("RGB", (800, 600), "white").save(image, format="PNG")
    content = image.getvalue()
    file_id = client.post("/api/v1/files/upload-sessions", headers=headers, json={
        "file_name": "ocr.png", "size_bytes": len(content), "media_type": "image/png",
    }).json()["data"]["file_id"]
    client.put(f"/api/v1/files/{file_id}/content", headers=headers, content=content)
    client.post(f"/api/v1/files/{file_id}/complete", headers=headers)
    job_id = client.post("/api/v1/ocr/jobs", headers=headers, json={
        "name": "page result job", "file_id": file_id,
        "model_id": "mock", "model_version": "1.0.0",
    }).json()["data"]["id"]

    response = client.get(f"/api/v1/ocr/jobs/{job_id}/pages/1/results", headers=headers)
    assert response.status_code == 200
    assert len(response.json()["data"]["items"]) == 3
    with app.state.service.store.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(pages)) == 1
        assert connection.scalar(select(func.count()).select_from(results)) == 3
        legacy = connection.scalar(
            select(func.count()).select_from(StoredObject).where(
                StoredObject.kind.in_(["file", "job", "page", "result"])
            )
        )
        assert legacy == 0
