"""Spatial and exact-text duplicate merging."""

from .models import OCRDetection


def _bounds(polygon: list[list[float]]) -> tuple[float, float, float, float] | None:
    if not polygon:
        return None
    xs = [float(point[0]) for point in polygon if len(point) >= 2]
    ys = [float(point[1]) for point in polygon if len(point) >= 2]
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _iou(first: list[list[float]], second: list[list[float]]) -> float:
    first_bounds = _bounds(first)
    second_bounds = _bounds(second)
    if first_bounds is None or second_bounds is None:
        return 0.0
    ax1, ay1, ax2, ay2 = first_bounds
    bx1, by1, bx2, by2 = second_bounds
    intersection_width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    intersection_height = max(0.0, min(ay2, by2) - max(ay1, by1))
    intersection = intersection_width * intersection_height
    first_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    second_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def _score(detection: OCRDetection) -> float:
    return detection.ocr_score if detection.ocr_score is not None else -1.0


def _sort_key(detection: OCRDetection) -> tuple[str, float, float, str]:
    bounds = _bounds(detection.text_bbox_original)
    x_min, y_min = (bounds[0], bounds[1]) if bounds else (float("inf"), float("inf"))
    return detection.roi_id, y_min, x_min, detection.raw_text


def deduplicate_detections(
    detections: list[OCRDetection],
    iou_threshold: float = 0.5,
) -> list[OCRDetection]:
    if not 0 <= iou_threshold <= 1:
        raise ValueError("IoU threshold must be between 0 and 1")

    kept: list[OCRDetection] = []
    for detection in detections:
        normalized_text = detection.raw_text.strip().upper()
        match_index = next(
            (
                index
                for index, existing in enumerate(kept)
                if existing.roi_id == detection.roi_id
                and existing.raw_text.strip().upper() == normalized_text
                and _iou(existing.text_bbox_original, detection.text_bbox_original) >= iou_threshold
            ),
            None,
        )
        if match_index is None:
            kept.append(detection)
        elif _score(detection) > _score(kept[match_index]):
            kept[match_index] = detection
    return sorted(kept, key=_sort_key)
