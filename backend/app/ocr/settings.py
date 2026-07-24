"""Environment-backed configuration for the future real OCR engine."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _default_cache_path() -> Path:
    """Return an absolute, writable-intended PaddleX cache location."""

    base = Path(os.getenv("LOCALAPPDATA") or tempfile.gettempdir())
    return (base / "ddocr" / "paddlex-cache").resolve()


def _default_library_path() -> Path:
    """Return the planned vendored terminal-code library location."""

    return (
        Path(__file__).resolve().parents[1]
        / "vendor"
        / "terminal_ocr_demo"
        / "resources"
        / "terminal_id_library.csv"
    )


def _parse_rotations(raw_value: str) -> tuple[int, ...]:
    """Parse a comma-separated list of unique right-angle rotations."""

    rotations: list[int] = []
    for token in raw_value.split(","):
        stripped = token.strip()
        if not stripped:
            continue
        try:
            rotation = int(stripped) % 360
        except ValueError as exc:
            raise ValueError("DDOCR_OCR_ROTATIONS must contain integers") from exc
        if rotation not in {0, 90, 180, 270}:
            raise ValueError("DDOCR_OCR_ROTATIONS supports only right angles")
        if rotation not in rotations:
            rotations.append(rotation)
    if not rotations:
        raise ValueError("DDOCR_OCR_ROTATIONS must not be empty")
    return tuple(rotations)


@dataclass(frozen=True, slots=True)
class OcrSettings:
    """Immutable settings required by the planned OCR engine and worker."""

    device: str
    model_cache: Path
    code_library: Path
    scale: float
    rotations: tuple[int, ...]
    max_concurrency: int
    execution_mode: str

    @classmethod
    def from_env(cls) -> OcrSettings:
        """Build and validate OCR settings from process environment variables."""

        device = os.getenv("DDOCR_OCR_DEVICE", "cpu").strip()
        model_cache = Path(
            os.getenv("DDOCR_OCR_MODEL_CACHE") or _default_cache_path()
        ).expanduser().resolve()
        code_library = Path(
            os.getenv("DDOCR_OCR_CODE_LIBRARY") or _default_library_path()
        ).expanduser().resolve()
        scale = float(os.getenv("DDOCR_OCR_SCALE", "2.0"))
        max_concurrency = int(os.getenv("DDOCR_OCR_MAX_CONCURRENCY", "1"))
        execution_mode = os.getenv(
            "DDOCR_OCR_EXECUTION_MODE", "blocking"
        ).strip().lower()
        rotations = _parse_rotations(
            os.getenv("DDOCR_OCR_ROTATIONS", "0,90,180,270")
        )

        if not device:
            raise ValueError("DDOCR_OCR_DEVICE must not be empty")
        if scale <= 0:
            raise ValueError("DDOCR_OCR_SCALE must be positive")
        if max_concurrency <= 0:
            raise ValueError("DDOCR_OCR_MAX_CONCURRENCY must be positive")
        if execution_mode not in {"blocking", "async"}:
            raise ValueError(
                "DDOCR_OCR_EXECUTION_MODE must be 'blocking' or 'async'"
            )

        return cls(
            device=device,
            model_cache=model_cache,
            code_library=code_library,
            scale=scale,
            rotations=rotations,
            max_concurrency=max_concurrency,
            execution_mode=execution_mode,
        )
