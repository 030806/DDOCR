"""SQLAlchemy repositories for the relational authentication subsystem."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, insert, select, update
from sqlalchemy.orm import Session

from app.models.schema import password_reset_tokens, sessions, tenants, users

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_TENANT_SLUG = "default"


def _legacy_timestamp(value: datetime | str | None) -> str | None:
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _database_timestamp(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _user_dict(row: Any) -> dict[str, Any]:
    mapping = row._mapping if hasattr(row, "_mapping") else row
    return {
        "id": mapping["id"],
        "name": mapping["name"],
        "email": mapping["email"] or "",
        "phone": mapping["phone"] or "",
        "employee_no": mapping["employee_no"] or "",
        "department": mapping["department"] or "",
        "password_salt": mapping["password_salt"],
        "password_hash": mapping["password_hash"],
        "role_names": mapping["role_names"] or [],
        "permissions": mapping["permissions"] or [],
        "avatar_url": mapping["avatar_url"],
        "created_at": _legacy_timestamp(mapping["created_at"]),
        "last_login_at": _legacy_timestamp(mapping["last_login_at"]),
        "deleted": mapping["deleted_at"] is not None or mapping["status"] == "disabled",
    }


class TenantRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def ensure_default(self) -> str:
        with Session(self.engine) as db, db.begin():
            tenant_id = db.scalar(
                select(tenants.c.id).where(tenants.c.slug == DEFAULT_TENANT_SLUG)
            )
            if tenant_id:
                return tenant_id
            db.execute(insert(tenants).values(
                id=DEFAULT_TENANT_ID,
                name="DDOCR",
                slug=DEFAULT_TENANT_SLUG,
                status="active",
                settings={},
            ))
            return DEFAULT_TENANT_ID


class UserRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        return self._find(users.c.email == email)

    def find_by_phone(self, phone: str) -> dict[str, Any] | None:
        return self._find(users.c.phone == phone)

    def find_by_employee_no(self, employee_no: str) -> dict[str, Any] | None:
        return self._find(users.c.employee_no == employee_no)

    def get(self, user_id: str) -> dict[str, Any] | None:
        return self._find(users.c.id == user_id)

    def _find(self, condition: Any) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            row = db.execute(select(users).where(condition)).first()
            return _user_dict(row) if row else None

    def create(self, tenant_id: str, user: dict[str, Any]) -> dict[str, Any]:
        with Session(self.engine) as db, db.begin():
            db.execute(insert(users).values(
                id=user["id"], tenant_id=tenant_id, name=user["name"],
                email=user.get("email") or None, phone=user["phone"],
                employee_no=user["employee_no"], department=user.get("department", ""),
                password_salt=user["password_salt"], password_hash=user["password_hash"],
                role_names=user["role_names"], permissions=user["permissions"],
                avatar_url=user.get("avatar_url"), status="active",
                created_at=_database_timestamp(user["created_at"]),
                last_login_at=_database_timestamp(user.get("last_login_at")),
            ))
        return user

    def update(self, user_id: str, values: dict[str, Any]) -> None:
        allowed = {
            "name", "department", "phone", "password_salt", "password_hash",
            "last_login_at", "role_names", "permissions", "avatar_url",
        }
        changes = {key: value for key, value in values.items() if key in allowed}
        if "last_login_at" in changes:
            changes["last_login_at"] = _database_timestamp(changes["last_login_at"])
        changes["updated_at"] = datetime.now(UTC)
        with Session(self.engine) as db, db.begin():
            db.execute(update(users).where(users.c.id == user_id).values(**changes))


class SessionRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, token: str, user_id: str, created_at: str) -> None:
        with Session(self.engine) as db, db.begin():
            db.execute(insert(sessions).values(
                token=token, user_id=user_id, created_at=_database_timestamp(created_at)
            ))

    def user_id_for_active_token(self, token: str) -> str | None:
        with Session(self.engine) as db:
            return db.scalar(
                select(sessions.c.user_id).where(
                    sessions.c.token == token,
                    sessions.c.revoked_at.is_(None),
                    (sessions.c.expires_at.is_(None) | (sessions.c.expires_at > datetime.now(UTC))),
                )
            )

    def revoke(self, token: str) -> None:
        with Session(self.engine) as db, db.begin():
            db.execute(
                update(sessions)
                .where(sessions.c.token == token, sessions.c.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )

    def revoke_all_for_user(self, user_id: str) -> None:
        with Session(self.engine) as db, db.begin():
            db.execute(
                update(sessions)
                .where(sessions.c.user_id == user_id, sessions.c.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )


class PasswordResetRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, token_id: str, user_id: str, code_hash: str, expires_at: datetime) -> None:
        with Session(self.engine) as db, db.begin():
            db.execute(
                update(password_reset_tokens)
                .where(password_reset_tokens.c.user_id == user_id, password_reset_tokens.c.used_at.is_(None))
                .values(used_at=datetime.now(UTC))
            )
            db.execute(insert(password_reset_tokens).values(
                id=token_id, user_id=user_id, code_hash=code_hash, expires_at=expires_at,
            ))

    def latest_active(self, user_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            row = db.execute(
                select(password_reset_tokens)
                .where(password_reset_tokens.c.user_id == user_id, password_reset_tokens.c.used_at.is_(None))
                .order_by(password_reset_tokens.c.created_at.desc())
                .limit(1)
            ).first()
            return dict(row._mapping) if row else None

    def increment_attempts(self, token_id: str) -> None:
        with Session(self.engine) as db, db.begin():
            db.execute(
                update(password_reset_tokens)
                .where(password_reset_tokens.c.id == token_id)
                .values(attempt_count=password_reset_tokens.c.attempt_count + 1)
            )

    def mark_used(self, token_id: str) -> None:
        with Session(self.engine) as db, db.begin():
            db.execute(
                update(password_reset_tokens)
                .where(password_reset_tokens.c.id == token_id)
                .values(used_at=datetime.now(UTC))
            )
