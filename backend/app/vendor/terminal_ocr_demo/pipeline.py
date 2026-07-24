"""Multi-ROI OCR pipeline with per-ROI failure isolation."""

from typing import Protocol

from PIL import Image

from .config import DemoConfig
from .geometry import crop_roi, map_processed_polygon_to_original
from .models import OCRDetection, PipelineResult, ROI
from .ocr_engine import RawOCRRecord
from .postprocess import postprocess_detections
from .preprocess import generate_variants
from .rules import TerminalCodeRules


class OCREngine(Protocol):
    def recognize(self, image: Image.Image) -> list[RawOCRRecord]: ...


def run_pipeline(
    image: Image.Image,
    rois: list[ROI],
    engine: OCREngine,
    config: DemoConfig,
    rules: TerminalCodeRules | None = None,
) -> PipelineResult:
    detections: list[OCRDetection] = []
    roi_errors: dict[str, str] = {}

    for roi in rois:
        try:
            roi_image = crop_roi(image, roi)
            variants = generate_variants(roi_image, config.scale, config.rotations)
            for variant in variants:
                for record in engine.recognize(variant.image):
                    if len(record.polygon) < 2:
                        continue
                    polygon = map_processed_polygon_to_original(
                        record.polygon,
                        roi,
                        variant.unrotated_size,
                        variant.scale,
                        variant.rotation,
                    )
                    detections.append(
                        OCRDetection(
                            roi_id=roi.roi_id,
                            raw_text=record.text,
                            ocr_score=record.score,
                            text_bbox_original=polygon,
                            rotation=variant.rotation,
                            scale=variant.scale,
                        )
                    )
        except Exception as exc:
            roi_errors[roi.roi_id] = f"{type(exc).__name__}: {exc}"

    active_rules = rules or TerminalCodeRules.from_config(config)
    postprocessed = postprocess_detections(detections, active_rules, config)
    return PipelineResult(
        detections=postprocessed.detections,
        roi_errors=roi_errors,
        audit_records=postprocessed.audit_records,
    )
