from pathlib import Path
from dataclasses import replace
from threading import Barrier, Lock, Thread
from time import sleep
from typing import Any

import pytest
from PIL import Image

from app.ocr.contracts import OcrRegion
from app.ocr.engine import TerminalOcrEngine
from app.ocr.errors import OcrInferenceError, OcrModelLoadError
from app.ocr.onnx_engine import OnnxRecognizerEngine
from app.ocr.settings import OcrSettings


def settings(tmp_path: Path) -> OcrSettings:
    return OcrSettings(
        device="cpu",
        model_cache=tmp_path / "cache",
        code_library=tmp_path / "terminal_id_library.csv",
        scale=2.0,
        rotations=(0, 90, 180, 270),
        max_concurrency=1,
        execution_mode="blocking",
    )


def region() -> OcrRegion:
    return OcrRegion("page_1", (0.0, 0.0, 20.0, 10.0))


def test_engine_is_lazily_loaded_and_reused(tmp_path: Path) -> None:
    created: list[object] = []

    def factory(_settings: OcrSettings) -> object:
        instance = object()
        created.append(instance)
        return instance

    def runner(
        engine: object,
        image: Image.Image,
        regions: Any,
        _settings: OcrSettings,
    ) -> tuple[object, tuple[OcrRegion, ...], tuple[int, int]]:
        return engine, tuple(regions), image.size

    wrapper = TerminalOcrEngine(
        settings(tmp_path),
        engine_factory=factory,
        engine_runner=runner,
    )
    assert not wrapper.is_loaded
    assert created == []

    first = wrapper.run(Image.new("RGB", (20, 10)), [region()])
    second = wrapper.run(Image.new("RGB", (20, 10)), [region()])

    assert wrapper.is_loaded
    assert len(created) == 1
    assert first[0] is created[0]
    assert second[0] is created[0]
    assert first[1] == (region(),)
    assert first[2] == (20, 10)


def test_default_engine_uses_onnx_backend(tmp_path: Path) -> None:
    engine = TerminalOcrEngine(settings(tmp_path))

    loaded = engine.load()

    assert isinstance(loaded, OnnxRecognizerEngine)
    engine.close()


def test_onnx_model_settings_reach_the_recognizer(tmp_path: Path) -> None:
    configured = replace(
        settings(tmp_path),
        onnx_rec_model_path=tmp_path / "rec.onnx",
        onnx_rec_keys_path=tmp_path / "keys.txt",
        ctc_min_relative_probability=0.7,
    )
    engine = TerminalOcrEngine(configured)
    loaded = engine.load()
    assert isinstance(loaded, OnnxRecognizerEngine)
    assert loaded.config.onnx_rec_model_path == configured.onnx_rec_model_path
    assert loaded.config.onnx_rec_keys_path == configured.onnx_rec_keys_path
    assert loaded.config.ctc_min_relative_probability == 0.7


def test_settings_rejects_unknown_ocr_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DDOCR_OCR_BACKEND", "unsupported")

    with pytest.raises(ValueError, match="DDOCR_OCR_BACKEND"):
        OcrSettings.from_env()


def test_settings_default_to_onnx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DDOCR_OCR_BACKEND", raising=False)

    assert OcrSettings.from_env().backend == "onnx"


def test_ctc_probability_setting_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DDOCR_OCR_CTC_MIN_RELATIVE_PROBABILITY", "0.7")
    assert OcrSettings.from_env().ctc_min_relative_probability == 0.7
    monkeypatch.setenv("DDOCR_OCR_CTC_MIN_RELATIVE_PROBABILITY", "0")
    with pytest.raises(ValueError, match="CTC_MIN_RELATIVE_PROBABILITY"):
        OcrSettings.from_env()


def test_custom_onnx_model_requires_matching_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DDOCR_OCR_ONNX_REC_MODEL_PATH", "rec.onnx")
    monkeypatch.delenv("DDOCR_OCR_ONNX_REC_KEYS_PATH", raising=False)
    with pytest.raises(ValueError, match="both model and keys"):
        OcrSettings.from_env()


def test_illumination_defaults_off_and_rejects_unknown_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DDOCR_OCR_ILLUMINATION", raising=False)
    assert OcrSettings.from_env().illumination == "none"
    monkeypatch.setenv("DDOCR_OCR_ILLUMINATION", "clahe")
    assert OcrSettings.from_env().illumination == "clahe"
    monkeypatch.setenv("DDOCR_OCR_ILLUMINATION", "unknown")
    with pytest.raises(ValueError, match="DDOCR_OCR_ILLUMINATION"):
        OcrSettings.from_env()


def test_each_job_can_override_illumination_without_changing_the_shared_engine(tmp_path: Path) -> None:
    seen: list[str] = []
    wrapper = TerminalOcrEngine(
        settings(tmp_path),
        engine_factory=lambda _settings: object(),
        engine_runner=lambda _engine, _image, _regions, configured: seen.append(configured.illumination),
    )
    for mode in ("he", "clahe", "none"):
        wrapper.run(Image.new("RGB", (20, 10)), [region()], illumination=mode)
    wrapper.run(Image.new("RGB", (20, 10)), [region()])
    assert seen == ["he", "clahe", "none", "none"]
    assert wrapper.settings.illumination == "none"
    with pytest.raises(ValueError, match="illumination"):
        wrapper.run(Image.new("RGB", (20, 10)), [region()], illumination="unknown")


def test_load_initializes_once_without_running_inference(tmp_path: Path) -> None:
    factory_calls = 0
    runner_calls = 0

    def factory(_settings: OcrSettings) -> object:
        nonlocal factory_calls
        factory_calls += 1
        return object()

    def runner(*_args: object) -> object:
        nonlocal runner_calls
        runner_calls += 1
        return object()

    wrapper = TerminalOcrEngine(
        settings(tmp_path),
        engine_factory=factory,
        engine_runner=runner,
    )

    assert wrapper.load() is wrapper.load()
    assert factory_calls == 1
    assert runner_calls == 0


def test_close_releases_fake_engine_and_allows_reload(tmp_path: Path) -> None:
    class FakeEngine:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    instances: list[FakeEngine] = []

    def factory(_settings: OcrSettings) -> object:
        instance = FakeEngine()
        instances.append(instance)
        return instance

    wrapper = TerminalOcrEngine(settings(tmp_path), engine_factory=factory)
    assert wrapper.load() is instances[0]

    wrapper.close()
    wrapper.close()

    assert instances[0].close_calls == 1
    assert not wrapper.is_loaded
    assert wrapper.load() is instances[1]
    assert len(instances) == 2


def test_context_manager_owns_engine_lifecycle(tmp_path: Path) -> None:
    class FakeEngine:
        closed = False

        def close(self) -> None:
            self.closed = True

    fake = FakeEngine()
    wrapper = TerminalOcrEngine(
        settings(tmp_path),
        engine_factory=lambda _settings: fake,
    )

    with wrapper as entered:
        assert entered is wrapper
        assert wrapper.is_loaded

    assert fake.closed
    assert not wrapper.is_loaded


def test_lock_serializes_concurrent_fake_inference(tmp_path: Path) -> None:
    state_lock = Lock()
    start_barrier = Barrier(3)
    active_calls = 0
    maximum_active_calls = 0
    results: list[str] = []

    def runner(
        _engine: object,
        _image: Image.Image,
        _regions: Any,
        _settings: OcrSettings,
    ) -> str:
        nonlocal active_calls, maximum_active_calls
        with state_lock:
            active_calls += 1
            maximum_active_calls = max(maximum_active_calls, active_calls)
        sleep(0.03)
        with state_lock:
            active_calls -= 1
        return "ok"

    wrapper = TerminalOcrEngine(
        settings(tmp_path),
        engine_factory=lambda _settings: object(),
        engine_runner=runner,
    )

    def invoke() -> None:
        start_barrier.wait()
        results.append(wrapper.run(Image.new("RGB", (20, 10)), [region()]))

    threads = [Thread(target=invoke), Thread(target=invoke)]
    for thread in threads:
        thread.start()
    start_barrier.wait()
    for thread in threads:
        thread.join(timeout=1)

    assert all(not thread.is_alive() for thread in threads)
    assert results == ["ok", "ok"]
    assert maximum_active_calls == 1


def test_factory_failure_is_wrapped_and_not_cached(tmp_path: Path) -> None:
    calls = 0

    def factory(_settings: OcrSettings) -> object:
        nonlocal calls
        calls += 1
        raise RuntimeError("model unavailable")

    wrapper = TerminalOcrEngine(settings(tmp_path), engine_factory=factory)

    with pytest.raises(OcrModelLoadError, match="model unavailable"):
        wrapper.load()
    with pytest.raises(OcrModelLoadError):
        wrapper.load()

    assert calls == 2
    assert not wrapper.is_loaded


def test_runner_failure_is_wrapped_but_engine_stays_loaded(tmp_path: Path) -> None:
    fake = object()

    def runner(*_args: object) -> object:
        raise RuntimeError("prediction failed")

    wrapper = TerminalOcrEngine(
        settings(tmp_path),
        engine_factory=lambda _settings: fake,
        engine_runner=runner,
    )

    with pytest.raises(OcrInferenceError, match="prediction failed"):
        wrapper.run(Image.new("RGB", (20, 10)), [region()])

    assert wrapper.is_loaded
    assert wrapper.load() is fake
