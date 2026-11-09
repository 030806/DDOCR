"""Reconcile saved business rows with the current point-to-OCR matching."""

from __future__ import annotations

from typing import Any


def _protected(record: dict[str, Any]) -> bool:
    return bool(record.get("manual") or record.get("manualConfirmed") or record.get("initialLinked"))


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
    """Seed position pairs once, then keep terminal rows and saved associations stable."""
    previous = {record["id"]: record for record in records}
    sources = sorted((item for item in items if not (item.get("attributes", {}).get("terminal_point_id")
                     and not item.get("display_text", "").strip())), key=lambda row: (
                         (row["bbox"][1] + row["bbox"][3]) / 2,
                         (row["bbox"][0] + row["bbox"][2]) / 2, str(row["id"])))
    active_sources = {item["id"] for item in sources}
    represented: set[str] = set()
    updated: list[dict[str, Any]] = []
    # Explicitly saved terminal links and independent manual OCR rows reserve
    # their sources before the old, unpaired documents are migrated.
    for old in records:
        source_id = old.get("sourceResultId")
        point_id = old.get("terminalPointId")
        if _protected(old) and source_id in active_sources and (point_id is None or point_id in active_point_ids):
            represented.add(source_id)

    unpaired = []
    for proposed in seed:
        point_id = proposed.get("terminalPointId")
        if point_id is None:
            continue
        old = previous.get(proposed["id"])
        if old and _protected(old):
            record = old.copy()
            if not old.get("manual") and not old.get("manualConfirmed"):
                record["terminalNumber"] = proposed.get("terminalNumber", record.get("terminalNumber", ""))
            if record.get("sourceResultId") and record["sourceResultId"] not in active_sources:
                record.update(sourceResultId=None, sourceRevision=0, cable="", manualConfirmed=False)
        elif not old:
            record = proposed.copy()
            if _protected(proposed) and not proposed.get("initialLinked"):
                if record.get("sourceResultId") in active_sources:
                    represented.add(record["sourceResultId"])
            else:
                record.update(sourceResultId=None, sourceRevision=0, cable="")
                unpaired.append(record)
        else:
            record = old.copy()
            record["terminalNumber"] = proposed.get("terminalNumber", record.get("terminalNumber", ""))
            unpaired.append(record)
        updated.append(record)

    available = (item for item in sources if item["id"] not in represented)
    for record in unpaired:
        source = next(available, None)
        record.update(sourceResultId=source["id"] if source else None,
                      sourceRevision=source.get("revision", 0) if source else 0,
                      cable=source.get("display_text", "") if source else "",
                      initialLinked=True)
        if source:
            represented.add(source["id"])

    # Orphaned point records remain available for review. Unassigned OCR rows
    # follow the fixed terminal rows in their own physical order.
    for old in records:
        point_id = old.get("terminalPointId")
        if point_id is not None and point_id not in active_point_ids:
            updated.append(old.copy())
        elif point_id is None and _protected(old) and (
            not old.get("sourceResultId") or old["sourceResultId"] in active_sources
        ):
            if old.get("sourceResultId") not in {r.get("sourceResultId") for r in updated}:
                updated.append(old.copy())

    for item in sources:
        source_id = item["id"]
        if source_id in represented:
            continue
        old = previous.get("ocr:" + source_id)
        record = old.copy() if old and _protected(old) else _unmatched_record(item)
        updated.append(record)
        represented.add(source_id)

    if updated == records:
        return False
    records[:] = updated
    return True
