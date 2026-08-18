"""Deterministic OCR engine for hosts without AVX/GPU support.

Official PaddlePaddle CPU wheels require the AVX instruction set. Some
virtual machines (for example QEMU guests with a masked CPU model) do not
expose AVX, so importing ``paddle`` aborts the process with SIGILL. Set
``DDOCR_OCR_BACKEND=mock`` to keep the whole upload -> job -> page -> result
flow exercisable on such hosts without loading Paddle.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PIL import Image

from app.ocr.contracts import OcrRegion
from app.vendor.terminal_ocr_demo.models import OCRDetection, PipelineResult


class MockOcrEngine:
    """Produce stable pseudo detections without loading any model.

    The output intentionally mirrors the real engine surface consumed by
    ``app.ocr.adapter.OcrAdapter`` so switching back to
    ``DDOCR_OCR_BACKEND=paddle`` requires no other changes.
    """

    def __init__(self) -> None:
        self._loaded = True

    @property
    def is_loaded(self) -> bool:
        """Return whether an engine instance is currently retained."""

        return self._loaded

    def load(self) -> MockOcrEngine:
        """Return self; there is nothing to initialize."""

        return self

    def close(self) -> None:
        """Release resources; the mock engine holds none."""

        self._loaded = False

    def run(
        self,
        image: Image.Image,
        regions: Sequence[OcrRegion],
    ) -> PipelineResult:
        """Synthesize three deterministic text lines per ROI."""

        del image
        detections: list[OCRDetection] = []
        for region in regions:
            x1, y1, x2, y2 = region.bbox
            roi_height = max(1.0, float(y2 - y1))
            for index in range(3):
                top = y1 + roi_height * (index + 1) / 4
                height = max(1.0, roi_height / 12)
                detections.append(
                    OCRDetection(
                        roi_id=region.roi_id,
                        raw_text=f"DEMO-{region.roi_id[-4:]}-{index + 1}",
                        ocr_score=max(0.0, 0.99 - index * 0.01),
                        text_bbox_original=[
                            [float(x1), top],
                            [float(x2), top],
                            [float(x2), top + height],
                            [float(x1), top + height],
                        ],
                        rotation=0,
                        scale=1.0,
                        assessment=None,
                        output_text=None,
                        cluster_id=None,
                        is_unresolved=False,
                    )
                )
        return PipelineResult(detections=detections, roi_errors={})
