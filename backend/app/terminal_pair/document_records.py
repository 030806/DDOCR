"""Reconcile saved business rows with the current point-to-OCR matching."""

from __future__ import annotations

from typing import Any


def _protected(record: dict[str, Any]) -> bool:
    return bool(record.get("manual") or record.get("manualConfirmed"))


def _unmatched_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "ocr:" + item["id"], "terminalPointId": None,
        "sourceResultId": item["id"], "terminalNumber": "",
        "cable": item.get("display_text", ""),
        "manualConfirmed": bool(item.get("manual_confirmed")),
        "tableNote": item.get("table_note", ""),
        "manual": bool(item.get("table_revision")),
        "sourceRevision": item.get("revision", 0),
    }


def reconcile_matches(
    records: list[dict[str, Any]],
    seed: list[dict[str, Any]],
    items: list[dict[str, Any]],
    active_point_ids: set[str],
) -> bool:
    """Rematch automatic rows, while retaining explicit business edits.

    The seed is recalculated from the current point and OCR geometry on every
    read. A new OCR box may displace an old match; the displaced source remains
    visible as an unnumbered row. Manually edited rows keep their association
    while their source is active. Deleting a source removes its line from the
    table, including a manually edited business value linked to that source.
    """
    previous = {record["id"]: record for record in records}
    active_sources = {item["id"] for item in items}
    locked_sources = {
        record["sourceResultId"] for record in records
        if _protected(record) and record.get("sourceResultId") in active_sources
        and (record.get("terminalPointId") is None
             or record["terminalPointId"] in active_point_ids)
    }
    represented: set[str] = set()
    updated: list[dict[str, Any]] = []

    for proposed in seed:
        point_id = proposed.get("terminalPointId")
        if point_id is None:
            continue
        old = previous.get(proposed["id"])
        source_removed = bool(old and old.get("sourceResultId")
                              and old["sourceResultId"] not in active_sources)
        if (old and _protected(old) and not source_removed) or (not old and _protected(proposed)):
            record = (old or proposed).copy()
            if record.get("sourceResultId") in active_sources:
                represented.add(record["sourceResultId"])
        else:
            record = old.copy() if old else proposed.copy()
            source_id = proposed.get("sourceResultId")
            if source_id in locked_sources or source_id in represented:
                source_id = None
            record.update(
                terminalNumber=proposed.get("terminalNumber", record.get("terminalNumber", "")),
                sourceResultId=source_id,
                sourceRevision=proposed.get("sourceRevision", 0) if source_id else 0,
                cable=proposed.get("cable", "") if source_id else "",
            )
            if source_removed:
                record.update(manual=False, manualConfirmed=False)
            if source_id:
                represented.add(source_id)
        updated.append(record)

    # Keep manually edited unnumbered rows and deleted-point records. Automatic
    # unmatched rows are rebuilt below, so they can move into a terminal row.
    for old in records:
        point_id = old.get("terminalPointId")
        if point_id is not None and point_id not in active_point_ids:
            updated.append(old.copy())
        elif point_id is None and _protected(old) and (
            not old.get("sourceResultId") or old["sourceResultId"] in active_sources
        ):
            updated.append(old.copy())
            if old.get("sourceResultId") in active_sources:
                represented.add(old["sourceResultId"])

    for item in sorted(items, key=lambda row: (
        (row["bbox"][1] + row["bbox"][3]) / 2,
        (row["bbox"][0] + row["bbox"][2]) / 2,
        str(row["id"]),
    )):
        source_id = item["id"]
        if source_id in represented or (item.get("attributes", {}).get("terminal_point_id") and not item.get("display_text", "").strip()):
            continue
        old = previous.get("ocr:" + source_id)
        record = old.copy() if old and _protected(old) else _unmatched_record(item)
        updated.append(record)
        represented.add(source_id)

    if updated == records:
        return False
    records[:] = updated
    return True
