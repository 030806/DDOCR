from app.terminal_pair.dedup import deduplicate_model_points
from app.terminal_pair.match import terminal_pair_rows


def point(identifier, y, *, score=0.9, bbox=None):
    result = {"id": identifier, "x": 50.0, "y": float(y), "score": score, "source": "model"}
    if bbox is not None:
        result["bbox"] = bbox
    return result


def line(identifier, y):
    return {"id": identifier, "bbox": [100, y - 5, 140, y + 5], "display_text": identifier}


def test_nearest_matching_skips_missing_line_without_shifting_later_rows():
    rows = terminal_pair_rows(
        [point("a", 100), point("b", 200), point("c", 300)],
        [line("H1", 105), line("H3", 305)],
    )
    assert [(number, item["id"] if item else "") for number, item in rows] == [
        ("1", "H1"), ("2", ""), ("3", "H3"),
    ]


def test_competing_lines_do_not_reassign_to_second_nearest_point():
    rows = terminal_pair_rows(
        [point("a", 100), point("b", 200)],
        [line("far", 110), line("near", 98), line("other", 198)],
    )
    assert len(rows) == 3
    assert [(number, item["id"] if item else "") for number, item in rows] == [
        ("1", "near"), ("", "far"), ("2", "other"),
    ]


def test_crossing_polygon_projections_fall_back_to_box_centers():
    upper = {"id": "upper", "bbox": [100, 135, 200, 155],
             "polygon": [[100, 145], [200, 135], [200, 145], [100, 155]]}
    lower = {"id": "lower", "bbox": [100, 145, 200, 165],
             "polygon": [[100, 145], [200, 155], [200, 165], [100, 155]]}
    rows = terminal_pair_rows([point("a", 100), point("b", 200)], [lower, upper])
    assert [(number, item["id"] if item else "") for number, item in rows] == [
        ("1", "upper"), ("2", "lower"),
    ]


def test_excessive_polygon_extrapolation_uses_box_center():
    slanted = {"id": "slanted", "bbox": [100, 150, 200, 190],
               "polygon": [[100, 150], [200, 180], [200, 190], [100, 160]]}
    terminals = [point("a", 100), point("b", 200)]
    for terminal in terminals:
        terminal["x"] = 0
    rows = terminal_pair_rows(terminals, [slanted])
    assert [(number, item["id"] if item else "") for number, item in rows] == [
        ("1", ""), ("2", "slanted"),
    ]


def test_small_polygon_correction_can_resolve_boundary_ambiguity():
    slanted = {"id": "slanted", "bbox": [100, 139, 200, 159],
               "polygon": [[100, 149], [200, 139], [200, 149], [100, 159]]}
    rows = terminal_pair_rows([point("a", 100), point("b", 200)], [slanted])
    assert [(number, item["id"] if item else "") for number, item in rows] == [
        ("1", ""), ("2", "slanted"),
    ]


def test_equal_height_points_are_numbered_left_to_right():
    left, right = point("left", 100), point("right", 100)
    left["x"], right["x"] = 20, 80
    assert [number for number, _ in terminal_pair_rows([right, left], [])] == ["1", "2"]


def test_dedup_keeps_raw_points_unmodified_and_retains_adjacent_terminals():
    raw = [
        point("duplicate", 102, score=0.7, bbox=[40, 90, 60, 110]),
        point("winner", 100, score=0.95, bbox=[40, 90, 60, 110]),
        point("adjacent", 120, score=0.8, bbox=[40, 110, 60, 130]),
    ]
    effective = deduplicate_model_points(raw)
    assert [item["id"] for item in effective] == ["winner", "adjacent"]
    assert len(raw) == 3


def test_dedup_never_removes_manual_points_or_boxless_detections():
    first = point("first", 100)
    manual = {**point("manual", 100), "source": "manual"}
    assert len(deduplicate_model_points([first, manual])) == 2
