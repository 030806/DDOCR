from __future__ import annotations

import re
from dataclasses import replace
from types import SimpleNamespace

import numpy as np

from app.ocr.ctc_candidates import CandidateTextRecognizer, decode_ctc_candidates
from app.ocr.adapter import OcrAdapter
from app.vendor.terminal_ocr_demo.config import DemoConfig
from app.vendor.terminal_ocr_demo.models import ModelTextCandidate, OCRDetection
from app.vendor.terminal_ocr_demo.postprocess import postprocess_detections
from app.vendor.terminal_ocr_demo.rules import ALLOWED_CHARACTERS, TerminalCodeRules


def _prediction(alternative: str) -> tuple[np.ndarray, list[str]]:
    characters = ["blank", "H", "1", "2", "（", "-", "/"]
    probabilities = np.full((3, len(characters)), 0.001, dtype=np.float64)
    probabilities[0, 1] = 0.95
    probabilities[1, 4] = 0.55
    probabilities[1, characters.index(alternative)] = 0.40
    probabilities[2, 0] = 0.95
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    return probabilities, characters


def test_ctc_candidates_compare_full_strings_and_keep_punctuation() -> None:
    probabilities, characters = _prediction("1")
    candidates, raw_log_probability = decode_ctc_candidates(
        probabilities, characters, ALLOWED_CHARACTERS, "H（"
    )

    by_text = {candidate.text: candidate.log_probability for candidate in candidates}
    assert "H1" in by_text
    assert "（" not in "".join(by_text)
    assert np.exp(by_text["H1"] - raw_log_probability) > 0.5
    for symbol in ("-", "/"):
        symbol_probabilities, _ = _prediction(symbol)
        symbol_candidates, _ = decode_ctc_candidates(
            symbol_probabilities, characters, ALLOWED_CHARACTERS, "H（"
        )
        assert f"H{symbol}" in {candidate.text for candidate in symbol_candidates}


def test_ctc_candidates_do_not_collapse_repeated_letters_without_blank() -> None:
    characters = ["blank", "A"]
    probabilities = np.array([[0.1, 0.9], [0.9, 0.1], [0.1, 0.9]])
    candidates, _ = decode_ctc_candidates(
        probabilities, characters, frozenset("A"), "AA"
    )
    assert candidates[0].text == "AA"


def test_ctc_candidates_reject_dictionary_shape_mismatch() -> None:
    probabilities, characters = _prediction("1")
    try:
        decode_ctc_candidates(probabilities[:, :-1], characters, ALLOWED_CHARACTERS, "H（")
    except ValueError as exc:
        assert "character table" in str(exc)
    else:
        raise AssertionError("mismatched OCR dictionary must not produce candidates")


def test_rapidocr_capture_preserves_original_detection_order() -> None:
    first, characters = _prediction("1")
    second, _ = _prediction("2")

    class Session:
        def __call__(self, marker: np.ndarray) -> list[np.ndarray]:
            return [(first if int(marker[0]) == 0 else second)[None, ...]]

    class Recognizer:
        def __init__(self) -> None:
            self.session = Session()
            self.postprocess_op = SimpleNamespace(character=characters)

        def __call__(self, images: list[np.ndarray], return_word_box: bool = False):
            results = [("", 0.0)] * len(images)
            for index in np.argsort([img.shape[1] / img.shape[0] for img in images]):
                self.session(np.asarray([index]))
                results[index] = ("H（", 0.8)
            return results, 0.01

    recognizer = CandidateTextRecognizer(Recognizer(), ALLOWED_CHARACTERS)
    images = [np.zeros((5, 10, 3)), np.zeros((5, 5, 3))]
    results, _ = recognizer(images)
    assert results[0][2]["model_candidates"][0].text == "H1"
    assert results[1][2]["model_candidates"][0].text == "H2"


def _rules() -> TerminalCodeRules:
    return TerminalCodeRules(
        library_codes=frozenset({"H1", "H2"}),
        library_statuses={"H1": "library", "H2": "library"},
        base_pattern=re.compile(r"^H\d+$"),
        extended_pattern=re.compile(r"^H\d+$"),
    )


def _detection(candidate_log_probability: float, raw_log_probability: float) -> OCRDetection:
    return OCRDetection(
        roi_id="roi-1",
        raw_text="H（",
        ocr_score=0.8,
        text_bbox_original=[[0, 0], [10, 0], [10, 5], [0, 5]],
        rotation=0,
        scale=1.0,
        model_candidates=(ModelTextCandidate("H1", candidate_log_probability),),
        model_raw_log_probability=raw_log_probability,
    )


def test_probability_correction_requires_close_model_score_and_review() -> None:
    result = postprocess_detections(
        [_detection(-1.0, -0.5)], _rules(), DemoConfig(ctc_min_relative_probability=0.5)
    )
    selected = result.detections[0]
    assert selected.raw_text == "H（"
    assert selected.output_text == "H1"
    assert selected.assessment is not None
    assert selected.assessment.match_method == "model_probability_correction"
    assert selected.assessment.review_status == "review_required"
    assert result.audit_records[0]["model_candidates"][0]["text"] == "H1"
    adapted = OcrAdapter.adapt_detection(selected, image_width=20, image_height=20)
    assert adapted.text == "H1"
    assert adapted.review_required
    assert adapted.attributes["raw_text"] == "H（"
    assert adapted.attributes["model_candidates"][0]["text"] == "H1"
    assert adapted.attributes["confidence_refers_to_raw_text"] is True


def test_probability_correction_does_not_guess_weak_or_unconfirmed_codes() -> None:
    weak = postprocess_detections([_detection(-3.0, -0.5)], _rules(), DemoConfig())
    assert weak.detections[0].output_text == "H"
    assert weak.detections[0].is_unresolved

    unconfirmed = replace(
        _detection(-1.0, -0.5),
        model_candidates=(ModelTextCandidate("H-", -1.0),),
    )
    result = postprocess_detections([unconfirmed], _rules(), DemoConfig())
    assert result.detections[0].output_text == "H"
