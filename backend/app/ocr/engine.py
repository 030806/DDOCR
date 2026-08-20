"""Thread-safe lifecycle wrapper for the terminal OCR engine."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from threading import Lock
from typing import Any, TypeAlias

from PIL import Image

from app.ocr.contracts import OcrRegion
from app.ocr.errors import OcrInferenceError, OcrModelLoadError
from app.ocr.settings import OcrSettings


EngineFactory: TypeAlias = Callable[[OcrSettings], object]
EngineRunner: TypeAlias = Callable[
    [object, Image.Image, Sequence[OcrRegion], OcrSettings],
    Any,
]


class TerminalOcrEngine:
    """Own one lazily loaded OCR engine and serialize access to it.

    The wrapper deliberately has no service, repository, worker, or database
    dependency. Tests and later integration layers can inject ``engine_factory``
    and ``engine_runner`` to exercise the lifecycle without importing PaddleOCR.
    A single lock protects both initialization and inference because the demo
    engine is not guaranteed to be thread-safe.
    """

    def __init__(
        self,
        settings: OcrSettings | None = None,
        *,
        engine_factory: EngineFactory | None = None,
        engine_runner: EngineRunner | None = None,
    ) -> None:
        """Create an unloaded engine wrapper.

        Neither the real nor an injected engine factory is called until
        :meth:`load` or :meth:`run` is invoked.
        """

        self.settings: OcrSettings = settings or OcrSettings.from_env()
        self._engine_factory: EngineFactory = (
            engine_factory or self._create_default_engine
        )
        self._engine_runner: EngineRunner = engine_runner or self._run_default_engine
        self._engine: object | None = None
        self._lock: Lock = Lock()

    @property
    def is_loaded(self) -> bool:
        """Return whether an engine instance is currently retained."""

        with self._lock:
            return self._engine is not None

    def load(self) -> object:
        """Initialize the engine once and return the retained instance."""

        with self._lock:
            return self._load_unlocked()

    def run(
        self,
        image: Image.Image,
        regions: Sequence[OcrRegion],
    ) -> Any:
        """Run OCR while holding the engine's exclusive lifecycle lock."""

        with self._lock:
            engine = self._load_unlocked()
            try:
                return self._engine_runner(
                    engine,
                    image,
                    regions,
                    self.settings,
                )
            except OcrInferenceError:
                raise
            except Exception as exc:
                raise OcrInferenceError(
                    f"Terminal OCR inference failed: {type(exc).__name__}: {exc}"
                ) from exc

    def close(self) -> None:
        """Release the retained engine and invoke its optional close hook.

        Calling this method repeatedly is safe. A later :meth:`load` or
        :meth:`run` call creates a fresh engine instance.
        """

        with self._lock:
            engine = self._engine
            self._engine = None
            if engine is None:
                return
            close_hook = getattr(engine, "close", None)
            if callable(close_hook):
                close_hook()

    def __enter__(self) -> TerminalOcrEngine:
        """Load and return this wrapper for context-managed use."""

        self.load()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        """Release the retained engine when leaving a context manager."""

        del exc_type, exc_value, traceback
        self.close()

    def _load_unlocked(self) -> object:
        """Load the engine while the caller owns ``self._lock``."""

        if self._engine is not None:
            return self._engine
        try:
            engine = self._engine_factory(self.settings)
        except OcrModelLoadError:
            raise
        except Exception as exc:
            raise OcrModelLoadError(
                f"Terminal OCR model load failed: {type(exc).__name__}: {exc}"
            ) from exc
        if engine is None:
            raise OcrModelLoadError("Terminal OCR engine factory returned None")
        self._engine = engine
        return engine

    @staticmethod
    def _create_default_engine(settings: OcrSettings) -> object:
        """Create the configured OCR recognizer only when first used."""

        try:
            from app.vendor.terminal_ocr_demo.config import DemoConfig
        except (ImportError, ModuleNotFoundError) as exc:
            raise OcrModelLoadError(
                "app.vendor.terminal_ocr_demo is not importable"
            ) from exc

        config = DemoConfig(
            device=settings.device,
            scale=settings.scale,
            rotations=settings.rotations,
            code_library_path=settings.code_library,
        )
        if settings.backend == "onnx":
            try:
                from app.ocr.onnx_engine import OnnxRecognizerEngine
            except (ImportError, ModuleNotFoundError) as exc:
                raise OcrModelLoadError("ONNX OCR engine is not importable") from exc
            return OnnxRecognizerEngine(config)

        try:
            from app.vendor.terminal_ocr_demo.ocr_engine import PaddleOCREngine
            from app.vendor.terminal_ocr_demo.runtime_env import (
                configure_paddlex_cache,
            )
        except (ImportError, ModuleNotFoundError) as exc:
            raise OcrModelLoadError("Paddle OCR engine is not importable") from exc
        configure_paddlex_cache(settings.model_cache)
        return PaddleOCREngine(config)

    @staticmethod
    def _run_default_engine(
        engine: object,
        image: Image.Image,
        regions: Sequence[OcrRegion],
        settings: OcrSettings,
    ) -> Any:
        """Invoke the demo pipeline for the retained real engine."""

        del settings
        try:
            from app.vendor.terminal_ocr_demo.models import ROI
            from app.vendor.terminal_ocr_demo.pipeline import run_pipeline
        except (ImportError, ModuleNotFoundError) as exc:
            raise OcrInferenceError(
                "app.vendor.terminal_ocr_demo pipeline is not importable"
            ) from exc

        demo_regions = [
            ROI(
                roi_id=region.roi_id,
                bbox=tuple(round(coordinate) for coordinate in region.bbox),
            )
            for region in regions
        ]
        config = getattr(engine, "config", None)
        if config is None:
            raise OcrInferenceError("Terminal OCR engine has no demo configuration")
        return run_pipeline(image, demo_regions, engine, config)
