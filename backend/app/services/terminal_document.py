"""Independent terminal business values, versioned at page/batch level."""
from copy import deepcopy
from datetime import datetime, UTC
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, insert, update
from sqlalchemy.orm import Session
from app.models.schema import terminal_documents, pages, results, ocr_jobs, corrections, users
from app.terminal_pair.match import terminal_pair_rows


def seeded_records(page, items):
    points = sorted(page.get("terminal_points") or [], key=lambda p: (p["y"], p["x"], str(p["id"])))
    pairs = terminal_pair_rows(points, items)
    matched = [item for number, item in pairs if number]
    output = []
    for i, point in enumerate(points):
        item = matched[i] if i < len(matched) else None
        legacy = bool(item and item.get("attributes", {}).get("terminal_point_id"))
        output.append({"id": "terminal:" + point["id"], "terminalPointId": point["id"],
                       "sourceResultId": item["id"] if item and not legacy else None,
                       "terminalNumber": (item or {}).get("terminal_number") or str(i + 1),
                       "cable": (item or {}).get("display_text", ""),
                       "manualConfirmed": bool((item or {}).get("manual_confirmed")),
                       "tableNote": (item or {}).get("table_note", ""),
                       "manual": legacy or bool(item and (item.get("current_correction") or item.get("table_revision"))),
                       "sourceRevision": (item or {}).get("revision", 0)})
    represented = {item["id"] for item in matched if item}
    for item in items:
        if item["id"] in represented or item.get("attributes", {}).get("terminal_point_id"):
            continue
        output.append({"id": "ocr:" + item["id"], "terminalPointId": None,
                       "sourceResultId": item["id"], "terminalNumber": item.get("terminal_number") or "",
                       "cable": item.get("display_text", ""), "manualConfirmed": bool(item.get("manual_confirmed")),
                       "tableNote": item.get("table_note", ""),
                       "manual": bool(item.get("current_correction") or item.get("table_revision")),
                       "sourceRevision": item.get("revision", 0)})
    return output


class TerminalDocumentService:
    def __init__(self, core):
        self.core = core
        self.engine = core.store.engine

    def context(self, job_id, page_no, owner):
        job = self.core.job(job_id, owner)
        page = next((p for pid in job["page_ids"] if (p := self.core.page(pid)) and p["page_no"] == page_no), None)
        if page is None:
            raise HTTPException(404, "Page not found")
        return page

    def get(self, job_id, page_no, owner):
        page = self.context(job_id, page_no, owner)
        with Session(self.engine) as db, db.begin():
            db.execute(update(ocr_jobs).where(ocr_jobs.c.id == job_id).values(result_version=ocr_jobs.c.result_version))
            doc = db.execute(select(terminal_documents).where(terminal_documents.c.page_id == page["id"])).mappings().first()
            if doc:
                records, revision = deepcopy(doc["records"]), doc["revision"]
            else:
                records = seeded_records(page, [self.core.public_result(self.core.result(rid)) for rid in page["result_ids"]
                                                if self.core.result(rid).get("review_status") not in {"deleted", "false_positive"}])
                revision = 0
                db.execute(insert(terminal_documents).values(page_id=page["id"], revision=0, records=records))
        seed = seeded_records(page, [self.core.public_result(self.core.result(rid)) for rid in page["result_ids"]
                                    if self.core.result(rid).get("review_status") not in {"deleted", "false_positive"}])
        existing_ids = {r["id"] for r in records}
        represented = {r.get("sourceResultId") for r in records if r.get("sourceResultId")}
        additions = [r for r in seed if r["id"] not in existing_ids and (r["terminalPointId"] is not None or r.get("sourceResultId") not in represented)]
        if additions:
            records.extend(additions)
            with Session(self.engine) as db, db.begin():
                changed = db.execute(update(terminal_documents).where(terminal_documents.c.page_id == page["id"],
                                     terminal_documents.c.revision == revision).values(records=records, revision=revision + 1))
                if not changed.rowcount:
                    raise HTTPException(409, "Terminal points changed; reload")
                revision += 1
        # Suggestions track source changes only until the user has edited/confirmed the record.
        active = {p["id"] for p in page.get("terminal_points") or []}
        refreshed = False
        for record in records:
            record["orphaned"] = record["terminalPointId"] is not None and record["terminalPointId"] not in active
            rid = record.get("sourceResultId")
            source = self.core.result_repository.get(rid) if rid else None
            record["sourceUnavailable"] = bool(rid and (not source or source.get("review_status") in {"deleted", "false_positive"}))
            if source:
                public = self.core.public_result(source)
                record["sourceChanged"] = record.get("sourceRevision", 0) != source["revision"]
                record["sourceText"] = public["display_text"]
                record["currentSourceRevision"] = source["revision"]
                if not record.get("manual") and not record.get("manualConfirmed") and not record["sourceUnavailable"]:
                    refreshed = refreshed or record.get("sourceRevision", 0) != source["revision"] or record["cable"] != public["display_text"]
                    record["cable"] = public["display_text"]
                    record["sourceRevision"] = source["revision"]
        if refreshed:
            with Session(self.engine) as db, db.begin():
                db.execute(update(ocr_jobs).where(ocr_jobs.c.id == job_id).values(result_version=ocr_jobs.c.result_version + 1))
                updated = db.execute(update(terminal_documents).where(terminal_documents.c.page_id == page["id"], terminal_documents.c.revision == revision).values(records=records, revision=revision + 1))
                if not updated.rowcount:
                    raise HTTPException(409, "Source suggestions changed; reload")
                revision += 1
        return {"revision": revision, "records": records}

    def save(self, job_id, page_no, body, owner):
        page = self.context(job_id, page_no, owner)
        before = self.get(job_id, page_no, owner)
        with Session(self.engine) as db, db.begin():
            # Serialize both business and OCR changes on the job lock.
            db.execute(update(ocr_jobs).where(ocr_jobs.c.id == job_id).values(result_version=ocr_jobs.c.result_version + 1))
            doc = db.execute(select(terminal_documents).where(terminal_documents.c.page_id == page["id"])).mappings().one()
            if doc["revision"] != body.base_revision:
                raise HTTPException(409, "Terminal records changed; reload before retry")
            records = deepcopy(body.records)
            if any(not isinstance(r.get("id"), str) for r in records):
                raise HTTPException(422, "Every record requires an identity")
            if body.sync_record_id and not body.source:
                raise HTTPException(422, "Sync requires a source correction")
            allowed = {r["id"]: r for r in doc["records"]}
            if len(records) != len(allowed) or {r["id"] for r in records} != set(allowed):
                raise HTTPException(422, "Record identities cannot be changed")
            for record in records:
                original = allowed[record["id"]]
                for key in ("terminalPointId",):
                    if record.get(key) != original.get(key):
                        raise HTTPException(422, "Source association cannot be changed by a value edit")
            if any(not isinstance(r.get("manual"), bool) or not isinstance(r.get("manualConfirmed"), bool)
                   or any(not isinstance(r.get(k), str) or len(r[k]) > limit for k, limit in
                          (("terminalNumber", 500), ("cable", 500), ("tableNote", 1000))) for r in records):
                raise HTTPException(422, "Invalid terminal record values")
            if body.sync_record_id and not any(r["id"] == body.sync_record_id and r.get("sourceResultId") == body.source.result_id for r in records):
                raise HTTPException(422, "Sync target must reference the corrected source")
            for record in records:
                source_id = record.get("sourceResultId")
                if source_id:
                    source_row = db.execute(select(results.c.id).where(results.c.id == source_id, results.c.page_id == page["id"])).first()
                    if source_row is None:
                        raise HTTPException(422, "Source must belong to the same page")
            correction = None
            if body.source:
                source = body.source
                row = db.execute(select(results).where(results.c.id == source.result_id, results.c.page_id == page["id"])).mappings().first()
                if not row or row["review_status"] in {"deleted", "false_positive"} or (row["attributes"] or {}).get("terminal_point_id"):
                    raise HTTPException(422, "Source is unavailable")
                if row["current_revision"] != source.base_revision:
                    raise HTTPException(409, "OCR source changed; reload before retry")
                revision = row["current_revision"] + 1
                now = datetime.now(UTC)
                correction = {"id": str(uuid4()), "result_id": source.result_id, "corrected_text": source.text,
                              "revision": revision, "created_by": {"id": owner, "name": db.scalar(select(users.c.name).where(users.c.id == owner)) or ""}, "created_at": now.isoformat()}
                db.execute(insert(corrections).values(id=correction["id"], result_id=source.result_id, corrected_text=source.text,
                           revision=revision, base_revision=source.base_revision, user_id=owner, created_at=now))
                db.execute(update(results).where(results.c.id == source.result_id).values(current_revision=revision, current_correction=correction))
                for record in records:
                    if record.get("sourceResultId") == source.result_id:
                        if body.sync_record_id == record["id"] or (not record.get("manual") and not record.get("manualConfirmed")):
                            record["cable"] = source.text
                            record["sourceRevision"] = revision
                            if body.sync_record_id == record["id"]:
                                record["manualConfirmed"] = False
                                record["manual"] = True
            updated = db.execute(update(terminal_documents).where(terminal_documents.c.page_id == page["id"],
                                 terminal_documents.c.revision == body.base_revision).values(records=records, revision=body.base_revision + 1))
            if not updated.rowcount:
                raise HTTPException(409, "Terminal records changed")
        return {**self.get(job_id, page_no, owner), "correction": correction, "before": before}


def effective_records(db, page):
    """Read business values for export/merge without mutating OCR evidence."""
    doc = db.execute(select(terminal_documents).where(terminal_documents.c.page_id == page["id"])).mappings().first()
    if not doc:
        return None
    records = deepcopy(doc["records"])
    active = {p["id"] for p in page.get("terminal_points") or []}
    for r in records:
        rid = r.get("sourceResultId")
        source = db.execute(select(results).where(results.c.id == rid)).mappings().first() if rid else None
        if source and source["review_status"] not in {"deleted", "false_positive"} and not r.get("manual") and not r.get("manualConfirmed"):
            r["cable"] = source["current_correction"]["corrected_text"] if source["current_correction"] else source["text"]
    return [r for r in records if r["terminalPointId"] is None or r["terminalPointId"] in active]
