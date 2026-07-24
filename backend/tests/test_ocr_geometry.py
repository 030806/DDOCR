import math

import pytest

from app.ocr.errors import OcrGeometryError
from app.ocr.geometry import full_image_roi, normalize_roi_bbox, polygon_to_bbox


def test_polygon_to_bbox_uses_polygon_extrema() -> None:
    polygon = ((20.5, 30.25), (80.75, 25.0), (90.0, 70.5), (10.0, 75.0))

    assert polygon_to_bbox(polygon, 100, 100) == (10.0, 25.0, 90.0, 75.0)


def test_polygon_to_bbox_clamps_coordinates_to_image() -> None:
    polygon = ((-20.0, 10.0), (40.0, -30.0), (130.0, 90.0), (50.0, 120.0))

    assert polygon_to_bbox(polygon, 100, 80) == (0.0, 0.0, 100.0, 80.0)


def test_polygon_entirely_outside_image_is_rejected() -> None:
    with pytest.raises(OcrGeometryError):
        polygon_to_bbox(((120.0, 20.0), (150.0, 40.0)), 100, 80)


@pytest.mark.parametrize("invalid_value", [math.nan, math.inf, -math.inf])
def test_polygon_rejects_non_finite_coordinates(invalid_value: float) -> None:
    with pytest.raises(OcrGeometryError):
        polygon_to_bbox(((0.0, 0.0), (invalid_value, 10.0)), 100, 80)


@pytest.mark.parametrize("polygon", [(), ((1.0, 2.0),)])
def test_polygon_rejects_empty_or_single_point_polygon(
    polygon: tuple[tuple[float, float], ...],
) -> None:
    with pytest.raises(OcrGeometryError):
        polygon_to_bbox(polygon, 100, 80)


def test_full_image_roi_uses_source_dimensions() -> None:
    roi = full_image_roi(1920, 1080)

    assert roi.roi_id == "page_1"
    assert roi.bbox == (0.0, 0.0, 1920.0, 1080.0)


@pytest.mark.parametrize(
    ("width", "height"),
    [(0, 100), (-1, 100), (100, 0), (100, -1)],
)
def test_full_image_roi_rejects_non_positive_dimensions(
    width: int,
    height: int,
) -> None:
    with pytest.raises(OcrGeometryError):
        full_image_roi(width, height)


def test_normalize_roi_bbox_reorders_and_clamps_coordinates() -> None:
    assert normalize_roi_bbox((120.0, 90.0, -10.0, 5.0), 100, 80) == (
        0.0,
        5.0,
        100.0,
        80.0,
    )


@pytest.mark.parametrize("invalid_value", [math.nan, math.inf, -math.inf])
def test_normalize_roi_bbox_rejects_non_finite_coordinates(
    invalid_value: float,
) -> None:
    with pytest.raises(OcrGeometryError):
        normalize_roi_bbox((0.0, 0.0, invalid_value, 10.0), 100, 80)


@pytest.mark.parametrize(
    "bbox",
    [
        (1.0, 1.0, 1.0, 10.0),
        (1.0, 1.0, 10.0, 1.0),
        (-20.0, 1.0, -10.0, 10.0),
        (120.0, 1.0, 130.0, 10.0),
    ],
)
def test_normalize_roi_bbox_rejects_zero_area_after_clamping(
    bbox: tuple[float, float, float, float],
) -> None:
    with pytest.raises(OcrGeometryError):
        normalize_roi_bbox(bbox, 100, 80)
