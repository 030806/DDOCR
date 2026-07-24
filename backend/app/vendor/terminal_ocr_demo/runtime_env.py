"""Runtime paths required by PaddleX/PaddleOCR on Windows."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def configure_paddlex_cache(cache_path: Path | None = None) -> Path:
    """Use an ASCII-friendly writable cache path before importing PaddleX."""

    configured = os.environ.get("PADDLE_PDX_CACHE_HOME")
    if cache_path is not None:
        resolved_path = Path(cache_path).expanduser().resolve()
        os.environ["PADDLE_PDX_CACHE_HOME"] = str(resolved_path)
    elif configured:
        resolved_path = Path(configured).expanduser().resolve()
    else:
        base_path = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
        resolved_path = (base_path / "ddocr" / "paddlex-cache").resolve()
        os.environ["PADDLE_PDX_CACHE_HOME"] = str(resolved_path)

    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    resolved_path.mkdir(parents=True, exist_ok=True)
    return resolved_path
