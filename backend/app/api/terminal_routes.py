from typing import Annotated, Literal
from fastapi import APIRouter, Header, Request, Response, Query
from pydantic import BaseModel, Field
from app.api.routes import authenticated_user, service
from app.services.terminal import TerminalService
from app.utils.common import envelope

router = APIRouter(prefix="/api/v1/terminal-tasks", tags=["terminal-tasks"])
Auth = Annotated[str | None, Header()]
Key = Annotated[str | None, Header(max_length=200)]


class CreateTask(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class SideBody(BaseModel):
    job_id: str
    page_no: int = Field(ge=1)
    base_revision: int = Field(ge=0)


class VersionBody(BaseModel):
    base_revision: int = Field(ge=0)
    version: str


class ReviewRow(BaseModel):
    id: str
    confirmed: bool
    note: str = Field(max_length=4000)


class ReviewBody(VersionBody):
    rows: list[ReviewRow] = Field(min_length=1, max_length=10000)


class LinkBody(VersionBody):
    left: str | None = None
    right: str | None = None


class ExportBody(VersionBody):
    scope: Literal["all", "confirmed"] = "all"


def execute(request, authorization, action, task_id, body, key):
    actor = authenticated_user(request, authorization)
    return envelope(TerminalService(service(request)).execute(action, task_id, body, actor["id"], key))


@router.post("")
def create(body: CreateTask, request: Request, authorization: Auth = None, idempotency_key: Key = None):
    return execute(request, authorization, "create", None, body.model_dump(), idempotency_key)


@router.get("")
def listing(request: Request, authorization: Auth = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    actor = authenticated_user(request, authorization)
    return envelope(TerminalService(service(request)).listing(actor["id"], offset, limit))


@router.get("/{task_id}")
@router.get("/{task_id}/rows")
def detail(task_id: str, request: Request, authorization: Auth = None):
    actor = authenticated_user(request, authorization)
    return envelope(TerminalService(service(request)).get(task_id, actor["id"]))


@router.put("/{task_id}/sides/{side}")
def side(task_id: str, side: Literal["left", "right"], body: SideBody, request: Request, authorization: Auth = None, idempotency_key: Key = None):
    return execute(request, authorization, "side", task_id, body.model_dump() | {"side": side}, idempotency_key)


@router.patch("/{task_id}/rows")
def review(task_id: str, body: ReviewBody, request: Request, authorization: Auth = None, idempotency_key: Key = None):
    return execute(request, authorization, "review", task_id, body.model_dump(), idempotency_key)


@router.post("/{task_id}/links")
def link(task_id: str, body: LinkBody, request: Request, authorization: Auth = None, idempotency_key: Key = None):
    return execute(request, authorization, "link", task_id, body.model_dump(), idempotency_key)


@router.post("/{task_id}/exports")
def export(task_id: str, body: ExportBody, request: Request, authorization: Auth = None, idempotency_key: Key = None):
    return execute(request, authorization, "export", task_id, body.model_dump(), idempotency_key)


@router.get("/{task_id}/exports/{export_id}")
def download(task_id: str, export_id: str, request: Request, authorization: Auth = None):
    actor = authenticated_user(request, authorization)
    content = TerminalService(service(request)).download(task_id, export_id, actor["id"])
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="terminal-results.xlsx"'})
