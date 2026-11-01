from app.terminal_pair.document_records import reconcile_matches
from app.terminal_pair.match import terminal_pair_rows


def point(identifier, y):
    return {"id": identifier, "x": 100, "y": y}


def item(identifier, y):
    return {
        "id": identifier, "bbox": [300, y - 5, 400, y + 5],
        "display_text": identifier, "revision": 0,
        "attributes": {}, "terminal_number": "", "manual_confirmed": False,
        "table_note": "", "current_correction": None,
    }


def seeded_records(page, items):
    points = page["terminal_points"]
    pairs = terminal_pair_rows(points, items)
    matched = [source for number, source in pairs if number]
    seed = []
    for index, terminal in enumerate(points, 1):
        source = matched[index - 1]
        seed.append({
            "id": "terminal:" + terminal["id"], "terminalPointId": terminal["id"],
            "sourceResultId": source["id"] if source else None,
            "terminalNumber": str(index), "cable": source["display_text"] if source else "",
            "manualConfirmed": False, "tableNote": "", "manual": False,
            "sourceRevision": source["revision"] if source else 0,
        })
    assigned = {source["id"] for source in matched if source}
    for source in items:
        if source["id"] in assigned:
            continue
        seed.append({
            "id": "ocr:" + source["id"], "terminalPointId": None,
            "sourceResultId": source["id"], "terminalNumber": "",
            "cable": source["display_text"], "manualConfirmed": False,
            "tableNote": "", "manual": False, "sourceRevision": source["revision"],
        })
    return seed


def reconcile(records, points, items):
    seed = seeded_records({"terminal_points": points}, items)
    return reconcile_matches(records, seed, items, {p["id"] for p in points})


def by_point(records, identifier):
    return next(row for row in records if row["terminalPointId"] == identifier)


def by_source(records, identifier):
    return next(row for row in records if row["sourceResultId"] == identifier)


def test_new_source_rematches_existing_automatic_terminal_row():
    points = [point("a", 100), point("b", 200)]
    old = item("old", 112)
    records = seeded_records({"terminal_points": points}, [old])
    fresh = item("fresh", 99)
    assert reconcile(records, points, [old, fresh])
    assert by_point(records, "a")["sourceResultId"] == "fresh"
    assert by_point(records, "b")["sourceResultId"] is None
    assert by_source(records, "old")["terminalPointId"] is None
    assert not reconcile(records, points, [old, fresh])


def test_saved_unmatched_source_moves_into_new_terminal_match():
    points = [point("a", 100)]
    first = item("first", 100)
    second = item("second", 200)
    records = seeded_records({"terminal_points": points}, [first, second])
    assert by_source(records, "second")["terminalPointId"] is None
    points.append(point("b", 200))
    assert reconcile(records, points, [first, second])
    assert by_point(records, "b")["sourceResultId"] == "second"
    assert not any(row["id"] == "ocr:second" for row in records)


def test_inserting_terminal_point_renumbers_unedited_rows():
    points = [point("a", 100), point("b", 200)]
    first, second = item("first", 100), item("second", 200)
    records = seeded_records({"terminal_points": points}, [first, second])
    points.insert(0, point("top", 50))
    assert reconcile(records, points, [first, second])
    assert [(by_point(records, key)["terminalNumber"], by_point(records, key)["sourceResultId"])
            for key in ("top", "a", "b")] == [("1", None), ("2", "first"), ("3", "second")]


def test_moving_detection_box_reassigns_automatic_rows():
    points = [point("a", 100), point("b", 200)]
    old = item("moving", 100)
    records = seeded_records({"terminal_points": points}, [old])
    assert reconcile(records, points, [item("moving", 200)])
    assert by_point(records, "a")["sourceResultId"] is None
    assert by_point(records, "b")["sourceResultId"] == "moving"


def test_manual_business_row_keeps_value_and_source_is_not_duplicated():
    points = [point("a", 100), point("b", 200)]
    old, fresh = item("old", 100), item("fresh", 200)
    records = seeded_records({"terminal_points": points}, [old, fresh])
    manual = by_point(records, "a")
    manual.update(cable="人工值", manual=True)
    moved = item("old", 200)
    reconcile(records, points, [moved, fresh])
    assert by_point(records, "a")["cable"] == "人工值"
    assert by_point(records, "a")["sourceResultId"] == "old"
    assert by_point(records, "b")["sourceResultId"] == "fresh"
    assert sum(row["sourceResultId"] == "old" for row in records) == 1


def test_removed_automatic_source_does_not_remain_in_current_table():
    points = [point("a", 100)]
    old, extra = item("old", 100), item("extra", 200)
    records = seeded_records({"terminal_points": points}, [old, extra])
    assert reconcile(records, points, [])
    assert by_point(records, "a")["cable"] == ""
    assert not any(row["sourceResultId"] == "extra" for row in records)


def test_deleted_source_disappears_even_from_manually_edited_terminal_row():
    points = [point("a", 100)]
    records = seeded_records({"terminal_points": points}, [item("old", 100)])
    records[0].update(cable="人工修改", manual=True, manualConfirmed=True)
    assert reconcile(records, points, [])
    assert by_point(records, "a")["sourceResultId"] is None
    assert by_point(records, "a")["cable"] == ""
    assert by_point(records, "a")["manual"] is False
    assert by_point(records, "a")["manualConfirmed"] is False


def test_deleted_manual_source_allows_remaining_line_to_match_terminal():
    points = [point("a", 100)]
    old, remaining = item("old", 100), item("remaining", 110)
    records = seeded_records({"terminal_points": points}, [old, remaining])
    by_point(records, "a").update(cable="人工修改", manual=True)
    assert reconcile(records, points, [remaining])
    assert by_point(records, "a")["sourceResultId"] == "remaining"
    assert by_point(records, "a")["cable"] == "remaining"
    assert not any(row["sourceResultId"] == "old" for row in records)


def test_deleted_source_removes_manually_edited_unmatched_row():
    points = [point("a", 100)]
    records = seeded_records({"terminal_points": points}, [item("first", 100), item("extra", 200)])
    by_source(records, "extra").update(cable="人工修改", manual=True)
    assert reconcile(records, points, [item("first", 100)])
    assert not any(row["sourceResultId"] == "extra" or row["id"] == "ocr:extra" for row in records)


def test_first_load_keeps_legacy_manual_business_value_without_source():
    proposed = {
        "id": "terminal:a", "terminalPointId": "a", "sourceResultId": None,
        "terminalNumber": "1", "cable": "人工补录", "manualConfirmed": False,
        "tableNote": "", "manual": True, "sourceRevision": 0,
    }
    records = []
    assert reconcile_matches(records, [proposed], [], {"a"})
    assert records[0]["cable"] == "人工补录"
