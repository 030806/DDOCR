"""ROI validation and coordinate transformations."""

from collections.abc import Sequence

from PIL import Image

from .models import ROI


def canvas_rect_to_roi(
    roi_id: str,
    rect: tuple[float, float, float, float],
    canvas_size: tuple[int, int],
    original_size: tuple[int, int],
    min_roi_size: int,
) -> ROI:
    canvas_width, canvas_height = canvas_size
    original_width, original_height = original_size
    if canvas_width <= 0 or canvas_height <= 0:
        raise ValueError("Canvas dimensions must be positive")
    if original_width <= 0 or original_height <= 0:
        raise ValueError("Original image dimensions must be positive")

    left, top, width, height = rect
    canvas_x_min = min(left, left + width)
    canvas_x_max = max(left, left + width)
    canvas_y_min = min(top, top + height)
    canvas_y_max = max(top, top + height)

    scale_x = original_width / canvas_width
    scale_y = original_height / canvas_height
    x_min = max(0, min(original_width, round(canvas_x_min * scale_x)))
    x_max = max(0, min(original_width, round(canvas_x_max * scale_x)))
    y_min = max(0, min(original_height, round(canvas_y_min * scale_y)))
    y_max = max(0, min(original_height, round(canvas_y_max * scale_y)))

    if x_max - x_min < min_roi_size or y_max - y_min < min_roi_size:
        raise ValueError(f"ROI is too small; minimum side is {min_roi_size} pixels")
    return ROI(roi_id=roi_id, bbox=(x_min, y_min, x_max, y_max))


def crop_roi(image: Image.Image, roi: ROI) -> Image.Image:
    return image.crop(roi.bbox)


def _unrotate_point(
    x: float,
    y: float,
    unrotated_width: int,
    unrotated_height: int,
    rotation: int,
) -> tuple[float, float]:
    normalized_rotation = rotation % 360
    if normalized_rotation == 0:
        return x, y
    if normalized_rotation == 90:
        return unrotated_width - y, x
    if normalized_rotation == 180:
        return unrotated_width - x, unrotated_height - y
    if normalized_rotation == 270:
        return y, unrotated_height - x
    raise ValueError("Only right-angle rotations are supported")


def map_processed_polygon_to_original(
    polygon: Sequence[Sequence[float]],
    roi: ROI,
    unrotated_size: tuple[int, int],
    scale: float,
    rotation: int,
) -> list[list[float]]:
    if scale <= 0:
        raise ValueError("Scale must be positive")
    if rotation % 360 not in {0, 90, 180, 270}:
        raise ValueError("Only right-angle rotations are supported")

    unrotated_width, unrotated_height = unrotated_size
    roi_x_min, roi_y_min, roi_x_max, roi_y_max = roi.bbox
    mapped: list[list[float]] = []
    for point in polygon:
        if len(point) < 2:
            continue
        unrotated_x, unrotated_y = _unrotate_point(
            float(point[0]),
            float(point[1]),
            unrotated_width,
            unrotated_height,
            rotation,
        )
        original_x = min(roi_x_max, max(roi_x_min, roi_x_min + unrotated_x / scale))
        original_y = min(roi_y_max, max(roi_y_min, roi_y_min + unrotated_y / scale))
        mapped.append([round(original_x, 4), round(original_y, 4)])
    return mapped
