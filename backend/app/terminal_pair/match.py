"""Pair each OCR line with its nearest terminal point, at most once per point."""

from __future__ import annotations

import math
from statistics import median
from typing import Any


def _center(item: dict[str, Any]) -> tuple[float, float]:
    x1, y1, x2, y2 = item["bbox"]
    return (float(x1) + float(x2)) / 2, (float(y1) + float(y2)) / 2


def _terminal_pitch(points: list[dict[str, Any]]) -> float:
    gaps = [float(right["y"]) - float(left["y"]) for left, right in zip(points, points[1:])]
    positive_gaps = [gap for gap in gaps if math.isfinite(gap) and gap > 0]
    return float(median(positive_gaps)) if positive_gaps else 0.0


def _logical_y(item: dict[str, Any], terminal_x: float, pitch: float) -> float:
    center_x, center_y = _center(item)
    polygon = item.get("polygon")
    if not isinstance(polygon, (tuple, list)) or len(polygon) != 4 or pitch <= 0:
        return center_y
    try:
        dx = ((polygon[1][0] - polygon[0][0]) + (polygon[2][0] - polygon[3][0])) / 2
        dy = ((polygon[1][1] - polygon[0][1]) + (polygon[2][1] - polygon[3][1])) / 2
        slope = dy / dx
        if not math.isfinite(slope) or abs(dx) < 8 or abs(slope) > 0.35:
            return center_y
        correction = slope * (terminal_x - center_x)
        box_height = max(0.0, float(item["bbox"][3]) - float(item["bbox"][1]))
        limit = min(pitch * 0.35, max(12.0, box_height * 1.5))
        return center_y + correction if math.isfinite(correction) and abs(correction) <= limit else center_y
    except (TypeError, ValueError, ZeroDivisionError):
        return center_y


def _nearest_point(
    item: dict[str, Any], points: list[dict[str, Any]], pitch: float,
) -> tuple[tuple[int, float], tuple[int, float]]:
    center_y = _center(item)[1]
    center = min(enumerate(points), key=lambda entry: (abs(center_y - float(entry[1]["y"])), entry[0]))
    center_candidate = (center[0], abs(center_y - float(center[1]["y"])))
    projected = min(enumerate(points), key=lambda entry: (
        abs(_logical_y(item, float(entry[1]["x"]), pitch) - float(entry[1]["y"])), entry[0],
    ))
    projected_candidate = (
        projected[0], abs(_logical_y(item, float(projected[1]["x"]), pitch) - float(projected[1]["y"])),
    )
    if projected_candidate[0] == center_candidate[0]:
        return projected_candidate, center_candidate
    gap = abs(float(points[projected_candidate[0]]["y"]) - float(points[center_candidate[0]]["y"]))
    center_cost_gap = abs(center_y - float(points[projected_candidate[0]]["y"])) - center_candidate[1]
    if abs(projected_candidate[0] - center_candidate[0]) != 1 or gap == 0 or center_cost_gap > gap * 0.2:
        return center_candidate, center_candidate
    return projected_candidate, center_candidate


def _assignments_cross(proposals: list[tuple[dict[str, Any], tuple[int, float], tuple[int, float]]]) -> bool:
    ordered = sorted(proposals, key=lambda proposal: (*_center(proposal[0])[::-1], str(proposal[0]["id"])))
    highest_point_index = -1
    for _, projected, _ in ordered:
        if projected[0] < highest_point_index:
            return True
        highest_point_index = max(highest_point_index, projected[0])
    return False


def terminal_pair_rows(
    points: list[dict[str, Any]], items: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any] | None]]:
    """Return numbered terminal rows plus unnumbered unmatched OCR rows."""
    ordered_points = sorted(points, key=lambda p: (p["y"], p["x"], str(p["id"])))
    winners: dict[str, tuple[dict[str, Any], tuple[float, float, str]]] = {}
    unmatched: list[dict[str, Any]] = []
    point_ids = {str(point["id"]) for point in ordered_points}
    bound = {str(item.get("attributes", {}).get("terminal_point_id")): item for item in items
             if str(item.get("attributes", {}).get("terminal_point_id")) in point_ids}
    items = [item for item in items if str(item.get("attributes", {}).get("terminal_point_id")) not in point_ids]
    pitch = _terminal_pitch(ordered_points)
    proposals = [(item, *_nearest_point(item, ordered_points, pitch)) for item in items] if ordered_points else []
    use_center = _assignments_cross(proposals)
    if not ordered_points:
        unmatched.extend(items)
    for item, projected, center in proposals:
        index, distance = center if use_center else projected
        point = ordered_points[index]
        key = str(point["id"])
        rank = (distance, _center(item)[1], str(item["id"]))
        incumbent = winners.get(key)
        if incumbent is not None and rank >= incumbent[1]:
            unmatched.append(item)
        else:
            if incumbent is not None:
                unmatched.append(incumbent[0])
            winners[key] = item, rank

    for key, (item, _) in winners.items():
        if key in bound:
            unmatched.append(item)
    rows: list[tuple[float, int, float, str, str, dict[str, Any] | None]] = []
    for index, point in enumerate(ordered_points, start=1):
        rows.append((float(point["y"]), 0, float(point["x"]), str(point["id"]), str(index),
                     bound.get(str(point["id"])) or winners.get(str(point["id"]), (None, None))[0]))
    for item in unmatched:
        center_x, center_y = _center(item)
        rows.append((center_y, 1, center_x, str(item["id"]), "", item))
    rows.sort(key=lambda row: row[:4])
    return [(number, item) for _, _, _, _, number, item in rows]
