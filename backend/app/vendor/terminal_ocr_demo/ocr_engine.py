"""Lazy PaddleOCR adapter with normalized output records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from PIL import Image

from .config import DemoConfig


@dataclass(frozen=True)
class RawOCRRecord:
    text: str
    score: float | None
    polygon: list[list[float]]


def build_paddleocr_kwargs(config: DemoConfig) -> dict[str, Any]:
    """Return the minimal CPU pipeline configuration used by the Demo."""

    return {
        "lang": "en",
        "device": config.device,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "enable_mkldnn": False,
        "text_detection_model_name": config.det_model_name,
        "text_recognition_model_name": config.rec_model_name,
    }


def _to_plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "tolist"):
        try:
            return _to_plain(value.tolist())
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    if hasattr(value, "json"):
        try:
            raw_json = value.json() if callable(value.json) else value.json
            return _to_plain(raw_json)
        except Exception:
            pass
    if hasattr(value, "to_dict"):
        try:
            return _to_plain(value.to_dict())
        except Exception:
            pass
    try:
        return _to_plain(dict(value))
    except Exception:
        return repr(value)


def _as_polygon(value: Any) -> list[list[float]]:
    if not isinstance(value, (list, tuple)):
        return []
    if len(value) == 4 and all(isinstance(item, (int, float)) for item in value):
        x_min, y_min, x_max, y_max = (float(item) for item in value)
        return [
            [x_min, y_min],
            [x_max, y_min],
            [x_max, y_max],
            [x_min, y_max],
        ]
    polygon: list[list[float]] = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return []
        if not isinstance(point[0], (int, float)) or not isinstance(point[1], (int, float)):
            return []
        polygon.append([float(point[0]), float(point[1])])
    return polygon


def _legacy_records(value: Any) -> list[RawOCRRecord]:
    records: list[RawOCRRecord] = []

    def visit(node: Any) -> None:
        if not isinstance(node, list):
            return
        if len(node) >= 2:
            polygon = _as_polygon(node[0])
            text_score = node[1]
            if polygon and isinstance(text_score, list) and text_score and isinstance(text_score[0], str):
                text = text_score[0].strip()
                score_value = text_score[1] if len(text_score) > 1 else None
                score = float(score_value) if isinstance(score_value, (int, float)) else None
                if text:
                    records.append(RawOCRRecord(text=text, score=score, polygon=polygon))
                return
        for child in node:
            visit(child)

    visit(value)
    return records


def normalize_records(result: Any) -> list[RawOCRRecord]:
    if result is None:
        return []
    plain = _to_plain(result)
    pages = plain if isinstance(plain, list) else [plain]
    records: list[RawOCRRecord] = []

    for page in pages:
        payload = page.get("res", page) if isinstance(page, dict) else page
        if isinstance(payload, dict):
            texts = payload.get("rec_texts") or payload.get("texts") or payload.get("text")
            scores = payload.get("rec_scores") or payload.get("scores") or payload.get("score")
            boxes = (
                payload.get("rec_polys")
                or payload.get("dt_polys")
                or payload.get("rec_boxes")
                or payload.get("dt_boxes")
                or payload.get("boxes")
                or payload.get("points")
            )
            if isinstance(texts, list):
                score_list = scores if isinstance(scores, list) else [None] * len(texts)
                box_list = boxes if isinstance(boxes, list) else [[] for _ in texts]
                for text, score_value, box in zip(texts, score_list, box_list):
                    text_value = str(text).strip() if text is not None else ""
                    if not text_value:
                        continue
                    score = float(score_value) if isinstance(score_value, (int, float)) else None
                    records.append(RawOCRRecord(text_value, score, _as_polygon(box)))
                continue
        records.extend(_legacy_records(payload))
    return records


class PaddleOCREngine:
    def __init__(
        self,
        config: DemoConfig,
        ocr_factory: Callable[[DemoConfig], Any] | None = None,
    ) -> None:
        self.config = config
        self._ocr_factory = ocr_factory
        self._ocr: Any | None = None

    @staticmethod
    def _default_factory(config: DemoConfig) -> Any:
        try:
            from paddleocr import PaddleOCR
        except ModuleNotFoundError as exc:
            raise RuntimeError("PaddleOCR is not installed in the backend environment") from exc
        return PaddleOCR(**build_paddleocr_kwargs(config))

    def _load(self) -> Any:
        if self._ocr is None:
            factory = self._ocr_factory or self._default_factory
            self._ocr = factory(self.config)
        return self._ocr

    def recognize(self, image: Image.Image) -> list[RawOCRRecord]:
        ocr = self._load()
        image_array = np.asarray(image.convert("RGB"))
        if hasattr(ocr, "predict"):
            try:
                result = ocr.predict(input=image_array)
            except TypeError:
                result = ocr.predict(image_array)
        elif hasattr(ocr, "ocr"):
            result = ocr.ocr(image_array, cls=True)
        else:
            raise RuntimeError("Loaded PaddleOCR object has no prediction method")
        return normalize_records(result)
