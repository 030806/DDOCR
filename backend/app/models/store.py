from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Index, String, create_engine, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class StoredObject(Base):
    __tablename__ = "objects"
    __table_args__ = (Index("ix_objects_kind", "kind"),)

    kind: Mapped[str] = mapped_column(String(64), primary_key=True)
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class Store:
    def __init__(self, root: Path, database_url: str) -> None:
        self.root = root
        self.uploads = root / "uploads"
        self.exports = root / "exports"
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.exports.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
        # SQLite is used only for isolated local/test instances. PostgreSQL
        # schemas are always managed explicitly through Alembic.
        if self.engine.dialect.name == "sqlite":
            Base.metadata.create_all(self.engine)

    def put(
        self,
        kind: str,
        ident: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        with Session(self.engine) as session, session.begin():
            if self.engine.dialect.name == "postgresql":
                statement = postgresql_insert(StoredObject).values(
                    kind=kind, id=ident, data=data
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[StoredObject.kind, StoredObject.id],
                    set_={"data": statement.excluded.data},
                )
                session.execute(statement)
            else:
                existing = session.get(StoredObject, (kind, ident))
                if existing:
                    existing.data = data
                else:
                    session.add(StoredObject(kind=kind, id=ident, data=data))
        return data

    def get(self, kind: str, ident: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = session.get(StoredObject, (kind, ident))
            return dict(row.data) if row else None

    def all(self, kind: str) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(StoredObject).where(StoredObject.kind == kind)
            ).all()
            return [dict(row.data) for row in rows]
