"""Stable public types for the DDOCR OCR integration layer."""

from app.ocr.contracts import (
    AdapterDetection,
    AdapterPageResult,
    BoundingBox,
    OcrAdapterProtocol,
    OcrRegion,
    Point,
    Polygon,
)
from app.ocr.errors import (
    OcrError,
    OcrGeometryError,
    OcrImageDecodeError,
    OcrInferenceError,
    OcrLibraryMissingError,
    OcrModelLoadError,
    OcrUnsupportedMediaTypeError,
)
from app.ocr.settings import OcrSettings

__all__ = [
    "AdapterDetection",
    "AdapterPageResult",
    "BoundingBox",
    "OcrAdapterProtocol",
    "OcrError",
    "OcrGeometryError",
    "OcrImageDecodeError",
    "OcrInferenceError",
    "OcrLibraryMissingError",
    "OcrModelLoadError",
    "OcrRegion",
    "OcrSettings",
    "OcrUnsupportedMediaTypeError",
    "Point",
    "Polygon",
]
