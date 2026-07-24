"""Stable internal exceptions and error codes for OCR processing."""

from __future__ import annotations


class OcrError(Exception):
    """Base exception for an OCR failure that can be persisted on a task."""

    code: str = "OCR_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message: str = message


class OcrUnsupportedMediaTypeError(OcrError):
    """Raised when a file type is not supported by the OCR adapter."""

    code: str = "OCR_UNSUPPORTED_MEDIA_TYPE"


class OcrImageDecodeError(OcrError):
    """Raised when an input image cannot be decoded safely."""

    code: str = "OCR_IMAGE_DECODE_FAILED"


class OcrModelLoadError(OcrError):
    """Raised when the configured OCR model cannot be initialized."""

    code: str = "OCR_MODEL_LOAD_FAILED"


class OcrInferenceError(OcrError):
    """Raised when model inference fails after successful initialization."""

    code: str = "OCR_INFERENCE_FAILED"


class OcrGeometryError(OcrError, ValueError):
    """Raised when an ROI or detected polygon has invalid geometry."""

    code: str = "OCR_INVALID_GEOMETRY"


class OcrLibraryMissingError(OcrError):
    """Raised when the configured terminal-code library is unavailable."""

    code: str = "OCR_LIBRARY_MISSING"
