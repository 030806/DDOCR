"""Validated ROI and polygon conversions in source-image pixel coordinates."""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.ocr.contracts import BoundingBox, OcrRegion
from app.ocr.errors import OcrGeometryError


def _positive_dimension(value: int, name: str) -> int:
    """Return a positive integer image dimension or raise a geometry error."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise OcrGeometryError(f"{name} must be a positive integer")
    return value


def _finite_coordinate(value: object, name: str) -> float:
    """Convert one numeric coordinate to a finite float."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OcrGeometryError(f"{name} must be a finite number")
    coordinate = float(value)
    if not math.isfinite(coordinate):
        raise OcrGeometryError(f"{name} must be a finite number")
    return coordinate


def normalize_roi_bbox(
    bbox: Sequence[float],
    image_width: int,
    image_height: int,
) -> BoundingBox:
    """Normalize and clamp an ROI to the source image.

    Reversed corners are accepted and reordered. Coordinates outside the image
    are clamped to its edges. A malformed or zero-area result is rejected.
    """

    width = _positive_dimension(image_width, "image_width")
    height = _positive_dimension(image_height, "image_height")
    if isinstance(bbox, (str, bytes)) or len(bbox) != 4:
        raise OcrGeometryError("ROI bbox must contain exactly four coordinates")

    first_x = _finite_coordinate(bbox[0], "bbox[0]")
    first_y = _finite_coordinate(bbox[1], "bbox[1]")
    second_x = _finite_coordinate(bbox[2], "bbox[2]")
    second_y = _finite_coordinate(bbox[3], "bbox[3]")

    x1 = min(float(width), max(0.0, min(first_x, second_x)))
    y1 = min(float(height), max(0.0, min(first_y, second_y)))
    x2 = min(float(width), max(0.0, max(first_x, second_x)))
    y2 = min(float(height), max(0.0, max(first_y, second_y)))
    if x2 <= x1 or y2 <= y1:
        raise OcrGeometryError("ROI bbox must have positive area inside the image")
    return x1, y1, x2, y2


def full_image_roi(
    image_width: int,
    image_height: int,
    *,
    roi_id: str = "page_1",
) -> OcrRegion:
    """Create the Milestone 1 whole-image ROI in original pixel coordinates."""

    width = _positive_dimension(image_width, "image_width")
    height = _positive_dimension(image_height, "image_height")
    if not isinstance(roi_id, str) or not roi_id.strip():
        raise OcrGeometryError("roi_id must be a non-empty string")
    return OcrRegion(
        roi_id=roi_id,
        bbox=(0.0, 0.0, float(width), float(height)),
    )


def polygon_to_bbox(
    polygon: Sequence[Sequence[float]],
    image_width: int,
    image_height: int,
) -> BoundingBox:
    """Convert a polygon to a clamped axis-aligned source-image bbox.

    At least two finite two-dimensional points are required. Coordinates are
    clamped only after the polygon bounds are calculated, so a polygon entirely
    outside the image is correctly rejected as a zero-area result.
    """

    width = _positive_dimension(image_width, "image_width")
    height = _positive_dimension(image_height, "image_height")
    if isinstance(polygon, (str, bytes)) or len(polygon) < 2:
        raise OcrGeometryError("Polygon must contain at least two points")

    x_values: list[float] = []
    y_values: list[float] = []
    for index, point in enumerate(polygon):
        if isinstance(point, (str, bytes)) or len(point) < 2:
            raise OcrGeometryError(
                f"polygon[{index}] must contain at least two coordinates"
            )
        x_values.append(_finite_coordinate(point[0], f"polygon[{index}][0]"))
        y_values.append(_finite_coordinate(point[1], f"polygon[{index}][1]"))

    return normalize_roi_bbox(
        (min(x_values), min(y_values), max(x_values), max(y_values)),
        width,
        height,
    )
