"""Validate the minimum traceability contract for monthly-report narratives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ALLOWED_ANOMALIES = {
    "reversal",
    "streak_change",
    "structural_divergence",
    "share_or_rank_shift",
    "contribution_concentration",
    "ordinary_change",
}
ALLOWED_GRADES = {"A", "B", "C", "U"}
ALLOWED_CERTAINTY = {"supported", "qualified", "unverified"}


def _nonempty_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(str(item).strip() for item in value)


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    if not str(data.get("run_id", "")).strip():
        errors.append("run_id is required")
    if not str(data.get("report_month", "")).strip():
        errors.append("report_month is required")

    evidence = data.get("evidence")
    evidence_by_id: dict[str, dict] = {}
    if not isinstance(evidence, list):
        errors.append("evidence must be an array")
        evidence = []
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            errors.append(f"evidence[{index}] must be an object")
            continue
        evidence_id = str(item.get("id", "")).strip()
        if not evidence_id:
            errors.append(f"evidence[{index}].id is required")
        elif evidence_id in evidence_by_id:
            errors.append(f"duplicate evidence id: {evidence_id}")
        else:
            evidence_by_id[evidence_id] = item
        if item.get("grade") not in ALLOWED_GRADES:
            errors.append(f"evidence[{index}].grade must be A, B, C, or U")
        for key in ("source_type", "source_name", "published_at", "applicable_month", "summary"):
            if not str(item.get(key, "")).strip():
                errors.append(f"evidence[{index}].{key} is required")
        if not _nonempty_list(item.get("entities")):
            errors.append(f"evidence[{index}].entities must be a non-empty array")

    slides = data.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("slides must be a non-empty array")
        return errors

    seen_slides: set[int] = set()
    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            errors.append(f"slides[{index}] must be an object")
            continue
        number = slide.get("slide")
        if not isinstance(number, int) or number < 1:
            errors.append(f"slides[{index}].slide must be a positive integer")
        elif number in seen_slides:
            errors.append(f"duplicate slide: {number}")
        else:
            seen_slides.add(number)
        if not str(slide.get("headline", "")).strip():
            errors.append(f"slides[{index}].headline is required")
        anomaly = slide.get("anomaly")
        if not isinstance(anomaly, dict):
            errors.append(f"slides[{index}].anomaly must be an object")
            continue
        if anomaly.get("type") not in ALLOWED_ANOMALIES:
            errors.append(f"slides[{index}].anomaly.type is invalid")
        if not _nonempty_list(anomaly.get("fact_ids")):
            errors.append(f"slides[{index}].anomaly.fact_ids must be a non-empty array")

        claims = slide.get("body_claims", [])
        if not isinstance(claims, list):
            errors.append(f"slides[{index}].body_claims must be an array")
            continue
        for claim_index, claim in enumerate(claims):
            prefix = f"slides[{index}].body_claims[{claim_index}]"
            if not isinstance(claim, dict):
                errors.append(f"{prefix} must be an object")
                continue
            if not str(claim.get("claim", "")).strip():
                errors.append(f"{prefix}.claim is required")
            if not _nonempty_list(claim.get("fact_ids")):
                errors.append(f"{prefix}.fact_ids must be a non-empty array")
            certainty = claim.get("certainty")
            if certainty not in ALLOWED_CERTAINTY:
                errors.append(f"{prefix}.certainty is invalid")
            ids = claim.get("evidence_ids", [])
            if not isinstance(ids, list):
                errors.append(f"{prefix}.evidence_ids must be an array")
                continue
            missing = [evidence_id for evidence_id in ids if evidence_id not in evidence_by_id]
            if missing:
                errors.append(f"{prefix}.evidence_ids not found: {missing}")
            grades = {evidence_by_id[evidence_id].get("grade") for evidence_id in ids if evidence_id in evidence_by_id}
            if certainty == "supported" and not grades.intersection({"A", "B"}):
                errors.append(f"{prefix} marked supported without A/B evidence")
            if certainty == "qualified" and not grades.intersection({"A", "B", "C"}):
                errors.append(f"{prefix} marked qualified without A/B/C evidence")
            if certainty == "unverified" and ids:
                errors.append(f"{prefix} marked unverified but has evidence_ids")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_package", type=Path)
    args = parser.parse_args()
    data = json.loads(args.evidence_package.read_text(encoding="utf-8"))
    errors = validate(data)
    if errors:
        print(json.dumps({"status": "failed", "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    print(
        json.dumps(
            {
                "status": "passed",
                "slides": len(data["slides"]),
                "evidence": len(data.get("evidence", [])),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
