"""Ferrule-code normalization, scheme-aware validation, and safe correction."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Pattern

from .config import DemoConfig
from .models import CodeAssessment


_NOISE_PUNCTUATION = str.maketrans("", "", ".()[]{}:;,_")
_DASH_TRANSLATION = str.maketrans({"－": "-", "—": "-", "–": "-", "‑": "-"})
_SLASH_TRANSLATION = str.maketrans({"／": "/"})
_CONFUSION_GROUPS = ("8B", "0OD", "1IJ", "5S", "2Z")
_VALID_SCHEMES = ("existing", "temp", "new")


def normalize_terminal_text(raw_text: str) -> str:
    """Normalize case/width/whitespace while preserving structural separators."""

    normalized = unicodedata.normalize("NFKC", raw_text)
    compact = "".join(character for character in normalized if not character.isspace())
    return compact.translate(_DASH_TRANSLATION).translate(_SLASH_TRANSLATION)


def _hamming_distance(left: str, right: str) -> int | None:
    if len(left) != len(right):
        return None
    return sum(a != b for a, b in zip(left, right))


def _separator_signature(value: str) -> tuple[tuple[int, str], ...]:
    return tuple((index, char) for index, char in enumerate(value) if not char.isalnum())


@dataclass(frozen=True)
class RulePattern:
    rule_id: str
    scheme: str
    expression: Pattern[str]
    match_method: str
    rule_level: str
    rule_status: str
    confidence: float


@dataclass(frozen=True)
class TerminalCodeRules:
    library_codes: frozenset[str]
    library_statuses: dict[str, str]
    library_schemes: dict[str, frozenset[str]]
    patterns_by_scheme: dict[str, tuple[RulePattern, ...]]
    base_pattern: Pattern[str]
    extended_pattern: Pattern[str]
    numbering_scheme: str = "auto"

    @classmethod
    def from_csv(
        cls,
        path: Path,
        base_pattern: str = DemoConfig.base_code_pattern,
        extended_pattern: str = DemoConfig.extended_code_pattern,
    ) -> "TerminalCodeRules":
        statuses, schemes = cls._read_library(path, default_scheme="existing")
        patterns = {
            "existing": (
                RulePattern(
                    "legacy_base", "existing", re.compile(base_pattern),
                    "base_regex", "base", "base_outside_library", 0.85,
                ),
                RulePattern(
                    "legacy_extended", "existing", re.compile(extended_pattern),
                    "extended_regex", "extended", "extended_pending", 0.70,
                ),
                RulePattern(
                    "open_numeric", "existing", re.compile(r"^\d+$"),
                    "open_numeric_regex", "open", "open_for_review", 0.55,
                ),
                RulePattern(
                    "open_alphabetic", "existing", re.compile(r"^[A-Za-z]+$"),
                    "open_alphabetic_regex", "open", "open_for_review", 0.55,
                ),
            )
        }
        return cls(
            library_codes=frozenset(statuses),
            library_statuses=statuses,
            library_schemes=schemes,
            patterns_by_scheme=patterns,
            base_pattern=re.compile(base_pattern),
            extended_pattern=re.compile(extended_pattern),
        )

    @classmethod
    def from_config(cls, config: DemoConfig) -> "TerminalCodeRules":
        statuses, schemes = cls._read_library(
            config.scheme_code_library_path,
            default_scheme="existing",
        )
        with Path(config.rule_family_path).open("r", encoding="utf-8") as handle:
            rule_config = json.load(handle)
        patterns: dict[str, tuple[RulePattern, ...]] = {}
        for scheme, values in rule_config["schemes"].items():
            patterns[scheme] = tuple(
                RulePattern(
                    rule_id=item["id"],
                    scheme=scheme,
                    expression=re.compile(item["expression"], re.IGNORECASE),
                    match_method=item["match_method"],
                    rule_level=item["level"],
                    rule_status=item["status"],
                    confidence=float(item["confidence"]),
                )
                for item in values["patterns"]
            )
        return cls(
            library_codes=frozenset(statuses),
            library_statuses=statuses,
            library_schemes=schemes,
            patterns_by_scheme=patterns,
            base_pattern=re.compile(config.base_code_pattern, re.IGNORECASE),
            extended_pattern=re.compile(config.extended_code_pattern, re.IGNORECASE),
            numbering_scheme=config.numbering_scheme or "auto",
        )

    @staticmethod
    def _read_library(
        path: Path,
        default_scheme: str,
    ) -> tuple[dict[str, str], dict[str, frozenset[str]]]:
        statuses: dict[str, str] = {}
        mutable_schemes: dict[str, set[str]] = {}
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "code" not in reader.fieldnames:
                raise ValueError(f"编号库缺少 code 列: {path}")
            for row in reader:
                code = normalize_terminal_text(row.get("code", ""))
                if not code:
                    continue
                scheme = (row.get("scheme") or default_scheme).strip().lower()
                if scheme not in _VALID_SCHEMES:
                    raise ValueError(f"未知编号体系 {scheme!r}: {path}")
                statuses[code] = (row.get("rule_status") or "library").strip()
                mutable_schemes.setdefault(code, set()).add(scheme)
        return statuses, {
            code: frozenset(code_schemes)
            for code, code_schemes in mutable_schemes.items()
        }

    def assess(self, raw_text: str, numbering_scheme: str | None = None) -> CodeAssessment:
        numbering_scheme = numbering_scheme or self.numbering_scheme
        if numbering_scheme not in (*_VALID_SCHEMES, "auto"):
            raise ValueError(f"未知编号体系: {numbering_scheme}")
        normalized = normalize_terminal_text(raw_text)
        active_schemes = (
            tuple(self.patterns_by_scheme)
            if numbering_scheme == "auto"
            else (numbering_scheme,)
        )
        # Keep the host application's illegal-character handling and CTC gate.
        from .rules import TerminalCodeRules as LegacyRules, contains_only_allowed_characters
        if not contains_only_allowed_characters(raw_text):
            codes = frozenset(code for code in self.library_codes
                              if self.library_schemes[code].intersection(active_schemes))
            assessment = LegacyRules(
                codes, self.library_statuses, self.base_pattern, self.extended_pattern,
            ).assess(raw_text)
            return replace(assessment, requested_scheme=numbering_scheme)
        variants: list[tuple[str, tuple[str, ...]]] = [(normalized, ())]
        noise_stripped = normalized.translate(_NOISE_PUNCTUATION)
        if noise_stripped != normalized:
            variants.append((noise_stripped, ("removed_nonstructural_punctuation",)))

        exact_hits: list[tuple[str, str, tuple[str, ...]]] = []
        for value, actions in variants:
            for scheme in active_schemes:
                case_hits = [code for code in self.library_codes if code.casefold() == value.casefold()]
                hit = value if value in self.library_codes else case_hits[0] if len(case_hits) == 1 else None
                if hit and scheme in self.library_schemes[hit]:
                    exact_hits.append((hit, scheme, actions))
        if exact_hits:
            value, scheme, actions = min(
                exact_hits,
                key=lambda item: (len(item[2]), active_schemes.index(item[1]), item[0]),
            )
            output_value = normalized.translate(_NOISE_PUNCTUATION) if actions else normalized
            return self._assessment(
                raw_text,
                normalized,
                output_text=output_value,
                recommended_code=output_value,
                candidate_codes=(output_value,),
                rule_status=self.library_statuses.get(value, "library"),
                match_method="exact_library",
                edit_count=0,
                review_status="confirmed" if not actions else "review_required",
                requested_scheme=numbering_scheme,
                matched_scheme=scheme,
                matched_rule_id="known_code_library",
                rule_level="exact",
                review_reason=None if not actions else "识别结果含非结构性标点，已规范化后命中编号库",
                normalization_actions=actions,
                rule_confidence=1.0 if not actions else 0.92,
            )

        pattern_hits: list[tuple[float, int, str, tuple[str, ...], RulePattern]] = []
        for value, actions in variants:
            for scheme in active_schemes:
                for pattern in self.patterns_by_scheme.get(scheme, ()):
                    if pattern.expression.fullmatch(value):
                        pattern_hits.append(
                            (pattern.confidence, -len(actions), value, actions, pattern)
                        )
        if pattern_hits:
            _, _, value, actions, pattern = max(
                pattern_hits,
                key=lambda item: (item[0], item[1], -active_schemes.index(item[4].scheme)),
            )
            return self._assessment(
                raw_text,
                normalized,
                output_text=value,
                recommended_code=value,
                candidate_codes=(value,),
                rule_status=pattern.rule_status,
                match_method=pattern.match_method,
                edit_count=0,
                review_status="review_required",
                requested_scheme=numbering_scheme,
                matched_scheme=pattern.scheme,
                matched_rule_id=pattern.rule_id,
                rule_level=pattern.rule_level,
                review_reason="正则命中但不在已知编号库中",
                normalization_actions=actions,
                rule_confidence=pattern.confidence,
            )

        correction_hits: list[tuple[str, str]] = []
        for scheme in active_schemes:
            for candidate in (() if any(c.islower() for c in normalized) else self._correction_candidates(normalized, scheme)):
                correction_hits.append((candidate, scheme))
        unique_candidates = tuple(sorted({item[0] for item in correction_hits}))
        if len(unique_candidates) == 1:
            candidate = unique_candidates[0]
            matched_scheme = next(
                scheme for value, scheme in correction_hits if value == candidate
            )
            return self._assessment(
                raw_text,
                normalized,
                output_text=candidate,
                recommended_code=candidate,
                candidate_codes=unique_candidates,
                rule_status=self.library_statuses.get(candidate, "library"),
                match_method="one_character_correction",
                edit_count=1,
                review_status="review_required",
                requested_scheme=numbering_scheme,
                matched_scheme=matched_scheme,
                matched_rule_id="same_scheme_one_character_correction",
                rule_level="correction",
                review_reason="同一编号体系内发生一次等长字符纠错",
                normalization_actions=(),
                rule_confidence=0.60,
            )
        return self._assessment(
            raw_text,
            normalized,
            output_text="",
            recommended_code=None,
            candidate_codes=unique_candidates,
            rule_status="invalid",
            match_method="ambiguous_correction" if unique_candidates else "unresolved",
            edit_count=1 if unique_candidates else None,
            review_status="unresolved",
            requested_scheme=numbering_scheme,
            matched_scheme=None,
            matched_rule_id=None,
            rule_level=None,
            review_reason=(
                "多个编号体系或规则给出不同纠错结果"
                if unique_candidates
                else "未命中已知编号、正则或安全纠错"
            ),
            normalization_actions=(),
            rule_confidence=0.0,
        )

    def _correction_candidates(self, normalized: str, scheme: str) -> tuple[str, ...]:
        scheme_codes = {
            code for code in self.library_codes if scheme in self.library_schemes[code]
        }
        confusion_hits: set[str] = set()
        for index, character in enumerate(normalized):
            for group in _CONFUSION_GROUPS:
                if character not in group:
                    continue
                for replacement in group:
                    if replacement == character:
                        continue
                    candidate = normalized[:index] + replacement + normalized[index + 1:]
                    if (
                        candidate in scheme_codes
                        and _separator_signature(candidate) == _separator_signature(normalized)
                    ):
                        confusion_hits.add(candidate)
        if confusion_hits:
            return tuple(sorted(confusion_hits))
        hamming_hits = {
            code
            for code in scheme_codes
            if _hamming_distance(normalized, code) == 1
            and _separator_signature(code) == _separator_signature(normalized)
        }
        return tuple(sorted(hamming_hits))

    @staticmethod
    def _assessment(
        raw_text: str,
        normalized_text: str,
        **values: object,
    ) -> CodeAssessment:
        return CodeAssessment(
            raw_text=raw_text,
            normalized_text=normalized_text,
            **values,
        )
