"""Pair each OCR line with its nearest terminal point, at most once per point."""

from __future__ import annotations

from typing import Any


def _center(item: dict[str, Any]) -> tuple[float, float]:
    x1, y1, x2, y2 = item["bbox"]
    return (float(x1) + float(x2)) / 2, (float(y1) + float(y2)) / 2


def _logical_y(item: dict[str, Any], terminal_x: float) -> float:
    center_x, center_y = _center(item)
    polygon = item.get("polygon")
    if not isinstance(polygon, (tuple, list)) or len(polygon) != 4:
        return center_y
    try:
        dx = ((polygon[1][0] - polygon[0][0]) + (polygon[2][0] - polygon[3][0])) / 2
        dy = ((polygon[1][1] - polygon[0][1]) + (polygon[2][1] - polygon[3][1])) / 2
        if abs(dx) < 8 or abs(dy / dx) > 0.35:
            return center_y
        return center_y + (dy / dx) * (terminal_x - center_x)
    except (TypeError, ValueError, ZeroDivisionError):
        return center_y


def terminal_pair_rows(
    points: list[dict[str, Any]], items: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any] | None]]:
    """Return numbered terminal rows plus unnumbered unmatched OCR rows."""
    ordered_points = sorted(points, key=lambda p: (p["y"], p["x"], str(p["id"])))
    winners: dict[str, tuple[dict[str, Any], tuple[float, float, str]]] = {}
    unmatched: list[dict[str, Any]] = []
    for item in items:
        if not ordered_points:
            unmatched.append(item)
            continue
        point, distance = min(
            ((point, abs(_logical_y(item, float(point["x"])) - float(point["y"])))
             for point in ordered_points),
            key=lambda candidate: (candidate[1], candidate[0]["y"], candidate[0]["x"], str(candidate[0]["id"])),
        )
        key = str(point["id"])
        rank = (distance, _center(item)[1], str(item["id"]))
        incumbent = winners.get(key)
        if incumbent is not None and rank >= incumbent[1]:
            unmatched.append(item)
        else:
            if incumbent is not None:
                unmatched.append(incumbent[0])
            winners[key] = item, rank

    rows: list[tuple[float, int, float, str, str, dict[str, Any] | None]] = []
    for index, point in enumerate(ordered_points, start=1):
        rows.append((float(point["y"]), 0, float(point["x"]), str(point["id"]), str(index),
                     winners.get(str(point["id"]), (None, None))[0]))
    for item in unmatched:
        center_x, center_y = _center(item)
        rows.append((center_y, 1, center_x, str(item["id"]), "", item))
    rows.sort(key=lambda row: row[:4])
    return [(number, item) for _, _, _, _, number, item in rows]
