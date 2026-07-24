"""Map terminal OCR demo results to model-independent DDOCR DTOs."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from PIL import Image, UnidentifiedImageError

from app.ocr.contracts import (
    AdapterDetection,
    AdapterPageResult,
    OcrRegion,
    Polygon,
)
from app.ocr.engine import TerminalOcrEngine
from app.ocr.errors import OcrImageDecodeError
from app.ocr.geometry import full_image_roi, polygon_to_bbox


class DemoDetection(Protocol):
    """Structural contract of ``terminal_ocr_demo.models.OCRDetection``."""

    roi_id: str
    raw_text: str
    ocr_score: float | None
    text_bbox_original: Sequence[Sequence[float]]
    rotation: int
    scale: float
    assessment: object | None
    output_text: str | None
    cluster_id: str | None
    is_unresolved: bool


class DemoPipelineResult(Protocol):
    """Structural contract of ``terminal_ocr_demo.models.PipelineResult``."""

    detections: Sequence[DemoDetection]
    roi_errors: Mapping[str, str]
    audit_records: Sequence[Mapping[str, object]]


def _json_safe(value: object) -> Any:
    """Recursively project arbitrary demo metadata to strict JSON values."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return repr(value)


def _normalize_confidence(value: object) -> tuple[float, dict[str, Any]]:
    """Return a database-safe confidence and JSON-safe audit attributes."""

    attributes: dict[str, Any] = {}
    if value is None:
        attributes["confidence_missing"] = True
        return 0.0, attributes
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        attributes["confidence_invalid"] = True
        attributes["raw_confidence"] = _json_safe(value)
        return 0.0, attributes

    confidence = float(value)
    if not math.isfinite(confidence):
        attributes["confidence_invalid"] = True
        attributes["raw_confidence"] = repr(confidence)
        return 0.0, attributes
    normalized = min(1.0, max(0.0, confidence))
    if normalized != confidence:
        attributes["confidence_clamped"] = True
        attributes["raw_confidence"] = confidence
    return normalized, attributes


def _normalize_polygon(points: Sequence[Sequence[float]]) -> Polygon:
    """Copy demo polygon coordinates into the immutable DDOCR representation."""

    polygon: list[tuple[float, float]] = []
    for point in points:
        if isinstance(point, (str, bytes)) or len(point) < 2:
            # ``polygon_to_bbox`` owns the stable public geometry error.
            polygon.append(tuple(point))  # type: ignore[arg-type]
            continue
        polygon.append((float(point[0]), float(point[1])))
    return tuple(polygon)


class OcrAdapter:
    """Execute an injected engine and adapt its Demo DTOs to DDOCR DTOs."""

    def __init__(self, engine: TerminalOcrEngine) -> None:
        """Create a stateless adapter around one managed OCR engine."""

        self._engine: TerminalOcrEngine = engine

    def recognize_file(
        self,
        source_path: Path,
        *,
        options: dict[str, Any] | None = None,
    ) -> AdapterPageResult:
        """Decode one image file, execute OCR, and adapt its result.

        Milestone 1 deliberately ignores future ROI options and uses one
        whole-image ROI, preserving the existing REST request contract.
        """

        del options
        try:
            with Image.open(source_path) as opened_image:
                opened_image.load()
                image = opened_image.convert("RGB")
        except (FileNotFoundError, OSError, UnidentifiedImageError) as exc:
            raise OcrImageDecodeError(
                f"OCR source image cannot be decoded: {source_path}"
            ) from exc
        return self.recognize_image(image)

    def recognize_image(
        self,
        image: Image.Image,
        regions: Sequence[OcrRegion] | None = None,
    ) -> AdapterPageResult:
        """Execute OCR for an in-memory image and adapt all detections."""

        active_regions: Sequence[OcrRegion] = regions or (
            full_image_roi(image.width, image.height),
        )
        started = perf_counter()
        demo_result = self._engine.run(image, active_regions)
        processing_ms = max(0, round((perf_counter() - started) * 1000))
        return self.adapt_page_result(
            demo_result,
            image_width=image.width,
            image_height=image.height,
            processing_ms=processing_ms,
        )

    def adapt_page_result(
        self,
        result: DemoPipelineResult,
        *,
        image_width: int,
        image_height: int,
        processing_ms: int,
    ) -> AdapterPageResult:
        """Map one Demo pipeline result to a DDOCR page result."""

        detections = tuple(
            self.adapt_detection(
                detection,
                image_width=image_width,
                image_height=image_height,
            )
            for detection in result.detections
        )
        return AdapterPageResult(
            detections=detections,
            roi_errors={str(key): str(value) for key, value in result.roi_errors.items()},
            processing_ms=max(0, int(processing_ms)),
        )

    @staticmethod
    def adapt_detection(
        detection: DemoDetection,
        *,
        image_width: int,
        image_height: int,
    ) -> AdapterDetection:
        """Map a Demo detection to one persistence-ready DDOCR detection."""

        bbox = polygon_to_bbox(
            detection.text_bbox_original,
            image_width,
            image_height,
        )
        polygon = _normalize_polygon(detection.text_bbox_original)
        confidence, confidence_attributes = _normalize_confidence(
            detection.ocr_score
        )
        text = (
            detection.raw_text
            if detection.output_text is None
            else detection.output_text
        )
        assessment = _json_safe(detection.assessment)
        attributes: dict[str, Any] = {
            "roi_id": str(detection.roi_id),
            "raw_text": str(detection.raw_text),
            "rotation": _json_safe(detection.rotation),
            "scale": _json_safe(detection.scale),
            "cluster_id": _json_safe(detection.cluster_id),
            "is_unresolved": bool(detection.is_unresolved),
            **confidence_attributes,
        }
        if assessment is not None:
            attributes["assessment"] = assessment

        # Reject accidental NaN/Infinity or unsupported objects before a future
        # repository passes this mapping to a SQLAlchemy JSON column.
        json.dumps(attributes, ensure_ascii=False, allow_nan=False)
        return AdapterDetection(
            text=str(text),
            confidence=confidence,
            polygon=polygon,
            bbox=bbox,
            roi_id=str(detection.roi_id),
            review_required=bool(detection.is_unresolved) or not str(text),
            attributes=attributes,
        )
