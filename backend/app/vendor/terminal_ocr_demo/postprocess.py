"""Spatially consolidate OCR variants into one result per physical code region."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, replace

from .config import DemoConfig
from .models import CodeAssessment, OCRDetection
from .rules import TerminalCodeRules


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
}


def _assessed(
    detection: OCRDetection,
    rules: TerminalCodeRules,
) -> OCRDetection:
    assessment = rules.assess(detection.raw_text)
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


def postprocess_detections(
    detections: list[OCRDetection],
    rules: TerminalCodeRules,
    config: DemoConfig,
) -> PostprocessResult:
    """Assess, cluster, and reduce raw OCR detections without losing audit data."""

    final_detections: list[OCRDetection] = []
    audit_records: list[dict[str, object]] = []
    for cluster in _make_clusters(detections, config):
        members = [_assessed(item, rules) for item in cluster.members]
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
                    is_unresolved=False,
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

    final_detections.sort(
        key=lambda item: (item.roi_id, _bounds(item)[1], _bounds(item)[0])
    )
    return PostprocessResult(final_detections, audit_records)
