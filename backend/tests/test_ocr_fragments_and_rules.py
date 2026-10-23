from dataclasses import replace

from app.vendor.terminal_ocr_demo.config import DemoConfig
from app.vendor.terminal_ocr_demo.models import OCRDetection
from app.vendor.terminal_ocr_demo.postprocess import postprocess_detections
from app.vendor.terminal_ocr_demo.rules import (
    TerminalCodeRules, contains_only_allowed_characters, normalize_terminal_text,
)


def detection(text, x1, y1, x2, y2):
    return OCRDetection(
        roi_id="roi-1", raw_text=text, ocr_score=0.9,
        text_bbox_original=[[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        rotation=0, scale=2.0,
    )


def rules(tmp_path):
    library = tmp_path / "codes.csv"
    library.write_text("code,count,rule_status\nX16,1,base\n", encoding="utf-8")
    return TerminalCodeRules.from_csv(library)


def test_horizontal_fragments_merge_and_keep_unconfirmed_complete_code(tmp_path):
    result = postprocess_detections(
        [detection("X16B", 10, 10, 60, 30), detection("6", 66, 10, 77, 30)],
        rules(tmp_path), DemoConfig(),
    )
    assert len(result.detections) == 1
    assert result.detections[0].raw_text == "X16B6"
    assert result.detections[0].is_unresolved
    assert any(record["disposition"] == "merged_horizontal_fragments" for record in result.audit_records)


def test_horizontal_fragments_do_not_merge_different_rows(tmp_path):
    result = postprocess_detections(
        [detection("X16B", 10, 10, 60, 30), detection("6", 66, 40, 77, 60)],
        rules(tmp_path), DemoConfig(),
    )
    assert len(result.detections) == 2


def test_text_band_merges_distant_fragments_from_different_rotation_variants(tmp_path):
    left = detection("X", 10, 10, 30, 30)
    right = detection("6", 100, 10, 115, 30)
    right = replace(right, rotation=180)
    result = postprocess_detections([left, right], rules(tmp_path), DemoConfig())
    assert [item.raw_text for item in result.detections] == ["X6"]
    assert result.detections[0].output_text == "X6"


def test_text_band_follows_sloping_four_point_box(tmp_path):
    left = detection("X", 10, 10, 30, 30)
    left = replace(left, text_bbox_original=[[10, 10], [30, 20], [30, 40], [10, 30]])
    right = detection("8", 75, 42, 85, 62)
    result = postprocess_detections([left, right], rules(tmp_path), DemoConfig())
    assert [item.raw_text for item in result.detections] == ["X8"]


def test_hyphen_and_slash_are_allowed_characters_but_not_confirmed_codes(tmp_path):
    code_rules = rules(tmp_path)
    for value in ("X-16", "X/16"):
        assert contains_only_allowed_characters(value)
        assert normalize_terminal_text(value) == value
        assert code_rules.assess(value).review_status == "unresolved"
    assert not contains_only_allowed_characters("X（16")
    masked = code_rules.assess("X（16")
    assert masked.output_text == "X#16"
    assert masked.rule_status == "masked_base_candidate"
    assert masked.review_status == "unresolved"
    assert masked.recommended_code is None


def test_masked_library_matches_are_suggestions_not_confirmed(tmp_path):
    code_rules = rules(tmp_path)
    masked = code_rules.assess("X（6")
    assert masked.output_text == "X#6"
    assert masked.candidate_codes == ("X16",)
    assert masked.recommended_code is None
    assert masked.review_status == "unresolved"


def test_invalid_latin_character_needs_model_evidence_or_remains_masked(tmp_path):
    library = tmp_path / "codes.csv"
    library.write_text("code,count,rule_status\nK21C,1,base\n", encoding="utf-8")
    assessment = TerminalCodeRules.from_csv(library).assess("K2IC")
    assert assessment.output_text == "K2#C"
    assert assessment.candidate_codes == ("K21C",)
    assert assessment.recommended_code is None
    assert assessment.review_status == "unresolved"

