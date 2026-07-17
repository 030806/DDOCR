from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def uid() -> str:
    return str(uuid4())


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def envelope(
    data: Any,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {"data": data, "request_id": request_id or f"req_{uid()}"}
