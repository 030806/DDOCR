import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.models.store import Store
from app.services.core import MockOcrService
from app.utils.common import uid


def create_app(data_dir: str | None = None) -> FastAPI:
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
    app.state.service = MockOcrService(Store(root))
    app.state.service.ensure_demo_job()
    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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
