"""Conservative suppression of duplicate YOLOX terminal-pair detections."""

from __future__ import annotations

from typing import Any


def _duplicate(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("source") != "model" or right.get("source") != "model":
        return False
    a, b = left.get("bbox"), right.get("bbox")
    if not isinstance(a, (list, tuple)) or not isinstance(b, (list, tuple)) or len(a) != 4 or len(b) != 4:
        return False
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - intersection
    if union <= 0 or intersection / union < 0.50:
        return False
    width = min(a[2] - a[0], b[2] - b[0])
    height = min(a[3] - a[1], b[3] - b[1])
    return abs(left["x"] - right["x"]) <= 0.25 * width and abs(left["y"] - right["y"]) <= 0.25 * height


def deduplicate_model_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the highest-scoring box in each clear duplicate group.

    Boxes without geometry and manually created points are never removed.
    The source list remains intact for the model-result audit field.
    """
    kept: list[dict[str, Any]] = []
    for point in sorted(points, key=lambda p: (-float(p.get("score", 0)), p["y"], p["x"], str(p["id"]))):
        if not any(_duplicate(point, prior) for prior in kept):
            kept.append(point)
    return sorted(kept, key=lambda p: (p["y"], p["x"], str(p["id"])))
