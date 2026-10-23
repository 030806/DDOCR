from __future__ import annotations

import numpy as np
from PIL import Image
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

from app.ocr.ctc_candidates import CandidateTextRecognizer
from app.ocr.onnx_engine import OnnxRecognizerEngine
from app.vendor.terminal_ocr_demo.config import DemoConfig
from app.vendor.terminal_ocr_demo.models import ModelTextCandidate


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


def test_onnx_engine_retains_model_candidate_evidence() -> None:
    candidate = ModelTextCandidate("H1", -1.0)

    def fake_ocr(image: np.ndarray) -> tuple[list[object], float]:
        del image
        return ([
            [[[1, 2], [5, 2], [5, 6], [1, 6]], "H（", 0.8, {
                "model_candidates": (candidate,),
                "model_raw_log_probability": -0.5,
            }]
        ], 0.01)

    engine = OnnxRecognizerEngine(DemoConfig(), ocr_factory=lambda: fake_ocr)
    records = engine.recognize(Image.new("RGB", (8, 8)))
    assert records[0].text == "H（"
    assert records[0].model_candidates == (candidate,)
    assert records[0].model_raw_log_probability == -0.5


def test_default_factory_passes_explicit_recognition_model_and_keys(monkeypatch) -> None:
    received: dict[str, str] = {}

    class FakeRapidOCR:
        def __init__(self, **kwargs: str) -> None:
            received.update(kwargs)
            self.text_rec = SimpleNamespace(
                session=object(), postprocess_op=SimpleNamespace(character=["blank", "H"])
            )

    fake_module = ModuleType("rapidocr_onnxruntime")
    fake_module.RapidOCR = FakeRapidOCR
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", fake_module)
    config = DemoConfig(
        onnx_rec_model_path=Path("/models/rec.onnx"),
        onnx_rec_keys_path=Path("/models/keys.txt"),
    )
    engine = OnnxRecognizerEngine(config)
    ocr = engine._default_factory()
    assert received == {
        "rec_model_path": str(config.onnx_rec_model_path),
        "rec_keys_path": str(config.onnx_rec_keys_path),
    }
    assert isinstance(ocr.text_rec, CandidateTextRecognizer)
