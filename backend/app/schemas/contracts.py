from typing import Any, Literal
from pydantic import BaseModel, Field


class UploadSessionCreate(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0, le=209_715_200)
    media_type: str
    sha256: str | None = None


class JobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    file_id: str
    model_id: str
    model_version: str
    pages: list[int] | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    illumination: Literal["none", "he", "clahe"] = "he"


class JobRerunCreate(BaseModel):
    model_id: str
    model_version: str
    illumination: Literal["none", "he", "clahe"] | None = None


class RegionJobRegionCreate(BaseModel):
    client_id: str = Field(min_length=1, max_length=100)
    bbox: tuple[float, float, float, float]


class RegionJobPageCreate(BaseModel):
    page_no: int = Field(gt=0)
    regions: list[RegionJobRegionCreate] = Field(min_length=1, max_length=20)


class RegionJobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    file_id: str | None = None
    source_job_id: str | None = None
    model_id: str
    model_version: str
    pages: list[RegionJobPageCreate] = Field(min_length=1, max_length=1)
    illumination: Literal["none", "he", "clahe"] = "he"


class CorrectionCreate(BaseModel):
    corrected_text: str = Field(max_length=500)
    base_revision: int = Field(ge=0)


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=300)


class CommentUpdate(CommentCreate):
    pass


class ResultReviewStatusUpdate(BaseModel):
    result_ids: list[str] = Field(min_length=1, max_length=500)
    review_status: Literal["unreviewed", "confirmed", "false_positive", "deleted"]


class ResultTableUpdate(BaseModel):
    terminal_number: str = Field(max_length=500)
    manual_confirmed: bool
    table_note: str = Field(max_length=1000)
    base_revision: int = Field(ge=0)


class ResultGeometryUpdate(BaseModel):
    result_id: str
    bbox: tuple[float, float, float, float]
    polygon: tuple[
        tuple[float, float], tuple[float, float],
        tuple[float, float], tuple[float, float],
    ] | None = None
    base_revision: int = Field(ge=0)


class ManualResultCreate(BaseModel):
    client_id: str
    bbox: tuple[float, float, float, float]
    polygon: tuple[
        tuple[float, float], tuple[float, float],
        tuple[float, float], tuple[float, float],
    ] | None = None
    text: str = Field(min_length=1, max_length=500)


class ResultDelete(BaseModel):
    result_id: str


class ResultEditsCreate(BaseModel):
    updates: list[ResultGeometryUpdate] = Field(default_factory=list, max_length=500)
    creates: list[ManualResultCreate] = Field(default_factory=list, max_length=500)
    deletes: list[ResultDelete] = Field(default_factory=list, max_length=500)


class TerminalPointInput(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    x: float
    y: float


class TerminalPointsUpdate(BaseModel):
    base_revision: int = Field(ge=0)
    points: list[TerminalPointInput] = Field(max_length=500)


class ExportCreate(BaseModel):
    format: Literal["xlsx"] = "xlsx"
    mode: Literal["simple", "full"] = "full"
    scope: Literal["all_pages"] = "all_pages"


class RegisterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str | None = Field(default=None, max_length=160)
    phone: str = Field(min_length=7, max_length=30)
    password: str = Field(min_length=8, max_length=128)
    employee_no: str | None = Field(default=None, max_length=40)
    department: str = Field(default="", max_length=100)


class LoginCreate(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    password: str = Field(min_length=1, max_length=128)


class CaptchaVerifyCreate(BaseModel):
    captcha_id: str = Field(min_length=16, max_length=128)
    code: str = Field(min_length=4, max_length=4, pattern=r"^[A-Za-z0-9]{4}$")


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    department: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ForgotPasswordCreate(BaseModel):
    phone: str = Field(min_length=7, max_length=30)


class PasswordResetCreate(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=128)


class TerminalSourceCorrection(BaseModel):
    result_id: str
    base_revision: int = Field(ge=0)
    text: str = Field(max_length=500)


class TerminalDocumentSave(BaseModel):
    base_revision: int = Field(ge=0)
    records: list[dict[str, Any]] = Field(max_length=5000)
    source: TerminalSourceCorrection | None = None
    sync_record_id: str | None = None
