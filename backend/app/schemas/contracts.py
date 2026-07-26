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


class RegisterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str | None = Field(default=None, max_length=160)
    phone: str = Field(min_length=7, max_length=30)
    password: str = Field(min_length=8, max_length=128)
    employee_no: str = Field(min_length=1, max_length=40)
    department: str = Field(default="", max_length=100)


class LoginCreate(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    password: str = Field(min_length=1, max_length=128)


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    department: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ForgotPasswordCreate(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    employee_no: str = Field(min_length=1, max_length=40)


class PasswordResetCreate(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=128)
