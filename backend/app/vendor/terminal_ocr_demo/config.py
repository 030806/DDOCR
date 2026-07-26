"""Immutable terminal OCR inference configuration."""

from dataclasses import dataclass
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
RESOURCE_ROOT = PACKAGE_ROOT / "resources"


@dataclass(frozen=True)
class DemoConfig:
    det_model_name: str = "PP-OCRv5_mobile_det"
    rec_model_name: str = "PP-OCRv5_mobile_rec"
    device: str = "cpu"
    scale: float = 2.0
    rotations: tuple[int, ...] = (0, 90, 180, 270) #, 90, 180, 270
    min_roi_size: int = 8
    output_root: Path = PACKAGE_ROOT / "outputs" / "demo_runs"
    code_library_path: Path = RESOURCE_ROOT / "terminal_id_library.csv"
    base_code_pattern: str = r"^[HJXKUW]\d{1,3}(?:A[123]|B[123]|C|D)?$"
    extended_code_pattern: str = r"^[HJXKUW]\d{1,3}(?:A[123]|B[123]|C2|C|D|P)?$"
    cluster_iou_threshold: float = 0.35
    cluster_containment_threshold: float = 0.80
    fragment_max_area_ratio: float = 0.60
    unresolved_min_score: float = 0.30
