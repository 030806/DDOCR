import json
import math
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from app.ocr.adapter import OcrAdapter
from app.ocr.contracts import OcrRegion
from app.ocr.errors import OcrGeometryError, OcrImageDecodeError


@dataclass(frozen=True)
class FakeAssessment:
    normalized_text: str
    candidate_codes: tuple[str, ...]
    metadata: dict[str, object]


def detection(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "roi_id": "roi_001",
        "raw_text": "K2IC",
        "ocr_score": 0.91,
        "text_bbox_original": [
            [10.5, 20.0],
            [80.0, 18.0],
            [82.0, 50.0],
            [9.0, 52.0],
        ],
        "rotation": 90,
        "scale": 2.0,
        "assessment": FakeAssessment(
            normalized_text="K2IC",
            candidate_codes=("K21C",),
            metadata={"source": Path("codes.csv")},
        ),
        "output_text": "K21C",
        "cluster_id": "cluster_001",
        "is_unresolved": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def pipeline_result(*detections: object) -> SimpleNamespace:
    return SimpleNamespace(
        detections=list(detections),
        roi_errors={},
        audit_records=[],
    )


def test_adapt_detection_maps_demo_dto_to_ddocr_dto() -> None:
    adapted = OcrAdapter.adapt_detection(
        detection(),
        image_width=100,
        image_height=80,
    )

    assert adapted.text == "K21C"
    assert adapted.confidence == pytest.approx(0.91)
    assert adapted.polygon == (
        (10.5, 20.0),
        (80.0, 18.0),
        (82.0, 50.0),
        (9.0, 52.0),
    )
    assert adapted.bbox == (9.0, 18.0, 82.0, 52.0)
    assert adapted.roi_id == "roi_001"
    assert not adapted.review_required


def test_output_text_none_falls_back_to_raw_text() -> None:
    adapted = OcrAdapter.adapt_detection(
        detection(output_text=None, raw_text="X12"),
        image_width=100,
        image_height=80,
    )

    assert adapted.text == "X12"


def test_empty_output_is_preserved_and_requires_review() -> None:
    adapted = OcrAdapter.adapt_detection(
        detection(output_text="", is_unresolved=True),
        image_width=100,
        image_height=80,
    )

    assert adapted.text == ""
    assert adapted.review_required


def test_missing_confidence_becomes_zero_with_audit_attribute() -> None:
    adapted = OcrAdapter.adapt_detection(
        detection(ocr_score=None),
        image_width=100,
        image_height=80,
    )

    assert adapted.confidence == 0.0
    assert adapted.attributes["confidence_missing"] is True


@pytest.mark.parametrize(
    ("raw_score", "expected"),
    [(1.4, 1.0), (-0.3, 0.0), (math.nan, 0.0), (math.inf, 0.0)],
)
def test_invalid_confidence_is_database_safe(
    raw_score: float,
    expected: float,
) -> None:
    adapted = OcrAdapter.adapt_detection(
        detection(ocr_score=raw_score),
        image_width=100,
        image_height=80,
    )

    assert adapted.confidence == expected
    json.dumps(adapted.attributes, allow_nan=False)


def test_attributes_are_strict_json_and_preserve_demo_audit_fields() -> None:
    adapted = OcrAdapter.adapt_detection(
        detection(),
        image_width=100,
        image_height=80,
    )

    encoded = json.dumps(adapted.attributes, ensure_ascii=False, allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded["raw_text"] == "K2IC"
    assert decoded["rotation"] == 90
    assert decoded["scale"] == 2.0
    assert decoded["cluster_id"] == "cluster_001"
    assert decoded["assessment"]["candidate_codes"] == ["K21C"]
    assert decoded["assessment"]["metadata"]["source"] == "codes.csv"


def test_polygon_is_converted_to_clamped_bbox() -> None:
    adapted = OcrAdapter.adapt_detection(
        detection(text_bbox_original=[[-10, -5], [120, 10], [110, 90], [0, 70]]),
        image_width=100,
        image_height=80,
    )

    assert adapted.bbox == (0.0, 0.0, 100.0, 80.0)


def test_invalid_polygon_uses_geometry_error() -> None:
    with pytest.raises(OcrGeometryError):
        OcrAdapter.adapt_detection(
            detection(text_bbox_original=[]),
            image_width=100,
            image_height=80,
        )


def test_recognize_image_uses_full_image_roi_and_maps_page_result() -> None:
    captured_regions: list[OcrRegion] = []

    class FakeManagedEngine:
        def run(
            self,
            _image: Image.Image,
            regions: list[OcrRegion] | tuple[OcrRegion, ...],
        ) -> SimpleNamespace:
            captured_regions.extend(regions)
            return pipeline_result(detection())

    adapter = OcrAdapter(FakeManagedEngine())  # type: ignore[arg-type]
    result = adapter.recognize_image(Image.new("RGB", (200, 120)))

    assert captured_regions == [OcrRegion("page_1", (0.0, 0.0, 200.0, 120.0))]
    assert len(result.detections) == 1
    assert result.detections[0].text == "K21C"
    assert result.processing_ms >= 0
    assert result.roi_errors == {}


def test_recognize_file_rejects_undecodable_image(tmp_path: Path) -> None:
    source = tmp_path / "broken.png"
    source.write_bytes(b"not an image")

    class UnusedEngine:
        def run(self, _image: Image.Image, _regions: object) -> object:
            raise AssertionError("engine must not run")

    adapter = OcrAdapter(UnusedEngine())  # type: ignore[arg-type]

    with pytest.raises(OcrImageDecodeError):
        adapter.recognize_file(source)
