"""Internal, model-independent contracts used by the OCR integration layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeAlias, runtime_checkable


Point: TypeAlias = tuple[float, float]
"""One point in the source image's top-left-origin pixel coordinate system."""

Polygon: TypeAlias = tuple[Point, ...]
"""An ordered sequence of points expressed in source-image pixels."""

BoundingBox: TypeAlias = tuple[float, float, float, float]
"""An axis-aligned ``(x1, y1, x2, y2)`` source-image bounding box."""


@dataclass(frozen=True, slots=True)
class OcrRegion:
    """A validated source-image region submitted to the OCR engine."""

    roi_id: str
    bbox: BoundingBox


@dataclass(frozen=True, slots=True)
class AdapterDetection:
    """One model-independent OCR result ready for persistence by a worker."""

    text: str
    confidence: float
    polygon: Polygon
    bbox: BoundingBox
    roi_id: str
    review_required: bool
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdapterPageResult:
    """All adapted detections and diagnostics produced for one source page."""

    detections: tuple[AdapterDetection, ...]
    roi_errors: dict[str, str]
    processing_ms: int


@runtime_checkable
class OcrAdapterProtocol(Protocol):
    """Interface consumed by a future OCR task worker.

    Implementations decode ``source_path``, execute the configured OCR model,
    and return database-ready values without performing persistence themselves.
    """

    def recognize_file(
        self,
        source_path: Path,
        *,
        options: dict[str, Any] | None = None,
    ) -> AdapterPageResult:
        """Recognize a single image file and return adapted page results."""

        ...
