from pathlib import Path

from app.models.store import Store


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
