"""Read full-text alternatives from RapidOCR 1.4.4's CTC recognizer.

RapidOCR normally reduces its [batch, time, character] output to one text and
one aggregate score. This wrapper observes that same forward pass; it never
runs a second model or changes the public OCR API. It relies on the pinned
RapidOCR 1.4.4 TextRecognizer/session contract and fails back to top-1 output
when that contract or the model's character table is incompatible.
"""

from __future__ import annotations

import logging
import math
from threading import Lock
from typing import Any, Sequence

import numpy as np

from app.vendor.terminal_ocr_demo.models import ModelTextCandidate


_LOG = logging.getLogger(__name__)
_NEG_INF = float("-inf")


def _log_add(left: float, right: float) -> float:
    if left == _NEG_INF:
        return right
    if right == _NEG_INF:
        return left
    if left < right:
        left, right = right, left
    return left + math.log1p(math.exp(right - left))


def _log_probabilities(prediction: np.ndarray, characters: Sequence[str]) -> np.ndarray:
    values = np.asarray(prediction, dtype=np.float64)
    if values.ndim != 2 or values.shape[0] < 1 or values.shape[1] != len(characters):
        raise ValueError("recognition output shape does not match its character table")
    if not np.isfinite(values).all() or characters[0] != "blank":
        raise ValueError("recognition output or CTC blank index is invalid")

    row_sums = values.sum(axis=1)
    if np.all(values >= 0) and np.all(values <= 1) and np.allclose(row_sums, 1, atol=1e-2):
        probabilities = values
    else:
        shifted = values - values.max(axis=1, keepdims=True)
        exponentials = np.exp(shifted)
        probabilities = exponentials / exponentials.sum(axis=1, keepdims=True)
    with np.errstate(divide="ignore"):
        return np.log(probabilities)


def ctc_text_log_probability(
    log_probs: np.ndarray, characters: Sequence[str], text: str
) -> float:
    """Sum the probabilities of every CTC alignment for one exact string."""

    lookup = {character: index for index, character in enumerate(characters)}
    if any(character not in lookup for character in text):
        return _NEG_INF
    labels = [0]
    for character in text:
        labels.extend((lookup[character], 0))
    previous = [_NEG_INF] * len(labels)
    previous[0] = float(log_probs[0, 0])
    if len(labels) > 1:
        previous[1] = float(log_probs[0, labels[1]])
    for time_index in range(1, log_probs.shape[0]):
        current = [_NEG_INF] * len(labels)
        for state, label in enumerate(labels):
            total = previous[state]
            if state:
                total = _log_add(total, previous[state - 1])
            if state >= 2 and label != 0 and label != labels[state - 2]:
                total = _log_add(total, previous[state - 2])
            current[state] = total + float(log_probs[time_index, label])
        previous = current
    return _log_add(previous[-1], previous[-2]) if len(previous) > 1 else previous[0]


def decode_ctc_candidates(
    prediction: np.ndarray,
    characters: Sequence[str],
    allowed_characters: frozenset[str],
    raw_text: str,
    *,
    beam_width: int = 32,
    max_candidates: int = 5,
) -> tuple[tuple[ModelTextCandidate, ...], float]:
    """Return allowed full strings and the original top-1 string likelihood.

    Beam search uses the model's CTC blank and allowed character classes.
    Exact CTC likelihoods are recomputed for the retained strings so scores
    are comparable with the unrestricted top-1 text. Values are log likelihoods,
    not calibrated per-character confidence percentages.
    """

    if beam_width < 1 or max_candidates < 1:
        raise ValueError("beam_width and max_candidates must be positive")
    log_probs = _log_probabilities(prediction, characters)
    raw_log_probability = ctc_text_log_probability(log_probs, characters, raw_text)
    indices = [
        index for index, char in enumerate(characters)
        if index and len(char) == 1 and char.upper() in allowed_characters
    ]
    beams: dict[str, tuple[float, float]] = {"": (0.0, _NEG_INF)}
    for row in log_probs:
        next_beams: dict[str, tuple[float, float]] = {}

        def add(prefix: str, blank: float = _NEG_INF, nonblank: float = _NEG_INF) -> None:
            old_blank, old_nonblank = next_beams.get(prefix, (_NEG_INF, _NEG_INF))
            next_beams[prefix] = (
                _log_add(old_blank, blank), _log_add(old_nonblank, nonblank)
            )

        for prefix, (blank, nonblank) in beams.items():
            total = _log_add(blank, nonblank)
            add(prefix, blank=total + float(row[0]))
            for index in indices:
                char = characters[index]
                emission = float(row[index])
                if prefix.endswith(char):
                    add(prefix, nonblank=nonblank + emission)
                    add(prefix + char, nonblank=blank + emission)
                else:
                    add(prefix + char, nonblank=total + emission)
        beams = dict(
            sorted(
                next_beams.items(),
                key=lambda item: _log_add(*item[1]),
                reverse=True,
            )[:beam_width]
        )

    # Different model classes (e.g. 'h' and 'H') can normalize to one code.
    ranked: dict[str, float] = {}
    for text in beams:
        normalized = text.upper()
        if not normalized or any(char not in allowed_characters for char in normalized):
            continue
        score = ctc_text_log_probability(log_probs, characters, text)
        ranked[normalized] = max(ranked.get(normalized, _NEG_INF), score)
    candidates = tuple(
        ModelTextCandidate(text, score)
        for text, score in sorted(ranked.items(), key=lambda item: item[1], reverse=True)[:max_candidates]
    )
    return candidates, raw_log_probability


class _CapturingSession:
    def __init__(self, delegate: Any, batches: list[np.ndarray]) -> None:
        self._delegate = delegate
        self._batches = batches

    def __call__(self, batch: np.ndarray) -> Any:
        output = self._delegate(batch)
        if isinstance(output, (tuple, list)) and output:
            self._batches.append(np.asarray(output[0]))
        return output

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class CandidateTextRecognizer:
    """Append CTC candidate evidence to RapidOCR recognition results."""

    def __init__(self, recognizer: Any, allowed_characters: frozenset[str]) -> None:
        self._recognizer = recognizer
        self._allowed_characters = allowed_characters
        self._lock = Lock()

    def __call__(
        self, img_list: np.ndarray | list[np.ndarray], return_word_box: bool = False
    ) -> tuple[list[tuple[Any, ...]], float]:
        images = [img_list] if isinstance(img_list, np.ndarray) else img_list
        with self._lock:
            batches: list[np.ndarray] = []
            session = self._recognizer.session
            self._recognizer.session = _CapturingSession(session, batches)
            try:
                results, elapsed = self._recognizer(images, return_word_box)
            finally:
                self._recognizer.session = session

        if return_word_box or not images or not batches:
            return results, elapsed
        characters = tuple(self._recognizer.postprocess_op.character)
        order = np.argsort(np.array([img.shape[1] / img.shape[0] for img in images]))
        evidence: list[dict[str, object] | None] = [None] * len(images)
        sorted_index = 0
        for batch in batches:
            if batch.ndim != 3 or sorted_index + batch.shape[0] > len(images):
                _LOG.warning("RapidOCR recognition output shape changed; CTC candidates disabled")
                return results, elapsed
            for row in batch:
                original_index = int(order[sorted_index])
                sorted_index += 1
                raw_text = str(results[original_index][0])
                if raw_text and all(
                    char.isspace() or char.upper() in self._allowed_characters
                    for char in raw_text
                ):
                    evidence[original_index] = {}
                    continue
                try:
                    candidates, raw_log_probability = decode_ctc_candidates(
                        row, characters, self._allowed_characters, raw_text
                    )
                except ValueError as exc:
                    _LOG.warning("RapidOCR CTC candidates unavailable: %s", exc)
                    return results, elapsed
                evidence[original_index] = {
                    "model_candidates": candidates,
                    "model_raw_log_probability": raw_log_probability,
                }
        if sorted_index != len(results) or any(item is None for item in evidence):
            _LOG.warning("RapidOCR recognition batch mapping changed; CTC candidates disabled")
            return results, elapsed
        return [tuple(result) + (item,) for result, item in zip(results, evidence)], elapsed
