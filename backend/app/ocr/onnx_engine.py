"""ONNX Runtime OCR engine for hosts without AVX support.

Official PaddlePaddle CPU wheels require the AVX instruction set. Some
virtual machines (for example KVM guests with a masked CPU model) do not
expose AVX, so importing ``paddle`` aborts the process with SIGILL. RapidOCR
executes the same PP-OCR detection/recognition models exported to ONNX
through onnxruntime, which does not require AVX. Set
``DDOCR_OCR_BACKEND=onnx`` to use this engine.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
import logging
import math

import numpy as np
from PIL import Image

from app.vendor.terminal_ocr_demo.config import DemoConfig
from app.vendor.terminal_ocr_demo.ocr_engine import RawOCRRecord
from app.vendor.terminal_ocr_demo.models import ModelTextCandidate
from app.vendor.terminal_ocr_demo.rules import ALLOWED_CHARACTERS

from .ctc_candidates import CandidateTextRecognizer


_LOG = logging.getLogger(__name__)


def _as_polygon(value: Any) -> list[list[float]]:
    """Convert a RapidOCR box (four points, possibly numpy) to float points."""

    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        return []
    polygon: list[list[float]] = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return []
        try:
            polygon.append([float(point[0]), float(point[1])])
        except (TypeError, ValueError):
            return []
    return polygon if len(polygon) >= 2 else []


def _normalize_records(result: Any) -> list[RawOCRRecord]:
    """Convert a RapidOCR ``(box, text, score)`` result into pipeline records.

    RapidOCR returns a tuple ``(items, elapse)`` where each item is
    ``[box, text, score]``; older versions may return a plain list. Empty
    texts and malformed boxes are skipped.
    """

    if isinstance(result, tuple):
        result = result[0] if result else None
    records: list[RawOCRRecord] = []
    for item in result or []:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        polygon = _as_polygon(item[0])
        if not polygon:
            continue
        text_value = str(item[1]).strip() if item[1] is not None else ""
        if not text_value:
            continue
        score = float(item[2]) if isinstance(item[2], (int, float)) else None
        evidence = item[3] if len(item) > 3 and isinstance(item[3], dict) else {}
        candidates = tuple(
            candidate for candidate in evidence.get("model_candidates", ())
            if isinstance(candidate, ModelTextCandidate)
        )
        raw_log_probability = evidence.get("model_raw_log_probability")
        if not isinstance(raw_log_probability, (int, float)) or not math.isfinite(raw_log_probability):
            raw_log_probability = None
        records.append(
            RawOCRRecord(
                text=text_value,
                score=score,
                polygon=polygon,
                model_candidates=candidates,
                model_raw_log_probability=raw_log_probability,
            )
        )
    return records


class OnnxRecognizerEngine:
    """Run RapidOCR (PP-OCR models on ONNX Runtime) for the demo pipeline.

    The class implements the same ``recognize`` protocol as
    ``PaddleOCREngine`` so the existing multi-ROI pipeline, terminal-code
    postprocessing, and the public adapter contract remain unchanged.
    """

    def __init__(
        self,
        config: DemoConfig,
        ocr_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.config = config
        self._ocr_factory = ocr_factory
        self._ocr: Any | None = None

    def _default_factory(self) -> Any:
        if (self.config.onnx_rec_model_path is None) != (self.config.onnx_rec_keys_path is None):
            raise ValueError("Custom ONNX recognition requires both model and keys paths")
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "rapidocr-onnxruntime is not installed in the backend environment"
            ) from exc
        options: dict[str, str] = {}
        if self.config.onnx_rec_model_path is not None:
            options["rec_model_path"] = str(self.config.onnx_rec_model_path)
        if self.config.onnx_rec_keys_path is not None:
            options["rec_keys_path"] = str(self.config.onnx_rec_keys_path)
        ocr = RapidOCR(**options)
        recognizer = getattr(ocr, "text_rec", None)
        if recognizer is not None and hasattr(recognizer, "session") and hasattr(recognizer, "postprocess_op"):
            ocr.text_rec = CandidateTextRecognizer(recognizer, ALLOWED_CHARACTERS)
        else:
            _LOG.warning("RapidOCR recognizer internals unavailable; CTC candidates disabled")
        return ocr

    def _load(self) -> Any:
        if self._ocr is None:
            factory = self._ocr_factory or self._default_factory
            self._ocr = factory()
        return self._ocr

    def recognize(self, image: Image.Image) -> list[RawOCRRecord]:
        """Recognize one image and return normalized pipeline records."""

        ocr = self._load()
        image_array = np.asarray(image.convert("RGB"))
        # RapidOCR expects the OpenCV BGR channel order like PaddleOCR.
        bgr_array = image_array[..., ::-1].copy()
        result = ocr(bgr_array)
        return _normalize_records(result)
