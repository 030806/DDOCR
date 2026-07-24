"""Core data models shared across the OCR pipeline."""

from dataclasses import dataclass
from dataclasses import field


@dataclass(frozen=True)
class CodeAssessment:
    raw_text: str
    normalized_text: str
    output_text: str
    recommended_code: str | None
    candidate_codes: tuple[str, ...]
    rule_status: str
    match_method: str
    edit_count: int | None
    review_status: str


@dataclass(frozen=True)
class ROI:
    roi_id: str
    bbox: tuple[int, int, int, int]

    def __post_init__(self) -> None:
        x_min, y_min, x_max, y_max = self.bbox
        if x_max <= x_min or y_max <= y_min:
            raise ValueError("ROI bounds must have positive width and height")

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]


@dataclass(frozen=True)
class OCRDetection:
    roi_id: str
    raw_text: str
    ocr_score: float | None
    text_bbox_original: list[list[float]]
    rotation: int
    scale: float
    assessment: CodeAssessment | None = None
    output_text: str | None = None
    cluster_id: str | None = None
    is_unresolved: bool = False


@dataclass(frozen=True)
class PipelineResult:
    detections: list[OCRDetection]
    roi_errors: dict[str, str]
    audit_records: list[dict[str, object]] = field(default_factory=list)
