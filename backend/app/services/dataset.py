"""Task-level human review and versioned incremental OCR dataset collection."""
from datetime import datetime, UTC, timedelta
from contextlib import nullcontext
import hashlib
import json
from io import BytesIO
import math
import errno
import logging
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from app.models.schema import dataset_images, dataset_reviews, idempotency_records, ocr_jobs, results, pages
from app.services.dataset_files import DatasetFiles

logger = logging.getLogger(__name__)


def normalized_points(polygon, bbox, width, height):
    if polygon is None:
        x1, y1, x2, y2 = bbox
        polygon = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    if len(polygon) != 4 or any(len(p) != 2 for p in polygon):
        raise HTTPException(422, "标注必须包含四个二维坐标点")
    if any(not math.isfinite(v) for p in polygon for v in p):
        raise HTTPException(422, "标注坐标必须是有限数字")
    points = [[round(x), round(y)] for x, y in polygon]
    if any(not (0 <= x <= width and 0 <= y <= height) for x, y in points):
        raise HTTPException(422, "标注框超出原图范围")
    cross = []
    for i in range(4):
        a, b, c = points[i], points[(i+1) % 4], points[(i+2) % 4]
        cross.append((b[0]-a[0])*(c[1]-b[1]) - (b[1]-a[1])*(c[0]-b[0]))
    if not (all(v > 0 for v in cross) or all(v < 0 for v in cross)):
        raise HTTPException(422, "标注框存在自交、重复点或退化，请调整后复核")
    if cross[0] < 0:
        points.reverse()
    start = min(range(4), key=lambda i: (sum(points[i]), points[i][1], points[i][0]))
    return points[start:] + points[:start]


class DatasetService:
    def __init__(self, core):
        self.core = core
        self.engine = core.store.engine
        self.files = DatasetFiles(core.store.root)

    def execute(self, action, job_id, payload, owner, key=None):
        self.core.job(job_id, owner)
        route = f"/ocr/jobs/{job_id}/{action}"
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.files.locked():
            self.recover_publications()
            if key:
                with Session(self.engine) as db:
                    previous = db.execute(select(idempotency_records).where(idempotency_records.c.user_id == owner, idempotency_records.c.route == route, idempotency_records.c.key == key, idempotency_records.c.expires_at > datetime.now(UTC))).mappings().first()
                    if previous:
                        if previous["request_hash"] != digest:
                            raise HTTPException(409, "幂等键已用于其他请求")
                        return previous["response_body"]
            value = self.review(job_id, payload["expected_results"], owner, locked=True) if action == "review-completion" else self.save(job_id, payload["reviewed_version"], owner, locked=True)
            if key:
                with Session(self.engine) as db, db.begin():
                    db.execute(delete(idempotency_records).where(idempotency_records.c.user_id == owner, idempotency_records.c.route == route, idempotency_records.c.key == key))
                    db.execute(insert(idempotency_records).values(id=str(uuid4()), user_id=owner, route=route, key=key, request_hash=digest, response_status=200, response_body=value, expires_at=datetime.now(UTC) + timedelta(hours=24)))
            return value

    def recover_publications(self):
        """Reconcile committed directories before any later review/publication.

        This also prevents another task overwriting an unacknowledged commit
        using the catalogue revision that existed before a process crash.
        """
        with Session(self.engine) as db, db.begin():
            for image_id, commit in self.files.publication().items():
                image = db.execute(select(dataset_images).where(dataset_images.c.image_id == image_id)).mappings().first()
                if image and image["revision"] < commit["revision"]:
                    db.execute(update(dataset_images).where(dataset_images.c.image_id == image_id).values(revision=commit["revision"], job_id=commit["job_id"], saved_version=commit["saved_version"]))
                    db.execute(update(dataset_reviews).where(dataset_reviews.c.job_id == commit["job_id"], dataset_reviews.c.reviewed_version == commit["saved_version"]).values(saved_version=commit["saved_version"], image_revision=commit["revision"], last_error=None))

    def source(self, job, owner):
        uploaded = self.core.file(job["file_id"], owner)
        try:
            content = self.core.content_path(uploaded).read_bytes()
            with Image.open(BytesIO(content)) as image:
                image.load()
                extension = {"PNG": "png", "JPEG": "jpg", "BMP": "bmp", "WEBP": "webp", "TIFF": "tif"}.get(image.format)
                if not extension or getattr(image, "n_frames", 1) != 1:
                    raise HTTPException(422, "当前数据集仅支持单帧图片")
                width, height = image.size
        except (OSError, UnidentifiedImageError) as exc:
            raise HTTPException(422, "原图无法读取，暂不支持 PDF 入库") from exc
        return uploaded, content, extension, width, height

    def statuses(self, job_ids, owner):
        if not job_ids:
            return []
        with Session(self.engine) as db:
            jobs = db.execute(select(ocr_jobs).where(ocr_jobs.c.id.in_(job_ids), ocr_jobs.c.user_id == owner, ocr_jobs.c.deleted_at.is_(None))).mappings().all()
            if len(jobs) != len(set(job_ids)):
                raise HTTPException(404, "任务不存在")
            reviews = {r["job_id"]: r for r in db.execute(select(dataset_reviews).where(dataset_reviews.c.job_id.in_(job_ids))).mappings()}
            images = {r["sha256"]: r for r in db.execute(select(dataset_images).where(dataset_images.c.owner_id == owner, dataset_images.c.sha256.in_([r["source_sha256"] for r in reviews.values()]))).mappings()}
            output = []
            for job in jobs:
                review = reviews.get(job["id"])
                image = images.get(review["source_sha256"]) if review else None
                current = bool(review and review["reviewed_version"] == job["result_version"])
                saved = bool(current and image and image["job_id"] == job["id"] and image["saved_version"] == review["reviewed_version"] and review["saved_version"] == review["reviewed_version"])
                if current and image and not saved and image["revision"] != review["image_revision"]:
                    current = False
                state = "saved" if saved else ("failed" if review["last_error"] else "reviewed") if current else "unreviewed"
                output.append({"job_id": job["id"], "state": state, "result_version": job["result_version"], "reviewed_version": review["reviewed_version"] if review else None, "reviewed_at": review["reviewed_at"] if review else None, "saved_version": review["saved_version"] if review else None, "image_id": image["image_id"] if image else None, "last_error": review["last_error"] if review else None})
            return output

    def review(self, job_id, expected_results, owner, *, locked=False):
        job = self.core.job(job_id, owner)
        if job["status"] not in {"succeeded", "partial_success"}:
            raise HTTPException(409, "请等待识别任务完成")
        uploaded, content, extension, width, height = self.source(job, owner)
        digest = hashlib.sha256(content).hexdigest()
        with (nullcontext() if locked else self.files.locked()), Session(self.engine) as db, db.begin():
            # Result mutation transactions acquire this job lock before writing.
            current_job = db.execute(select(ocr_jobs).where(ocr_jobs.c.id == job_id).with_for_update()).mappings().one()
            rows = db.execute(select(results).where(results.c.job_id == job_id).order_by(results.c.page_no, results.c.reading_order, results.c.id)).mappings().all()
            actual = [{"id": r["id"], "revision": r["current_revision"], "geometry_revision": r["geometry_revision"], "review_status": r["review_status"]} for r in rows]
            if sorted(actual, key=lambda r: r["id"]) != sorted(expected_results, key=lambda r: r["id"]):
                raise HTTPException(409, "任务结果已变化，请刷新后重新复核")
            page_rows = db.execute(select(pages).where(pages.c.job_id == job_id)).mappings().all()
            if len(page_rows) != 1 or any((p["image"]["width_px"], p["image"]["height_px"]) != (width, height) for p in page_rows):
                raise HTTPException(422, "页面与原图尺寸不一致，无法保存训练坐标")
            annotations = []
            for row in rows:
                if row["review_status"] in {"deleted", "false_positive"}:
                    continue
                correction = row["current_correction"]
                text = correction["corrected_text"] if correction is not None else row["text"]
                if not text.strip() or text.strip() == "###" or any(c in text for c in "\t\r\n"):
                    raise HTTPException(422, "请填写全部有效框的文字，不允许空白、###、TAB 或换行")
                annotations.append({"transcription": text, "points": normalized_points(row["polygon"], row["bbox"], width, height), "ignore": False})
            image = db.execute(select(dataset_images).where(dataset_images.c.owner_id == owner, dataset_images.c.sha256 == digest)).mappings().first()
            now = datetime.now(UTC).isoformat()
            if not image:
                inserted = db.execute(insert(dataset_images).values(owner_id=owner, sha256=digest, revision=0))
                sequence = inserted.inserted_primary_key[0]
                if sequence > 999999:
                    raise HTTPException(409, "数据集编号容量已满")
                image_id = f"INC_{datetime.now(UTC):%Y%m%d}_{sequence:06d}"
                db.execute(update(dataset_images).where(dataset_images.c.sequence == sequence).values(image_id=image_id))
                image = {"image_id": image_id, "revision": 0}
            existing = db.execute(select(dataset_reviews).where(dataset_reviews.c.job_id == job_id)).mappings().first()
            # Repeated review of an unchanged snapshot is idempotent.
            if existing and existing["reviewed_version"] == current_job["result_version"] and existing["source_sha256"] == digest and existing["image_revision"] == image["revision"]:
                pass
            else:
                record = {"image_id": image["image_id"], "original_filename": uploaded["file_name"], "image_width": width, "image_height": height, "confirmed_at": now, "annotations": annotations}
                values = dict(reviewed_version=current_job["result_version"], reviewed_by=owner, reviewed_at=now, snapshot={"record": record, "extension": extension}, source_sha256=digest, image_revision=image["revision"], saved_version=existing["saved_version"] if existing else None, last_error=None)
                if existing:
                    db.execute(update(dataset_reviews).where(dataset_reviews.c.job_id == job_id).values(**values))
                else:
                    db.execute(insert(dataset_reviews).values(job_id=job_id, **values))
        return self.statuses([job_id], owner)[0]

    def save(self, job_id, reviewed_version, owner, *, locked=False):
        job = self.core.job(job_id, owner)
        with (nullcontext() if locked else self.files.locked()):
            with Session(self.engine) as db:
                review = db.execute(select(dataset_reviews).where(dataset_reviews.c.job_id == job_id)).mappings().first()
                version = db.scalar(select(ocr_jobs.c.result_version).where(ocr_jobs.c.id == job_id))
                if not review or review["reviewed_version"] != version or reviewed_version != version:
                    raise HTTPException(409, "请先完成当前版本的复核")
                image = db.execute(select(dataset_images).where(dataset_images.c.owner_id == owner, dataset_images.c.sha256 == review["source_sha256"])).mappings().one()
            record = review["snapshot"]["record"]
            committed = self.files.publication().get(image["image_id"], {})
            same = committed.get("job_id") == job_id and committed.get("saved_version") == version
            if not same and image["revision"] != review["image_revision"]:
                raise HTTPException(409, "同一图片已有其他入库版本，请重新复核")
            try:
                save_stage = "读取原图"
                _, content, extension, _, _ = self.source(job, owner)
                if hashlib.sha256(content).hexdigest() != review["source_sha256"]:
                    raise HTTPException(409, "原图已变化，请重新复核")
                revision = committed["revision"] if same else image["revision"] + 1
                if not same:
                    save_stage = "发布训练文件"
                    self.files.publish(record, content, extension, {"job_id": job_id, "saved_version": version, "revision": revision})
                # A crash after publication but before this transaction is repaired
                # by the next retry using the published commit metadata above.
                save_stage = "记录入库状态"
                with Session(self.engine) as db, db.begin():
                    db.execute(update(dataset_images).where(dataset_images.c.sequence == image["sequence"]).values(revision=revision, job_id=job_id, saved_version=version))
                    db.execute(update(dataset_reviews).where(dataset_reviews.c.job_id == job_id, dataset_reviews.c.reviewed_version == version).values(saved_version=version, image_revision=revision, last_error=None))
            except Exception as exc:
                logger.error("Dataset save failed job=%s stage=%s type=%s errno=%s winerror=%s", job_id, save_stage, type(exc).__name__, getattr(exc, "errno", None), getattr(exc, "winerror", None))
                reason = f"{save_stage}失败，请重试"
                if isinstance(exc, PermissionError):
                    reason = f"{save_stage}失败：文件被占用或目录没有写入权限，请关闭占用文件后重试"
                elif isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
                    reason = "数据集保存失败：磁盘空间不足，请清理空间后重试"
                elif isinstance(exc, HTTPException) and isinstance(exc.detail, str):
                    reason = exc.detail
                with Session(self.engine) as db, db.begin():
                    db.execute(update(dataset_reviews).where(dataset_reviews.c.job_id == job_id).values(last_error=reason))
                if isinstance(exc, HTTPException):
                    raise
                raise HTTPException(503, reason) from exc
        return self.statuses([job_id], owner)[0]
