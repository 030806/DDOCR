"""Terminal-code normalization, validation, and constrained correction."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Pattern

from .config import DemoConfig
from .models import CodeAssessment


_REMOVABLE_PUNCTUATION = str.maketrans("", "", "./\\()[]{}:;,_-")
_CONFUSION_GROUPS = ("8B", "0OD", "1IJ", "5S", "2Z")


def normalize_terminal_text(raw_text: str) -> str:
    """Normalize presentation noise without changing recognized letters/digits."""

    compact = "".join(character for character in raw_text if not character.isspace())
    return compact.upper().translate(_REMOVABLE_PUNCTUATION)


def _hamming_distance(left: str, right: str) -> int | None:
    if len(left) != len(right):
        return None
    return sum(a != b for a, b in zip(left, right))


@dataclass(frozen=True)
class TerminalCodeRules:
    library_codes: frozenset[str]
    library_statuses: dict[str, str]
    base_pattern: Pattern[str]
    extended_pattern: Pattern[str]

    @classmethod
    def from_csv(
        cls,
        path: Path,
        base_pattern: str = DemoConfig.base_code_pattern,
        extended_pattern: str = DemoConfig.extended_code_pattern,
    ) -> "TerminalCodeRules":
        statuses: dict[str, str] = {}
        library_path = Path(path).expanduser().resolve()
        with library_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "code" not in reader.fieldnames:
                raise ValueError(f"编号库缺少 code 列: {library_path}")
            for row in reader:
                code = normalize_terminal_text(row.get("code", ""))
                if code:
                    statuses[code] = (row.get("rule_status") or "library").strip()
        return cls(
            library_codes=frozenset(statuses),
            library_statuses=statuses,
            base_pattern=re.compile(base_pattern),
            extended_pattern=re.compile(extended_pattern),
        )

    @classmethod
    def from_config(cls, config: DemoConfig) -> "TerminalCodeRules":
        return cls.from_csv(
            config.code_library_path,
            base_pattern=config.base_code_pattern,
            extended_pattern=config.extended_code_pattern,
        )

    def assess(self, raw_text: str) -> CodeAssessment:
        normalized = normalize_terminal_text(raw_text)
        if normalized in self.library_codes:
            return self._assessment(
                raw_text,
                normalized,
                output_text=normalized,
                recommended_code=normalized,
                candidate_codes=(normalized,),
                rule_status=self.library_statuses.get(normalized, "library"),
                match_method="exact_library",
                edit_count=0,
                review_status="confirmed",
            )
        if self.base_pattern.fullmatch(normalized):
            return self._assessment(
                raw_text,
                normalized,
                output_text=normalized,
                recommended_code=normalized,
                candidate_codes=(normalized,),
                rule_status="base_outside_library",
                match_method="base_regex",
                edit_count=0,
                review_status="review_required",
            )
        if self.extended_pattern.fullmatch(normalized):
            return self._assessment(
                raw_text,
                normalized,
                output_text=normalized,
                recommended_code=normalized,
                candidate_codes=(normalized,),
                rule_status="extended_pending",
                match_method="extended_regex",
                edit_count=0,
                review_status="review_required",
            )

        candidates = self._correction_candidates(normalized)
        if len(candidates) == 1:
            candidate = candidates[0]
            return self._assessment(
                raw_text,
                normalized,
                output_text=candidate,
                recommended_code=candidate,
                candidate_codes=candidates,
                rule_status=self.library_statuses.get(candidate, "library"),
                match_method="one_character_correction",
                edit_count=1,
                review_status="review_required",
            )
        return self._assessment(
            raw_text,
            normalized,
            output_text="",
            recommended_code=None,
            candidate_codes=candidates,
            rule_status="invalid",
            match_method="ambiguous_correction" if candidates else "unresolved",
            edit_count=1 if candidates else None,
            review_status="unresolved",
        )

    def _correction_candidates(self, normalized: str) -> tuple[str, ...]:
        confusion_hits: set[str] = set()
        for index, character in enumerate(normalized):
            for group in _CONFUSION_GROUPS:
                if character not in group:
                    continue
                for replacement in group:
                    if replacement == character:
                        continue
                    candidate = normalized[:index] + replacement + normalized[index + 1 :]
                    if candidate in self.library_codes:
                        confusion_hits.add(candidate)
        if confusion_hits:
            return tuple(sorted(confusion_hits))

        hamming_hits = {
            code
            for code in self.library_codes
            if _hamming_distance(normalized, code) == 1
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
