"""Single source of truth for terminal matching, review and export."""
from collections import Counter
from datetime import datetime, UTC, timedelta
from hashlib import sha256
from io import BytesIO
import json
import re
from uuid import uuid4

from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy import select, insert, update, delete
from sqlalchemy.orm import Session

from app.models.schema import (terminal_tasks, terminal_sides, terminal_reviews,
                               terminal_events, users, ocr_jobs, pages, results, idempotency_records)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def merge_rows(sources, links, reviews):
    """Only unique nonempty terminal numbers are matched automatically."""
    by_side = {side: {r["id"]: r for r in sources.get(side, [])} for side in ("left", "right")}
    counts = {s: Counter(r["terminal_number"].strip() for r in rows.values()) for s, rows in by_side.items()}
    unique_right = {r["terminal_number"].strip(): r for r in by_side["right"].values()
                    if r["terminal_number"].strip() and counts["right"][r["terminal_number"].strip()] == 1}
    used = set()
    pairs = []
    for link in links:
        left = by_side["left"].get(link.get("left"))
        right = by_side["right"].get(link.get("right"))
        # A stale pair never silently becomes an intentional single-sided row.
        if (link.get("left") and not left) or (link.get("right") and not right):
            continue
        if not left and not right:
            continue
        pairs.append((left, right, True))
        used.update(r["id"] for r in (left, right) if r)
    for left in by_side["left"].values():
        if left["id"] in used:
            continue
        number = left["terminal_number"].strip()
        right = unique_right.get(number)
        if right and right["id"] in used:
            right = None
        if not number or counts["left"][number] != 1 or counts["right"][number] != 1:
            right = None
        pairs.append((left, right, False))
        used.update(r["id"] for r in (left, right) if r)
    pairs.extend((None, r, False) for r in by_side["right"].values() if r["id"] not in used)
    output = []
    for left, right, manual in pairs:
        number = (left or right)["terminal_number"].strip()
        conflict = not manual and any(r and (not r["terminal_number"].strip() or
            counts[s][r["terminal_number"].strip()] > 1) for s, r in (("left", left), ("right", right)))
        row_id = digest([left["id"] if left else None, right["id"] if right else None])
        fingerprint = digest([left, right, manual])
        previous = reviews.get(row_id)
        note = previous["note"] if previous else "；".join(
            f"{label}：{r['table_note']}" for label, r in (("左", left), ("右", right)) if r and r["table_note"])
        output.append({"id": row_id, "terminal_number": number, "left": left, "right": right,
                       "manual": manual, "conflict": conflict, "fingerprint": fingerprint,
                       "confirmed": bool(previous and previous["confirmed"] and previous["fingerprint"] == fingerprint and not conflict),
                       "note": note})
    def natural(row):
        return [(1, int(p)) if p.isdigit() else (0, p) for p in re.split(r"(\d+)", row["terminal_number"])]
    return sorted(output, key=natural)


class TerminalService:
    def __init__(self, core):
        self.engine = core.store.engine

    def task(self, db, task_id, owner, lock=False):
        query = select(terminal_tasks).where(terminal_tasks.c.id == task_id, terminal_tasks.c.user_id == owner,
                                             terminal_tasks.c.deleted_at.is_(None))
        row = db.execute(query.with_for_update() if lock else query).mappings().first()
        if not row:
            raise HTTPException(404, "端子排任务不存在")
        return dict(row)

    def state(self, db, task, lock=False):
        sides = {}
        sources = {}
        associations = db.execute(select(terminal_sides).where(terminal_sides.c.task_id == task["id"])).mappings().all()
        # Same order as OCR mutations; task lock is always acquired first here.
        jobs = {}
        for job_id in sorted({a["job_id"] for a in associations}):
            query = select(ocr_jobs).where(ocr_jobs.c.id == job_id, ocr_jobs.c.user_id == task["user_id"], ocr_jobs.c.tenant_id == task["tenant_id"])
            jobs[job_id] = db.execute(query.with_for_update() if lock else query).mappings().first()
        for association in associations:
            side = association["side"]
            job = jobs[association["job_id"]]
            available = bool(job and not job["deleted_at"])
            sides[side] = {"job_id": association["job_id"], "page_no": association["page_no"],
                           "status": job["status"] if available else "unavailable", "name": job["name"] if available else "来源已删除"}
            if not available:
                continue
            values = db.execute(select(results).where(results.c.job_id == job["id"], results.c.page_no == association["page_no"],
                results.c.review_status.notin_(["deleted", "false_positive"])).order_by(results.c.reading_order, results.c.id)).mappings()
            sources[side] = [{"id": r["id"], "job_id": r["job_id"], "page_no": r["page_no"],
                              "terminal_number": r["terminal_number"], "text": r["current_correction"]["corrected_text"] if r["current_correction"] else r["text"],
                              "table_note": r["table_note"], "revision": r["current_revision"],
                              "table_revision": r["table_revision"], "geometry_revision": r["geometry_revision"],
                              "review_status": r["review_status"]} for r in values]
        from app.services.terminal_document import effective_records
        for association in associations:
            page = db.execute(select(pages).where(pages.c.job_id == association["job_id"], pages.c.page_no == association["page_no"])).mappings().first()
            if page and association["side"] in sources:
                business = effective_records(db, page)
                if business is not None:
                    sources[association["side"]] = [{"id": r.get("sourceResultId") or r["id"], "job_id": association["job_id"], "page_no": association["page_no"],
                        "terminal_number": r["terminalNumber"], "text": r["cable"], "table_note": r["tableNote"],
                        "revision": 0, "table_revision": digest(r), "geometry_revision": 0, "review_status": "unreviewed"} for r in business]
        reviews = {r["row_id"]: r for r in db.execute(select(terminal_reviews).where(terminal_reviews.c.task_id == task["id"])).mappings()}
        rows = merge_rows(sources, task["links"], reviews)
        return {"id": task["id"], "name": task["name"], "revision": task["revision"], "created_at": task["created_at"],
                "sides": sides, "rows": rows, "version": digest([task["revision"], sides, rows])}

    def get(self, task_id, owner):
        with Session(self.engine) as db, db.begin():
            return self.state(db, self.task(db, task_id, owner, True), True)

    def listing(self, owner, offset=0, limit=50):
        with Session(self.engine) as db:
            tasks = db.execute(select(terminal_tasks).where(terminal_tasks.c.user_id == owner,
                                                           terminal_tasks.c.deleted_at.is_(None))
                               .order_by(terminal_tasks.c.created_at.desc(), terminal_tasks.c.id).offset(offset).limit(limit + 1)).mappings().all()
            output = []
            for task in tasks[:limit]:
                state = self.state(db, task)
                output.append({k: v for k, v in state.items() if k not in {"rows", "version"}} | {
                    "row_count": len(state["rows"]), "confirmed_count": sum(r["confirmed"] for r in state["rows"]),
                    "conflict_count": sum(r["conflict"] for r in state["rows"])})
            return {"items": output, "next_offset": offset + limit if len(tasks) > limit else None}

    def delete_task(self, task_id, owner, base_revision):
        now = datetime.now(UTC)
        with Session(self.engine) as db, db.begin():
            task = db.execute(select(terminal_tasks).where(terminal_tasks.c.id == task_id,
                terminal_tasks.c.user_id == owner).with_for_update()).mappings().first()
            if not task:
                raise HTTPException(404, "端子排任务不存在")
            if task["deleted_at"] is not None:
                return
            if task["revision"] != base_revision:
                raise HTTPException(409, "任务已更新，请刷新后重试")
            db.execute(update(terminal_tasks).where(terminal_tasks.c.id == task_id).values(
                deleted_at=now, revision=task["revision"] + 1, updated_at=now.isoformat()))
            db.execute(insert(terminal_events).values(id=str(uuid4()), task_id=task_id, user_id=owner,
                action="delete", snapshot={"name": task["name"], "base_revision": base_revision},
                created_at=now.isoformat()))

    def execute(self, action, task_id, body, owner, key=None):
        route = f"terminal/{task_id or 'new'}/{action}"
        now = datetime.now(UTC)
        with Session(self.engine) as db, db.begin():
            # Serializes idempotency checks even when creating the initial task.
            actor = db.execute(select(users).where(users.c.id == owner).with_for_update()).mappings().one()
            if key:
                previous = db.execute(select(idempotency_records).where(idempotency_records.c.user_id == owner,
                    idempotency_records.c.route == route, idempotency_records.c.key == key)).mappings().first()
                if previous:
                    if previous["request_hash"] != digest(body):
                        raise HTTPException(409, "幂等键对应的请求内容不同")
                    return previous["response_body"]
            if action == "create":
                task_id = str(uuid4())
                task = {"id": task_id, "user_id": owner, "tenant_id": actor["tenant_id"], "name": body["name"].strip(),
                        "revision": 0, "links": [], "created_at": now.isoformat(), "updated_at": now.isoformat()}
                if not task["name"]:
                    raise HTTPException(422, "请填写端子排名称")
                db.execute(insert(terminal_tasks).values(**task))
            else:
                task = self.task(db, task_id, owner, True)
                if task["revision"] != body["base_revision"]:
                    raise HTTPException(409, "任务已更新，请刷新后重试")
                state = self.state(db, task, action != "side")
                if action in {"review", "link", "export"} and body["version"] != state["version"]:
                    raise HTTPException(409, "识别结果已变化，请刷新后重新核对")
                if action == "side":
                    job = db.execute(select(ocr_jobs).where(ocr_jobs.c.id == body["job_id"], ocr_jobs.c.user_id == owner,
                        ocr_jobs.c.tenant_id == actor["tenant_id"], ocr_jobs.c.deleted_at.is_(None)).with_for_update()).mappings().first()
                    if not job:
                        raise HTTPException(404, "识别记录不存在")
                    if job["status"] not in {"succeeded", "partial_success"}:
                        raise HTTPException(409, "请等待识别完成后关联")
                    if not db.execute(select(pages.c.id).where(pages.c.job_id == job["id"], pages.c.page_no == body["page_no"])).first():
                        raise HTTPException(422, "所选页不存在")
                    if any(s != body["side"] and a["job_id"] == job["id"] and a["page_no"] == body["page_no"] for s, a in state["sides"].items()):
                        raise HTTPException(409, "同一识别页不能同时关联左右侧")
                    db.execute(delete(terminal_sides).where(terminal_sides.c.task_id == task_id, terminal_sides.c.side == body["side"]))
                    db.execute(insert(terminal_sides).values(task_id=task_id, side=body["side"], job_id=job["id"], page_no=body["page_no"]))
                    task["links"] = []
                    # Replacing a side always invalidates previous confirmations.
                    db.execute(update(terminal_reviews).where(terminal_reviews.c.task_id == task_id).values(confirmed=False))
                elif action == "review":
                    lookup = {r["id"]: r for r in state["rows"]}
                    for change in body["rows"]:
                        row = lookup.get(change["id"])
                        if not row or (change["confirmed"] and row["conflict"]):
                            raise HTTPException(409, "请先处理编号缺失或重复冲突")
                        db.execute(delete(terminal_reviews).where(terminal_reviews.c.task_id == task_id, terminal_reviews.c.row_id == row["id"]))
                        db.execute(insert(terminal_reviews).values(task_id=task_id, row_id=row["id"], fingerprint=row["fingerprint"],
                            confirmed=change["confirmed"], note=change["note"], updated_by=owner, updated_at=now.isoformat()))
                elif action == "link":
                    available = {s: {r[s]["id"] for r in state["rows"] if r[s]} for s in ("left", "right")}
                    chosen = {body[s] for s in ("left", "right") if body[s]}
                    if not chosen or any(body[s] and body[s] not in available[s] for s in ("left", "right")):
                        raise HTTPException(422, "请选择当前任务中的对应结果")
                    if any(body[s] and not next(r[s]["terminal_number"].strip() for r in state["rows"] if r[s] and r[s]["id"] == body[s]) for s in ("left", "right")):
                        raise HTTPException(422, "请先填写来源端子编号")
                    links = [p for p in task["links"] if not chosen.intersection({p.get("left"), p.get("right")})]
                    # Preserve deliberately detached partners as independent rows.
                    for row in state["rows"]:
                        if chosen.intersection({row[s]["id"] for s in ("left", "right") if row[s]}):
                            for side in ("left", "right"):
                                if row[side] and row[side]["id"] not in chosen:
                                    links.append({"left": None, "right": None, side: row[side]["id"]})
                    links.append({s: body[s] for s in ("left", "right")})
                    # De-duplicate old single-side overrides before applying new ones.
                    unique = []
                    seen = set()
                    for link in reversed(links):
                        ids = {v for v in link.values() if v}
                        if not ids.intersection(seen):
                            unique.append(link)
                            seen.update(ids)
                    task["links"] = list(reversed(unique))
                    db.execute(update(terminal_reviews).where(terminal_reviews.c.task_id == task_id).values(confirmed=False))
                elif action == "export":
                    if any(r["conflict"] for r in state["rows"]):
                        raise HTTPException(409, "请先解决编号缺失或匹配冲突")
                    if any(s["status"] == "unavailable" for s in state["sides"].values()):
                        raise HTTPException(409, "来源已删除，请重新关联")
                    selected = [r for r in state["rows"] if body["scope"] == "all" or r["confirmed"]]
                    if not selected:
                        raise HTTPException(422, "没有可导出的结果")
                    export_id = str(uuid4())
                    snapshot = {"name": task["name"], "version": state["version"], "rows": selected}
                    db.execute(insert(terminal_events).values(id=export_id, task_id=task_id, user_id=owner,
                        action="export", snapshot=snapshot, created_at=now.isoformat()))
                    value = {"id": export_id, "download_url": f"/api/v1/terminal-tasks/{task_id}/exports/{export_id}"}
                if action != "export":
                    task["revision"] += 1
                    db.execute(update(terminal_tasks).where(terminal_tasks.c.id == task_id).values(
                        revision=task["revision"], links=task["links"], updated_at=now.isoformat()))
            if action != "export":
                value = self.state(db, task)
                db.execute(insert(terminal_events).values(id=str(uuid4()), task_id=task_id, user_id=owner,
                    action=action, snapshot=body, created_at=now.isoformat()))
            if key:
                db.execute(insert(idempotency_records).values(id=str(uuid4()), user_id=owner, route=route, key=key,
                    request_hash=digest(body), response_status=200, response_body=value, expires_at=now + timedelta(days=1)))
            return value

    def download(self, task_id, export_id, owner):
        with Session(self.engine) as db:
            self.task(db, task_id, owner)
            event = db.execute(select(terminal_events).where(terminal_events.c.id == export_id,
                terminal_events.c.task_id == task_id, terminal_events.c.action == "export")).mappings().first()
            if not event:
                raise HTTPException(404, "导出不存在")
            snapshot = event["snapshot"]
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "端子排结果"
        sheet.append(["序号", "端子编号", "左侧线缆号", "右侧线缆号", "人工确认", "备注"])
        for index, row in enumerate(snapshot["rows"], 1):
            sheet.append([index, row["terminal_number"], row["left"]["text"] if row["left"] else "",
                          row["right"]["text"] if row["right"] else "", "是" if row["confirmed"] else "否", row["note"]])
            # OCR/user content must remain literal Excel strings, including '='.
            for cell in sheet[sheet.max_row][1:]:
                cell.data_type = "s"
        for column, width in zip("ABCDEF", [8, 22, 30, 30, 12, 50]):
            sheet.column_dimensions[column].width = width
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        stream = BytesIO()
        workbook.save(stream)
        return stream.getvalue()
