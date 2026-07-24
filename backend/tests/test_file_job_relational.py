from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app.main import create_app
from app.models.schema import files, ocr_jobs
from app.models.store import StoredObject
from tests.ocr_fakes import FakeOcrAdapter, wait_for_job


def test_files_and_jobs_use_only_relational_tables(tmp_path: Path) -> None:
    app = create_app(str(tmp_path), f"sqlite:///{(tmp_path / 'milestone3.db').as_posix()}", FakeOcrAdapter())
    client = TestClient(app)
    registration = client.post("/api/v1/auth/register", json={
        "name": "文件用户", "phone": "13800137777",
        "password": "Files123", "employee_no": "FILE-001",
    })
    headers = {"Authorization": f"Bearer {registration.json()['data']['access_token']}"}

    image = BytesIO()
    Image.new("RGB", (640, 480), "white").save(image, format="PNG")
    content = image.getvalue()
    upload = client.post("/api/v1/files/upload-sessions", headers=headers, json={
        "file_name": "terminal.png", "size_bytes": len(content), "media_type": "image/png",
    }).json()["data"]
    file_id = upload["file_id"]
    assert client.put(f"/api/v1/files/{file_id}/content", headers=headers, content=content).status_code == 200
    assert client.post(f"/api/v1/files/{file_id}/complete", headers=headers).status_code == 200
    job_response = client.post("/api/v1/ocr/jobs", headers=headers, json={
        "name": "relation job", "file_id": file_id,
        "model_id": "mock", "model_version": "1.0.0",
    })
    assert job_response.status_code == 202
    wait_for_job(client, job_response.json()["data"]["id"], headers)

    with app.state.service.store.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(files)) == 1
        assert connection.scalar(select(func.count()).select_from(ocr_jobs)) == 1
        legacy_count = connection.scalar(
            select(func.count()).select_from(StoredObject).where(
                StoredObject.kind.in_(["file", "job"])
            )
        )
        assert legacy_count == 0
