"""Independent terminal business values, versioned at page/batch level."""
from copy import deepcopy
from datetime import datetime, UTC
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, insert, update
from sqlalchemy.orm import Session
from app.models.schema import terminal_documents, pages, results, ocr_jobs, corrections, users
from app.terminal_pair.document_records import reconcile_matches


def is_terminal_marker(item):
    text = item.get("display_text")
    if text is None:
        text = item.get("text") or ""
    return bool((item.get("attributes") or {}).get("terminal_point_id") and not str(text).strip())


def seeded_records(page, items):
    points = sorted(page.get("terminal_points") or [], key=lambda p: (p["y"], p["x"], str(p["id"])))
    sources = sorted((item for item in items if not is_terminal_marker(item)),
                     key=lambda item: ((item["bbox"][1] + item["bbox"][3]) / 2,
                                       (item["bbox"][0] + item["bbox"][2]) / 2, str(item["id"])))
    output = []
    for i, point in enumerate(points):
        source = sources[i] if i < len(sources) else None
        output.append({"id": "terminal:" + point["id"], "terminalPointId": point["id"],
                       "sourceResultId": source["id"] if source else None,
                       "terminalNumber": point.get("terminal_number") or str(i + 1),
                       "cable": source.get("display_text", "") if source else "", "manualConfirmed": False,
                       "tableNote": "", "manual": False, "initialLinked": True,
                       "sourceRevision": source.get("revision", 0) if source else 0})
    for item in sources[len(points):]:
        output.append({"id": "ocr:" + item["id"], "terminalPointId": None,
                       "sourceResultId": item["id"], "terminalNumber": "",
                       "cable": item.get("display_text", ""), "manualConfirmed": bool(item.get("manual_confirmed")),
                       "tableNote": item.get("table_note", ""),
                       "manual": bool(item.get("table_revision")),
                       "sourceRevision": item.get("revision", 0)})
    return output


def _manual_link_records(records, items, links):
    """Apply explicit one-to-one links, retaining independent OCR rows."""
    by_source = {item["id"]: item for item in items}
    old_unmatched = {r.get("sourceResultId"): r for r in records if r.get("terminalPointId") is None}
    linked = set(links.values())
    output = []
    for record in records:
        point_id = record.get("terminalPointId")
        if point_id is None:
            if not record.get("sourceResultId"):
                output.append(record.copy())
            continue
        row = record.copy()
        source_id = links.get(point_id)
        if row.get("sourceResultId") != source_id:
            source = by_source.get(source_id)
            row.update(sourceResultId=source_id, sourceRevision=source.get("revision", 0) if source else 0,
                       cable=source.get("display_text", "") if source else "", manualConfirmed=False)
        row["manual"] = True
        row["initialLinked"] = True
        output.append(row)
    from app.terminal_pair.document_records import _unmatched_record
    for item in items:
        if item["id"] not in linked and not is_terminal_marker(item):
            output.append(old_unmatched.get(item["id"], _unmatched_record(item)).copy())
    return output


class TerminalDocumentService:
    def __init__(self, core):
        self.core = core
        self.engine = core.store.engine

    def save_links(self, job_id, page_no, body, owner):
        page = self.context(job_id, page_no, owner)
        current = self.get(job_id, page_no, owner)
        points = {str(point["id"]) for point in page.get("terminal_points") or []}
        items = [self.core.public_result(self.core.result(rid)) for rid in page["result_ids"]
                 if self.core.result(rid).get("review_status") not in {"deleted", "false_positive"}]
        available = {item["id"] for item in items if not is_terminal_marker(item)}
        links = body.links
        if not set(links) <= points or not set(links.values()) <= available or len(set(links.values())) != len(links):
            raise HTTPException(422, "Links must uniquely reference active points and OCR results on this page")
        records = _manual_link_records(current["records"], items, links)
        with Session(self.engine) as db, db.begin():
            db.execute(update(ocr_jobs).where(ocr_jobs.c.id == job_id).values(result_version=ocr_jobs.c.result_version + 1))
            updated = db.execute(update(terminal_documents).where(
                terminal_documents.c.page_id == page["id"], terminal_documents.c.revision == body.base_revision
            ).values(records=records, revision=body.base_revision + 1))
            if not updated.rowcount:
                raise HTTPException(409, "Terminal links changed; reload before retry")
        return self.get(job_id, page_no, owner)

    def context(self, job_id, page_no, owner):
        job = self.core.job(job_id, owner)
        page = next((p for pid in job["page_ids"] if (p := self.core.page(pid)) and p["page_no"] == page_no), None)
        if page is None:
            raise HTTPException(404, "Page not found")
        from app.terminal_pair.numbering import page_with_workflow_numbers
        return page_with_workflow_numbers(page, self.core.store.get("terminal_workflow_snapshot", job_id))

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
        active_items = [self.core.public_result(self.core.result(rid)) for rid in page["result_ids"]
                        if self.core.result(rid).get("review_status") not in {"deleted", "false_positive"}]
        seed = seeded_records(page, active_items)
        active_point_ids = {str(point["id"]) for point in page.get("terminal_points") or []}
        if reconcile_matches(records, seed, active_items, active_point_ids):
            with Session(self.engine) as db, db.begin():
                changed = db.execute(update(terminal_documents).where(terminal_documents.c.page_id == page["id"],
                                     terminal_documents.c.revision == revision).values(records=records, revision=revision + 1))
                if not changed.rowcount:
                    raise HTTPException(409, "Terminal points changed; reload")
                revision += 1
        # Unconfirmed values follow subsequent source revisions, including manual edits and transfers.
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
                if not record.get("manualConfirmed") and not record["sourceUnavailable"] and record.get("sourceRevision", 0) != source["revision"]:
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

    def save(self, job_id, page_no, body, owner, source_updates=()):
        page = self.context(job_id, page_no, owner)
        before = self.get(job_id, page_no, owner)
        synced = []
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
                if not row or row["review_status"] in {"deleted", "false_positive"} or is_terminal_marker(row):
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
                        if body.sync_record_id == record["id"] or (not record.get("manualConfirmed")):
                            record["cable"] = source.text
                            record["sourceRevision"] = revision
                            if body.sync_record_id == record["id"]:
                                record["manualConfirmed"] = False
                                record["manual"] = True
            if len({u.result_id for u in source_updates}) != len(source_updates):
                raise HTTPException(422, 'Duplicate OCR source update')
            for source in source_updates:
                linked = [r for r in records if r.get('sourceResultId') == source.result_id]
                old_linked = [r for r in allowed.values() if r.get('sourceResultId') == source.result_id]
                if not linked or {r['id'] for r in linked} != {r['id'] for r in old_linked}:
                    raise HTTPException(422, 'Cannot change source associations during synchronization')
                if len(linked) > 1 and not source.allow_shared:
                    raise HTTPException(409, '该 OCR 来源被多行共用，请确认影响范围')
                row = db.execute(select(results).where(results.c.id == source.result_id, results.c.page_id == page['id'])).mappings().first()
                if not row or row['review_status'] in ('deleted','false_positive'):
                    raise HTTPException(422, 'OCR source unavailable')
                if row['current_revision'] != source.base_revision or row['table_revision'] != source.base_table_revision:
                    raise HTTPException(409, 'OCR 来源已变化，请重新加载核对')
                changes = {}
                revision, table_revision = row['current_revision'], row['table_revision']
                text = row['current_correction']['corrected_text'] if row['current_correction'] else row['text']
                if source.text is not None and source.text != text:
                    revision += 1
                    stamp = datetime.now(UTC)
                    correction = {'id':str(uuid4()), 'result_id':row['id'], 'corrected_text':source.text,
                                  'revision':revision, 'created_by':{'id':owner,'name':db.scalar(select(users.c.name).where(users.c.id==owner)) or ''},'created_at':stamp.isoformat()}
                    db.execute(insert(corrections).values(id=correction['id'],result_id=row['id'],corrected_text=source.text,
                        revision=revision,base_revision=row['current_revision'],user_id=owner,created_at=stamp))
                    changes.update(current_revision=revision,current_correction=correction)
                    text = source.text
                number = row['terminal_number']
                if source.terminal_number is not None and source.terminal_number != number:
                    table_revision += 1
                    number = source.terminal_number
                    changes.update(terminal_number=number,table_revision=table_revision)
                if changes: db.execute(update(results).where(results.c.id==row['id']).values(**changes))
                for record in linked:
                    if source.text is not None:
                        if source.propagate: record['cable']=text
                        record['sourceRevision']=revision
                    if source.terminal_number is not None and source.propagate: record['terminalNumber']=number
                    # An explicit undo snapshot must keep its values and source binding.
                    record['manual']=True
                synced.append({'result_id':row['id'],'text':text,'revision':revision,'terminal_number':number,'table_revision':table_revision})
            updated = db.execute(update(terminal_documents).where(terminal_documents.c.page_id == page["id"],
                                 terminal_documents.c.revision == body.base_revision).values(records=records, revision=body.base_revision + 1))
            if not updated.rowcount:
                raise HTTPException(409, "Terminal records changed")
        return {**self.get(job_id, page_no, owner), "correction": correction, "before": before, **({"sources": synced} if source_updates else {})}


def effective_records(db, page):
    """Read business values for export/merge without mutating OCR evidence."""
    doc = db.execute(select(terminal_documents).where(terminal_documents.c.page_id == page["id"])).mappings().first()
    from app.models.store import StoredObject
    from app.terminal_pair.numbering import page_with_workflow_numbers
    snapshot = db.get(StoredObject, ("terminal_workflow_snapshot", page["job_id"]))
    page = page_with_workflow_numbers(page, snapshot.data if snapshot else None)
    records = deepcopy(doc["records"]) if doc else []
    active = {p["id"] for p in page.get("terminal_points") or []}
    source_rows = db.execute(select(results).where(results.c.id.in_(page["result_ids"]))).mappings().all()
    by_id = {row["id"]: row for row in source_rows}
    items = []
    for result_id in page["result_ids"]:
        row = by_id.get(result_id)
        if not row or row["review_status"] in {"deleted", "false_positive"}:
            continue
        item = dict(row)
        item["attributes"] = row["attributes"] or {}
        item["display_text"] = row["current_correction"]["corrected_text"] if row["current_correction"] else row["text"]
        item["revision"] = row["current_revision"]
        items.append(item)
    if not doc:
        return seeded_records(page, items) if page.get('terminal_points') else None
    reconcile_matches(records, seeded_records(page, items), items, active)
    for r in records:
        rid = r.get("sourceResultId")
        source = db.execute(select(results).where(results.c.id == rid)).mappings().first() if rid else None
        if source and source["review_status"] not in {"deleted", "false_positive"} and not r.get("manualConfirmed") and r.get("sourceRevision", 0) != source["current_revision"]:
            r["cable"] = source["current_correction"]["corrected_text"] if source["current_correction"] else source["text"]
    return [r for r in records if r["terminalPointId"] is None or r["terminalPointId"] in active]
