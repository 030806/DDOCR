from pathlib import Path
import sqlite3

from app.models.store import Store


def test_store_adds_review_status_to_legacy_sqlite_results(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE results (id VARCHAR(36) PRIMARY KEY)")
        connection.execute("INSERT INTO results (id) VALUES ('result-1')")

    store = Store(tmp_path, f"sqlite:///{database_path.as_posix()}")
    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(results)")}
        status = connection.execute("SELECT review_status FROM results WHERE id = 'result-1'").fetchone()[0]
    assert "review_status" in columns
    assert "geometry_revision" in columns
    assert status == "unreviewed"
    store.engine.dispose()


def test_store_upserts_and_separates_object_kinds(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'store.db').as_posix()}"
    store = Store(tmp_path, database_url)

    store.put("job", "same-id", {"id": "same-id", "status": "queued"})
    store.put("file", "same-id", {"id": "same-id", "name": "input.png"})
    store.put("job", "same-id", {"id": "same-id", "status": "succeeded"})

    assert store.get("job", "same-id") == {
        "id": "same-id",
        "status": "succeeded",
    }
    assert store.get("file", "same-id") == {
        "id": "same-id",
        "name": "input.png",
    }
    assert store.all("job") == [{"id": "same-id", "status": "succeeded"}]
    store.engine.dispose()
