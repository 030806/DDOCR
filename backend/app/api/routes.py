from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse

from app.schemas.contracts import (
    CommentCreate,
    CommentUpdate,
    CorrectionCreate,
    ExportCreate,
    JobCreate,
    UploadSessionCreate,
)
from app.services.core import MockOcrService
from app.utils.common import envelope, now

router = APIRouter(prefix="/api/v1")


def service(request: Request) -> MockOcrService:
    return request.app.state.service


def base(request: Request) -> str:
    return str(request.base_url)


@router.get("/models")
def models(request: Request, status: str = "available") -> dict[str, Any]:
    del request
    items = [
        {
            "id": "mock",
            "name": "Mock OCR",
            "default_version": "1.0.0",
            "languages": ["zh-CN", "en"],
            "capabilities": ["text_detection", "text_recognition"],
            "note": "第一阶段固定模拟结果",
            "estimated_ms_per_page": 20,
            "status": "available",
            "input_limits": {
                "max_width_px": 10000,
                "max_height_px": 10000,
            },
        }
    ]
    filtered_items = [item for item in items if item["status"] == status]
    return envelope({"items": filtered_items})


@router.post("/files/upload-sessions", status_code=201)
def create_upload(
    body: UploadSessionCreate,
    request: Request,
) -> dict[str, Any]:
    upload = service(request).create_upload(body, base(request))
    return envelope(upload)


@router.put("/files/{file_id}/content")
async def upload_content(file_id: str, request: Request) -> dict[str, Any]:
    content = await request.body()
    uploaded_file = service(request).save_content(file_id, content)
    return envelope(uploaded_file)


@router.post("/files/{file_id}/complete")
def complete(file_id: str, request: Request) -> dict[str, Any]:
    completed_file = service(request).complete(file_id)
    return envelope(completed_file)


@router.get("/files/{file_id}")
def get_file(file_id: str, request: Request) -> dict[str, Any]:
    uploaded_file = service(request).file(file_id)
    return envelope(uploaded_file)


@router.delete("/files/{file_id}", status_code=204)
def delete_file(file_id: str, request: Request) -> Response:
    ocr_service = service(request)
    uploaded_file = ocr_service.file(file_id)
    jobs = ocr_service.store.all("job")
    is_in_use = any(
        job["file_id"] == file_id and not job.get("deleted") for job in jobs
    )
    if is_in_use:
        return Response(status_code=409)

    uploaded_file["deleted"] = True
    ocr_service.store.put("file", file_id, uploaded_file)
    return Response(status_code=204)


@router.post("/ocr/jobs", status_code=202)
def create_job(body: JobCreate, request: Request) -> dict[str, Any]:
    job_data = service(request).create_job(body)
    return envelope(job_data)


@router.get("/ocr/jobs")
def jobs(
    request: Request,
    query: str | None = None,
    status: str | None = None,
    sort: str = "-created_at",
    cursor: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    del cursor
    all_jobs = service(request).store.all("job")
    items = [job for job in all_jobs if not job.get("deleted")]
    if query:
        normalized_query = query.lower()
        items = [
            job
            for job in items
            if normalized_query in (job["name"] + job["file_name"]).lower()
        ]
    if status:
        requested_statuses = status.split(",")
        items = [job for job in items if job["status"] in requested_statuses]

    items.sort(
        key=lambda job: job["created_at"],
        reverse=sort.startswith("-"),
    )
    items = items[: min(limit, 100)]
    data = {"items": items, "next_cursor": None, "total": len(items)}
    return envelope(data)


@router.get("/ocr/jobs/{job_id}")
def job(job_id: str, request: Request) -> dict[str, Any]:
    job_data = service(request).job(job_id)
    return envelope(job_data)


@router.get("/ocr/jobs/{job_id}/pages")
def pages(job_id: str, request: Request) -> dict[str, Any]:
    page_items = service(request).pages(job_id)
    return envelope({"items": page_items})


@router.get("/ocr/jobs/{job_id}/pages/{page_no}/results")
def results(job_id: str, page_no: int, request: Request) -> dict[str, Any]:
    ocr_service = service(request)
    job_data = ocr_service.job(job_id)
    pages_data = [
        ocr_service.store.get("page", page_id)
        for page_id in job_data["page_ids"]
    ]
    page = next(
        (
            page_data
            for page_data in pages_data
            if page_data and page_data["page_no"] == page_no
        ),
        None,
    )
    if not page:
        raise HTTPException(404, "Page not found")

    image = page["image"]
    result_items = [
        ocr_service.public_result(ocr_service.result(result_id))
        for result_id in page["result_ids"]
    ]
    data = {
        "job_id": job_id,
        "page_id": page["id"],
        "page_no": page_no,
        "coordinate_system": {
            "origin": "top_left",
            "unit": "pixel",
            "width_px": image["width_px"],
            "height_px": image["height_px"],
        },
        "items": result_items,
    }
    return envelope(data)


@router.post("/ocr/results/{result_id}/corrections", status_code=201)
def correct(
    result_id: str,
    body: CorrectionCreate,
    request: Request,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    ocr_service = service(request)
    cache_key = f"correction:{result_id}:{idempotency_key}"
    if idempotency_key:
        cached = ocr_service.store.get("idempotency", cache_key)
        if cached:
            return envelope(cached)

    correction = ocr_service.add_correction(result_id, body)
    if idempotency_key:
        ocr_service.store.put("idempotency", cache_key, correction)
    return envelope(correction)


@router.get("/ocr/results/{result_id}/corrections")
def corrections(result_id: str, request: Request) -> dict[str, Any]:
    ocr_service = service(request)
    ocr_service.result(result_id)
    all_corrections = ocr_service.store.all("correction")
    items = [
        item for item in all_corrections if item["result_id"] == result_id
    ]
    sorted_items = sorted(items, key=lambda item: item["revision"])
    data = {
        "items": sorted_items,
        "next_cursor": None,
        "total": len(items),
    }
    return envelope(data)


@router.get("/ocr/results/{result_id}/comments")
def comments(result_id: str, request: Request) -> dict[str, Any]:
    ocr_service = service(request)
    ocr_service.result(result_id)
    items = ocr_service.comments(result_id)
    data = {"items": items, "next_cursor": None, "total": len(items)}
    return envelope(data)


@router.post("/ocr/results/{result_id}/comments", status_code=201)
def add_comment(
    result_id: str,
    body: CommentCreate,
    request: Request,
) -> dict[str, Any]:
    comment = service(request).add_comment(result_id, body.content)
    return envelope(comment)


@router.patch("/ocr/results/{result_id}/comments/{comment_id}")
def update_comment(
    result_id: str,
    comment_id: str,
    body: CommentUpdate,
    request: Request,
) -> dict[str, Any]:
    ocr_service = service(request)
    comment = ocr_service.store.get("comment", comment_id)
    is_missing = not comment or comment["result_id"] != result_id
    if is_missing or comment.get("deleted"):
        raise HTTPException(404, "Comment not found")

    comment["content"] = body.content
    comment["updated_at"] = now()
    ocr_service.store.put("comment", comment_id, comment)
    return envelope(comment)


@router.delete(
    "/ocr/results/{result_id}/comments/{comment_id}",
    status_code=204,
)
def delete_comment(
    result_id: str,
    comment_id: str,
    request: Request,
) -> Response:
    ocr_service = service(request)
    comment = ocr_service.store.get("comment", comment_id)
    if not comment or comment["result_id"] != result_id:
        raise HTTPException(404, "Comment not found")

    comment["deleted"] = True
    ocr_service.store.put("comment", comment_id, comment)
    return Response(status_code=204)


@router.post("/ocr/jobs/{job_id}/exports", status_code=202)
def create_export(
    job_id: str,
    body: ExportCreate,
    request: Request,
) -> dict[str, Any]:
    export = service(request).export(job_id, body, base(request))
    return envelope(export)


@router.get("/ocr/jobs/{job_id}/exports/{export_id}")
def get_export(
    job_id: str,
    export_id: str,
    request: Request,
) -> dict[str, Any]:
    export = service(request).store.get("export", export_id)
    if not export or export["job_id"] != job_id:
        raise HTTPException(404, "Export not found")
    return envelope(export)


@router.get("/ocr/jobs/{job_id}/exports/{export_id}/download")
def download(job_id: str, export_id: str, request: Request) -> FileResponse:
    ocr_service = service(request)
    export = ocr_service.store.get("export", export_id)
    if not export or export["job_id"] != job_id:
        raise HTTPException(404, "Export not found")

    export_path = ocr_service.store.exports / f"{export_id}.xlsx"
    filename = f"ocr-{job_id}.xlsx"
    return FileResponse(export_path, filename=filename)
