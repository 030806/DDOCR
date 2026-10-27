"""Spatially consolidate OCR variants into one result per physical code region."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, replace
import math

from .config import DemoConfig
from .models import CodeAssessment, OCRDetection
from .rules import (
    ALLOWED_CHARACTERS,
    TerminalCodeRules,
    contains_only_allowed_characters,
    normalize_terminal_text,
)


@dataclass(frozen=True)
class PostprocessResult:
    detections: list[OCRDetection]
    audit_records: list[dict[str, object]]


@dataclass
class _Cluster:
    cluster_id: str
    representative: OCRDetection
    members: list[OCRDetection]


def _bounds(detection: OCRDetection) -> tuple[float, float, float, float]:
    points = [point for point in detection.text_bbox_original if len(point) >= 2]
    if not points:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _area(detection: OCRDetection) -> float:
    x1, y1, x2, y2 = _bounds(detection)
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _intersection_area(left: OCRDetection, right: OCRDetection) -> float:
    lx1, ly1, lx2, ly2 = _bounds(left)
    rx1, ry1, rx2, ry2 = _bounds(right)
    width = max(0.0, min(lx2, rx2) - max(lx1, rx1))
    height = max(0.0, min(ly2, ry2) - max(ly1, ry1))
    return width * height


def _iou(left: OCRDetection, right: OCRDetection) -> float:
    intersection = _intersection_area(left, right)
    union = _area(left) + _area(right) - intersection
    return intersection / union if union > 0 else 0.0


def _center_inside(inner: OCRDetection, outer: OCRDetection) -> bool:
    ix1, iy1, ix2, iy2 = _bounds(inner)
    ox1, oy1, ox2, oy2 = _bounds(outer)
    center_x = (ix1 + ix2) / 2
    center_y = (iy1 + iy2) / 2
    return ox1 <= center_x <= ox2 and oy1 <= center_y <= oy2


def _containment(inner: OCRDetection, outer: OCRDetection) -> float:
    inner_area = _area(inner)
    return _intersection_area(inner, outer) / inner_area if inner_area > 0 else 0.0


def _belongs_to_cluster(
    detection: OCRDetection,
    representative: OCRDetection,
    config: DemoConfig,
) -> bool:
    if _iou(detection, representative) >= config.cluster_iou_threshold:
        return True
    smaller, larger = (
        (detection, representative)
        if _area(detection) <= _area(representative)
        else (representative, detection)
    )
    return (
        _containment(smaller, larger) >= config.cluster_containment_threshold
        and _center_inside(smaller, larger)
    )


def _make_clusters(
    detections: list[OCRDetection],
    config: DemoConfig,
) -> list[_Cluster]:
    by_roi: dict[str, list[OCRDetection]] = defaultdict(list)
    for detection in detections:
        by_roi[detection.roi_id].append(detection)

    clusters: list[_Cluster] = []
    for roi_id in sorted(by_roi):
        ordered = sorted(
            by_roi[roi_id],
            key=lambda item: (-_area(item), _bounds(item)[1], _bounds(item)[0]),
        )
        roi_clusters: list[_Cluster] = []
        for detection in ordered:
            target = next(
                (
                    cluster
                    for cluster in roi_clusters
                    if _belongs_to_cluster(detection, cluster.representative, config)
                ),
                None,
            )
            if target is None:
                target = _Cluster(
                    cluster_id=f"{roi_id}-cluster-{len(roi_clusters) + 1:03d}",
                    representative=detection,
                    members=[],
                )
                roi_clusters.append(target)
            target.members.append(detection)
        clusters.extend(roi_clusters)
    return clusters


_MATCH_PRIORITY = {
    "exact_library": 4,
    "base_regex": 3,
    "extended_regex": 2,
    "one_character_correction": 1,
    "model_probability_correction": 1,
}


def _assessed(
    detection: OCRDetection,
    rules: TerminalCodeRules,
    config: DemoConfig,
) -> OCRDetection:
    assessment = rules.assess(detection.raw_text)
    raw = normalize_terminal_text(detection.raw_text)
    raw_log_probability = detection.model_raw_log_probability
    if (
        not contains_only_allowed_characters(raw)
        and raw_log_probability is not None
        and math.isfinite(raw_log_probability)
    ):
        minimum_log_ratio = math.log(config.ctc_min_relative_probability)
        for candidate in detection.model_candidates:
            text = normalize_terminal_text(candidate.text)
            if not math.isfinite(candidate.log_probability):
                continue
            if candidate.log_probability - raw_log_probability < minimum_log_ratio:
                continue
            if len(text) != len(raw) or not contains_only_allowed_characters(text):
                continue
            changed = [index for index, (before, after) in enumerate(zip(raw, text)) if before != after]
            if len(changed) != 1 or raw[changed[0]] in ALLOWED_CHARACTERS:
                continue
            replacement = rules.assess(text)
            if replacement.match_method not in {"exact_library", "base_regex", "extended_regex"}:
                continue
            assessment = replace(
                replacement,
                raw_text=detection.raw_text,
                normalized_text=raw,
                match_method="model_probability_correction",
                edit_count=1,
                review_status="review_required",
            )
            break
    return replace(detection, assessment=assessment)


def _score(detection: OCRDetection) -> float:
    return detection.ocr_score if detection.ocr_score is not None else 0.0


def _candidate_rank(group: list[OCRDetection]) -> tuple[float, ...]:
    assessments = [item.assessment for item in group if item.assessment is not None]
    match_priority = max(_MATCH_PRIORITY.get(item.match_method, 0) for item in assessments)
    rotations = len({item.rotation for item in group})
    edit_counts = [item.edit_count for item in assessments if item.edit_count is not None]
    best_edit_count = min(edit_counts) if edit_counts else 99
    return (
        float(match_priority),
        float(rotations),
        float(-best_edit_count),
        max(_score(item) for item in group),
        max(_area(item) for item in group),
    )


def _source_rank(detection: OCRDetection) -> tuple[float, ...]:
    assessment = detection.assessment
    priority = _MATCH_PRIORITY.get(assessment.match_method, 0) if assessment else 0
    edit_count = assessment.edit_count if assessment and assessment.edit_count is not None else 99
    return (float(priority), float(-edit_count), _score(detection), _area(detection))


def _audit_record(
    detection: OCRDetection,
    cluster_id: str,
    disposition: str,
) -> dict[str, object]:
    assessment: CodeAssessment | None = detection.assessment
    record: dict[str, object] = {
        "cluster_id": cluster_id,
        "roi_id": detection.roi_id,
        "raw_text": detection.raw_text,
        "ocr_score": detection.ocr_score,
        "rotation": detection.rotation,
        "scale": detection.scale,
        "text_bbox_original": detection.text_bbox_original,
        "disposition": disposition,
    }
    if assessment is not None:
        record.update(asdict(assessment))
    if detection.model_candidates:
        record["model_candidates"] = [asdict(candidate) for candidate in detection.model_candidates]
        record["model_raw_log_probability"] = detection.model_raw_log_probability
    return record


def _is_spatial_fragment(
    detection: OCRDetection,
    representative: OCRDetection,
    config: DemoConfig,
) -> bool:
    representative_area = _area(representative)
    return (
        detection is not representative
        and representative_area > 0
        and _area(detection) <= representative_area * config.fragment_max_area_ratio
        and _containment(detection, representative) >= config.cluster_containment_threshold
        and _center_inside(detection, representative)
    )


def _horizontal_fragment_pair(left: OCRDetection, right: OCRDetection) -> bool:
    """Accept a right-hand center inside the left quadrilateral's text band."""
    if left.roi_id != right.roi_id:
        return False
    lx1, ly1, lx2, ly2 = _bounds(left)
    rx1, ry1, rx2, ry2 = _bounds(right)
    center_x, center_y = (rx1 + rx2) / 2, (ry1 + ry2) / 2
    if lx2 <= lx1 or ly2 <= ly1 or rx2 <= rx1 or ry2 <= ry1:
        return False
    if center_x <= (lx1 + lx2) / 2:
        return False
    quad = _horizontal_quad(left)
    if quad is not None:
        top_dx = quad[1][0] - quad[0][0]
        bottom_dx = quad[2][0] - quad[3][0]
        if top_dx > 0 and bottom_dx > 0:
            top_y = quad[0][1] + (quad[1][1] - quad[0][1]) * (center_x - quad[0][0]) / top_dx
            bottom_y = quad[3][1] + (quad[2][1] - quad[3][1]) * (center_x - quad[3][0]) / bottom_dx
        else:
            top_y, bottom_y = ly1, ly2
    else:
        top_y, bottom_y = ly1, ly2
    return min(top_y, bottom_y) <= center_y <= max(top_y, bottom_y)


def _horizontal_quad(detection: OCRDetection) -> list[list[float]] | None:
    """Normalize four corners to left-top, right-top, right-bottom, left-bottom."""
    if len(detection.text_bbox_original) != 4:
        return None
    points = sorted(
        ([float(point[0]), float(point[1])] for point in detection.text_bbox_original),
        key=lambda point: (point[0], point[1]),
    )
    left = sorted(points[:2], key=lambda point: point[1])
    right = sorted(points[2:], key=lambda point: point[1])
    return [left[0], right[0], right[1], left[1]]


def _merged_polygon(left: OCRDetection, right: OCRDetection) -> list[list[float]]:
    left_quad, right_quad = _horizontal_quad(left), _horizontal_quad(right)
    if left_quad is not None and right_quad is not None:
        return [
            left_quad[0], right_quad[1],
            right_quad[2], left_quad[3],
        ]
    lx1, ly1, lx2, ly2 = _bounds(left)
    rx1, ry1, rx2, ry2 = _bounds(right)
    return [[min(lx1, rx1), min(ly1, ry1)], [max(lx2, rx2), min(ly1, ry1)],
            [max(lx2, rx2), max(ly2, ry2)], [min(lx1, rx1), max(ly2, ry2)]]


def _merge_horizontal_fragments(
    detections: list[OCRDetection], rules: TerminalCodeRules,
) -> tuple[list[OCRDetection], list[dict[str, object]]]:
    remaining = detections[:]
    audit: list[dict[str, object]] = []
    while True:
        candidates = [
            ((_bounds(right)[0] + _bounds(right)[2]) / 2 -
             (_bounds(left)[0] + _bounds(left)[2]) / 2, i, j)
            for i, left in enumerate(remaining)
            for j, right in enumerate(remaining)
            if i != j and _horizontal_fragment_pair(left, right)
        ]
        if not candidates:
            return remaining, audit
        _, left_index, right_index = min(candidates)
        left, right = remaining[left_index], remaining[right_index]
        raw_text = left.raw_text.strip() + right.raw_text.strip()
        assessment = rules.assess(raw_text)
        merged = replace(
            left, raw_text=raw_text, ocr_score=min(_score(left), _score(right)),
            text_bbox_original=_merged_polygon(left, right), assessment=assessment,
            output_text=assessment.output_text,
            is_unresolved=assessment.review_status == "unresolved" or not bool(assessment.output_text),
            cluster_id=f"{left.cluster_id}+{right.cluster_id}",
        )
        audit.append({
            "disposition": "merged_horizontal_fragments", "roi_id": left.roi_id,
            "source_cluster_ids": [left.cluster_id, right.cluster_id], "raw_text": raw_text,
            "text_bbox_original": merged.text_bbox_original,
        })
        remaining = [item for index, item in enumerate(remaining) if index not in {left_index, right_index}]
        remaining.append(merged)


def postprocess_detections(
    detections: list[OCRDetection],
    rules: TerminalCodeRules,
    config: DemoConfig,
) -> PostprocessResult:
    """Assess, cluster, and reduce raw OCR detections without losing audit data."""

    final_detections: list[OCRDetection] = []
    audit_records: list[dict[str, object]] = []
    for cluster in _make_clusters(detections, config):
        members = [_assessed(item, rules, config) for item in cluster.members]
        representative = next(
            item for item in members if item is not None and item.raw_text == cluster.representative.raw_text
            and item.text_bbox_original == cluster.representative.text_bbox_original
            and item.rotation == cluster.representative.rotation
        )
        groups: dict[str, list[OCRDetection]] = defaultdict(list)
        for member in members:
            if _is_spatial_fragment(member, representative, config):
                continue
            if member.assessment and member.assessment.output_text:
                groups[member.assessment.output_text].append(member)

        if groups:
            output_text, winning_group = max(
                groups.items(),
                key=lambda item: (_candidate_rank(item[1]), item[0]),
            )
            selected = max(winning_group, key=_source_rank)
            final_detections.append(
                replace(
                    selected,
                    output_text=output_text,
                    cluster_id=cluster.cluster_id,
                    is_unresolved=bool(selected.assessment and selected.assessment.review_status == "unresolved"),
                )
            )
            for member in members:
                disposition = "selected" if member is selected else "rejected_candidate"
                if _is_spatial_fragment(member, representative, config):
                    disposition = "absorbed_fragment"
                audit_records.append(_audit_record(member, cluster.cluster_id, disposition))
            continue

        qualifying = [
            item
            for item in members
            if not _is_spatial_fragment(item, representative, config)
            and item.raw_text.strip()
            and (item.ocr_score is None or item.ocr_score >= config.unresolved_min_score)
        ]
        if qualifying:
            selected = max(qualifying, key=lambda item: (_area(item), _score(item)))
            final_detections.append(
                replace(
                    selected,
                    output_text="",
                    cluster_id=cluster.cluster_id,
                    is_unresolved=True,
                )
            )
            for member in members:
                disposition = "unresolved_selected" if member is selected else "rejected_candidate"
                if _is_spatial_fragment(member, representative, config):
                    disposition = "absorbed_fragment"
                audit_records.append(_audit_record(member, cluster.cluster_id, disposition))
        else:
            for member in members:
                disposition = (
                    "absorbed_fragment"
                    if _is_spatial_fragment(member, representative, config)
                    else "below_unresolved_threshold"
                )
                audit_records.append(
                    _audit_record(member, cluster.cluster_id, disposition)
                )

    final_detections, fragment_audit = _merge_horizontal_fragments(final_detections, rules)
    audit_records.extend(fragment_audit)
    final_detections.sort(
        key=lambda item: (item.roi_id, _bounds(item)[1], _bounds(item)[0])
    )
    return PostprocessResult(final_detections, audit_records)
