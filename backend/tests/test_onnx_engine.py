from __future__ import annotations

import numpy as np
from PIL import Image

from app.ocr.onnx_engine import OnnxRecognizerEngine
from app.vendor.terminal_ocr_demo.config import DemoConfig


def test_onnx_engine_normalizes_rapidocr_records_and_uses_bgr() -> None:
    received: list[np.ndarray] = []

    def fake_ocr(image: np.ndarray) -> tuple[list[object], float]:
        received.append(image)
        return ([[[[1, 2], [5, 2], [5, 6], [1, 6]], "K21C", 0.94]], 0.01)

    engine = OnnxRecognizerEngine(DemoConfig(), ocr_factory=lambda: fake_ocr)
    records = engine.recognize(Image.new("RGB", (8, 8), (10, 20, 30)))

    assert received[0][0, 0].tolist() == [30, 20, 10]
    assert [(record.text, record.score, record.polygon) for record in records] == [
        ("K21C", 0.94, [[1.0, 2.0], [5.0, 2.0], [5.0, 6.0], [1.0, 6.0]])
    ]
