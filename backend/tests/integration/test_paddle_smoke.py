"""Opt-in smoke test for the real vendored PaddleOCR pipeline."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.ocr.contracts import OcrRegion
from app.ocr.engine import TerminalOcrEngine
from app.ocr.settings import OcrSettings
from app.vendor.terminal_ocr_demo.config import RESOURCE_ROOT
from app.vendor.terminal_ocr_demo.models import PipelineResult


pytestmark = pytest.mark.skipif(
    os.getenv("DDOCR_RUN_PADDLE_SMOKE") != "1",
    reason="set DDOCR_RUN_PADDLE_SMOKE=1 to run the real PaddleOCR smoke test",
)


def test_terminal_ocr_engine_runs_real_paddle_pipeline(tmp_path: Path) -> None:
    """Load real Paddle models and return a normal PipelineResult."""

    image = Image.new("RGB", (320, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 45), "K21C", fill="black", stroke_width=1)
    settings = OcrSettings(
        device="cpu",
        model_cache=Path(
            os.getenv("DDOCR_OCR_MODEL_CACHE", tmp_path / "paddlex-cache")
        ).expanduser().resolve(),
        code_library=(RESOURCE_ROOT / "terminal_id_library.csv").resolve(),
        scale=1.0,
        rotations=(0,),
        max_concurrency=1,
        execution_mode="blocking",
    )
    engine = TerminalOcrEngine(settings)

    try:
        result = engine.run(
            image,
            [OcrRegion("page_1", (0.0, 0.0, 320.0, 120.0))],
        )
    finally:
        engine.close()

    assert isinstance(result, PipelineResult)
    assert isinstance(result.detections, list)
    assert isinstance(result.roi_errors, dict)
    assert isinstance(result.audit_records, list)
    assert result.roi_errors == {}
