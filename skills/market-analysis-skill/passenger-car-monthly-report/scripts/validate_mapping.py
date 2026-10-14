"""Validate the minimum contract for a data-source-to-PPT mapping JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ALLOWED_KINDS = {"chart_series", "table_cells", "text_fields", "insight_text"}


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    dashboard = data.get("dashboard")
    if not isinstance(dashboard, dict):
        errors.append("dashboard must be an object")
    else:
        for key in ("name", "url", "as_of"):
            if not dashboard.get(key):
                errors.append(f"dashboard.{key} is required")

    cards = data.get("cards")
    card_ids: set[str] = set()
    if not isinstance(cards, list) or not cards:
        errors.append("cards must be a non-empty array")
    else:
        for index, card in enumerate(cards):
            if not isinstance(card, dict):
                errors.append(f"cards[{index}] must be an object")
                continue
            cid = card.get("id")
            if not cid:
                errors.append(f"cards[{index}].id is required")
            elif cid in card_ids:
                errors.append(f"duplicate card id: {cid}")
            else:
                card_ids.add(cid)
            if not card.get("title"):
                errors.append(f"cards[{index}].title is required")
            if not isinstance(card.get("rows"), list):
                errors.append(f"cards[{index}].rows must be an array")

    targets = data.get("targets")
    seen: set[tuple] = set()
    if not isinstance(targets, list) or not targets:
        errors.append("targets must be a non-empty array")
    else:
        for index, target in enumerate(targets):
            if not isinstance(target, dict):
                errors.append(f"targets[{index}] must be an object")
                continue
            kind = target.get("kind")
            if kind not in ALLOWED_KINDS:
                errors.append(f"targets[{index}].kind is invalid: {kind!r}")
            slide = target.get("slide")
            if not isinstance(slide, int) or slide < 1:
                errors.append(f"targets[{index}].slide must be a positive integer")
            name = target.get("target")
            if not name:
                errors.append(f"targets[{index}].target is required")
            key = (slide, kind, name)
            if key in seen:
                errors.append(f"duplicate target: slide={slide}, kind={kind}, target={name}")
            seen.add(key)
            source = target.get("source_card")
            if source not in card_ids:
                errors.append(f"targets[{index}].source_card not found: {source!r}")
            if not target.get("source_field"):
                errors.append(f"targets[{index}].source_field is required")
            if kind in {"chart_series", "table_cells"} and not target.get("format"):
                errors.append(f"targets[{index}].format is required for {kind}")

    if data.get("zero_denominator_rule") not in {"blank", "dash", "not_applicable", "custom"}:
        errors.append("zero_denominator_rule must be blank, dash, not_applicable, or custom")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mapping", type=Path)
    args = parser.parse_args()
    data = json.loads(args.mapping.read_text(encoding="utf-8"))
    errors = validate(data)
    if errors:
        print(json.dumps({"status": "failed", "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"status": "passed", "cards": len(data["cards"]), "targets": len(data["targets"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
