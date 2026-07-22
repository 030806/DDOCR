from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models.schema import sessions, users
from app.models.store import StoredObject


def test_authentication_uses_relational_tables(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'auth.db').as_posix()}"
    app = create_app(str(tmp_path), database_url)
    client = TestClient(app)

    registration = client.post("/api/v1/auth/register", json={
        "name": "关系表用户",
        "phone": "13800138888",
        "password": "Relational123",
        "employee_no": "DB-001",
    })
    assert registration.status_code == 201
    token = registration.json()["data"]["access_token"]

    with app.state.service.store.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(users)) == 1
        assert connection.scalar(select(func.count()).select_from(sessions)) == 1
        auth_objects = connection.scalar(
            select(func.count()).select_from(StoredObject).where(
                StoredObject.kind.in_(["user", "session"])
            )
        )
        assert auth_objects == 0

    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/users/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/users/me", headers=headers).status_code == 401
