import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.uploads = root / "uploads"
        self.exports = root / "exports"
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.exports.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / "mock.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = RLock()
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS objects(
                kind TEXT NOT NULL,
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_objects_kind ON objects(kind);
            """
        )

    def put(
        self,
        kind: str,
        ident: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        serialized_data = json.dumps(data, ensure_ascii=False)
        with self.lock, self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO objects VALUES(?,?,?)",
                (kind, ident, serialized_data),
            )
        return data

    def get(self, kind: str, ident: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT data FROM objects WHERE kind=? AND id=?",
            (kind, ident),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def all(self, kind: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT data FROM objects WHERE kind=?",
            (kind,),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]
