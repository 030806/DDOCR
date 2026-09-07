from typing import Annotated, Literal
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from app.api.routes import authenticated_user, service
from app.services.dataset import DatasetService
from app.utils.common import envelope

router = APIRouter(prefix="/api/v1/ocr")


class ExpectedResult(BaseModel):
    id: str
    revision: int = Field(ge=0)
    geometry_revision: int = Field(ge=0)
    review_status: Literal["unreviewed", "confirmed", "false_positive", "deleted"]


class ReviewCompletion(BaseModel):
    expected_results: list[ExpectedResult] = Field(max_length=10000)


class DatasetEntry(BaseModel):
    reviewed_version: int = Field(ge=0)


class DatasetStatuses(BaseModel):
    job_ids: list[str] = Field(max_length=200)


@router.post("/jobs/dataset-statuses")
def statuses(body: DatasetStatuses, request: Request, authorization: Annotated[str | None, Header()] = None):
    actor = authenticated_user(request, authorization)
    return envelope(DatasetService(service(request)).statuses(body.job_ids, actor["id"]))


@router.post("/jobs/{job_id}/review-completion")
def complete(job_id: str, body: ReviewCompletion, request: Request, authorization: Annotated[str | None, Header()] = None, idempotency_key: Annotated[str | None, Header(max_length=200)] = None):
    actor = authenticated_user(request, authorization)
    return envelope(DatasetService(service(request)).execute("review-completion", job_id, body.model_dump(), actor["id"], idempotency_key))


@router.post("/jobs/{job_id}/dataset-entries")
def save(job_id: str, body: DatasetEntry, request: Request, authorization: Annotated[str | None, Header()] = None, idempotency_key: Annotated[str | None, Header(max_length=200)] = None):
    actor = authenticated_user(request, authorization)
    return envelope(DatasetService(service(request)).execute("dataset-entries", job_id, body.model_dump(), actor["id"], idempotency_key))
