from typing import Any, Literal
from pydantic import BaseModel, Field


class UploadSessionCreate(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0, le=104_857_600)
    media_type: str
    sha256: str | None = None


class JobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    file_id: str
    model_id: str
    model_version: str
    pages: list[int] | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class CorrectionCreate(BaseModel):
    corrected_text: str = Field(max_length=500)
    base_revision: int = Field(ge=0)


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=300)


class CommentUpdate(CommentCreate):
    pass


class ExportCreate(BaseModel):
    format: Literal["xlsx"] = "xlsx"
    mode: Literal["simple", "full"] = "full"
    scope: Literal["all_pages"] = "all_pages"

