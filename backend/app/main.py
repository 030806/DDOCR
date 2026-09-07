import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from app.api.routes import router
from app.api.dataset_routes import router as dataset_router
from app.models.store import Store
from app.ocr.adapter import OcrAdapter
from app.ocr.contracts import OcrAdapterProtocol
from app.ocr.engine import TerminalOcrEngine
from app.services.core import MockOcrService
from app.utils.common import uid
from app.workers.ocr_task import OcrTaskWorker


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def create_app(
    data_dir: str | None = None,
    database_url: str | None = None,
    ocr_adapter: OcrAdapterProtocol | None = None,
) -> FastAPI:
    app = FastAPI(
        title="DDOCR Mock Backend",
        version="0.1.0",
        description="第一阶段 Mock OCR API",
    )
    default_data_dir = Path(__file__).resolve().parents[1] / "data"
    configured_data_dir = data_dir or os.getenv(
        "DDOCR_DATA_DIR",
        default_data_dir,
    )
    root = Path(configured_data_dir)
    configured_database_url = database_url or os.getenv("DDOCR_DATABASE_URL")
    if not configured_database_url:
        configured_database_url = f"sqlite:///{(root / 'ddocr.db').as_posix()}"
    managed_engine = TerminalOcrEngine() if ocr_adapter is None else None
    active_adapter = (
        ocr_adapter if ocr_adapter is not None else OcrAdapter(managed_engine)
    )
    service = MockOcrService(Store(root, configured_database_url), active_adapter)
    worker = OcrTaskWorker(service)
    service.job_submitter = worker.submit
    app.state.service = service
    app.state.ocr_worker = worker
    app.state.ocr_engine = managed_engine
    app.include_router(router)
    app.include_router(dataset_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.on_event("shutdown")
    def shutdown_ocr() -> None:
        worker.shutdown(wait=True)
        if managed_engine is not None:
            managed_engine.close()

    @app.exception_handler(HTTPException)
    async def http_error(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        del request
        details = exc.detail if isinstance(exc.detail, dict) else None
        code = details.pop("code", None) if details else None
        message = (
            exc.detail if isinstance(exc.detail, str) else "Request failed"
        )
        content = {
            "error": {
                "code": code or f"HTTP_{exc.status_code}",
                "message": message,
                "details": details,
            },
            "request_id": f"req_{uid()}",
        }
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del request
        content = {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": {"errors": exc.errors()},
            },
            "request_id": f"req_{uid()}",
        }
        return JSONResponse(status_code=422, content=content)
    return app


app = create_app()
