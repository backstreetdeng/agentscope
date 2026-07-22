"""Validate the monthly Skill distribution without calling a model or network."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

try:
    import yaml
except ImportError as exc:  # pragma: no cover - actionable environment failure
    raise SystemExit("PyYAML is required. Run: python -m pip install -r requirements.txt") from exc


ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "profiles" / "passenger_vehicle_monthly"

REQUIRED_FILES = (
    "SKILL.md",
    "README.md",
    "manifest.yaml",
    "requirements.txt",
    "install.ps1",
    "config/market_analysis.example.json",
    "profiles/passenger_vehicle_monthly/profile.yaml",
    "profiles/passenger_vehicle_monthly/page_specs.yaml",
    "profiles/passenger_vehicle_monthly/quality_rules.yaml",
    "profiles/passenger_vehicle_monthly/narrative_rules.md",
    "profiles/passenger_vehicle_monthly/data_contract.md",
    "profiles/passenger_vehicle_monthly/assets/monthly_report_template.pptx",
    "profiles/passenger_vehicle_monthly/assets/demo_monthly_data.xlsx",
    "payload/skills/market_analysis_skill/runtime.py",
    "payload/skills/market_analysis_skill/research_evidence.py",
    "payload/skills/agent_reach/adapter.py",
    "payload/utils/monthly_report_pptx.py",
    "evals/evals.json",
)

EXPECTED_PAGE_IDS = (
    "vehicle_category",
    "vehicle_level",
    "sedan_level",
    "suv_level",
    "mpv_level",
)

EXPECTED_OUTPUT_RULES = {
    "report_structure",
    "overall_judgement_first",
    "representative_models",
    "causal_evidence",
    "data_consistency",
    "hidden_evidence_ids",
    "positive_sign",
    "slide_overflow",
}


def load_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a YAML object")
    return payload


def validate_zip_asset(path: Path, kind: str) -> dict[str, object]:
    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            if kind == "pptx":
                slide_pattern = re.compile(r"^ppt/slides/slide\d+\.xml$")
                slides = sorted(name for name in names if slide_pattern.match(name))
                if "ppt/presentation.xml" not in names or len(slides) < 5:
                    raise ValueError("PPTX template must contain at least five slides")
                return {"path": str(path.relative_to(ROOT)), "slides": len(slides)}
            if "xl/workbook.xml" not in names:
                raise ValueError("XLSX demo dataset is missing xl/workbook.xml")
            worksheet_pattern = re.compile(r"^xl/worksheets/sheet\d+\.xml$")
            worksheets = sorted(name for name in names if worksheet_pattern.match(name))
            if not worksheets:
                raise ValueError("XLSX demo dataset contains no worksheets")
            return {"path": str(path.relative_to(ROOT)), "worksheets": len(worksheets)}
    except BadZipFile as exc:
        raise ValueError(f"{path.name} is not a valid Office Open XML file") from exc


def scan_secrets() -> list[str]:
    findings: list[str] = []
    text_suffixes = {".md", ".yaml", ".yml", ".json", ".py", ".ps1", ".txt"}
    patterns = (
        re.compile(r"(?i)(api[_-]?key|token|secret)\s*[=:]\s*['\"]?[A-Za-z0-9_-]{20,}"),
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    )
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        if "dist" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in patterns):
            findings.append(str(path.relative_to(ROOT)))
    return findings


def validate() -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    details: dict[str, object] = {}

    missing = [relative for relative in REQUIRED_FILES if not (ROOT / relative).is_file()]
    if missing:
        errors.extend(f"missing required file: {item}" for item in missing)

    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "details": details}

    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    skill_lines = skill_text.splitlines()
    if not skill_text.startswith("---\n") or "name:" not in skill_text[:600] or "description:" not in skill_text[:600]:
        errors.append("SKILL.md frontmatter must contain name and description")
    if len(skill_lines) > 500:
        warnings.append(f"SKILL.md has {len(skill_lines)} lines; keep it below 500")
    details["skill_lines"] = len(skill_lines)

    manifest = load_yaml(ROOT / "manifest.yaml")
    if manifest.get("version") != "0.1.1":
        errors.append("manifest version must be 0.1.1")
    if manifest.get("framework", {}).get("required_version") != "2.0.3":
        errors.append("AgentScope required_version must be exactly 2.0.3")
    details["manifest"] = {
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "status": manifest.get("status"),
    }

    pages_payload = load_yaml(PROFILE_DIR / "page_specs.yaml")
    pages = pages_payload.get("pages", [])
    page_ids = tuple(page.get("id") for page in pages if isinstance(page, dict))
    if page_ids != EXPECTED_PAGE_IDS:
        errors.append(f"page ids/order mismatch: {page_ids}")
    slide_indexes = [page.get("template_slide_index") for page in pages if isinstance(page, dict)]
    if slide_indexes != [0, 1, 2, 3, 4]:
        errors.append(f"template slide indexes must be 0..4: {slide_indexes}")
    for page in pages:
        if not isinstance(page, dict):
            errors.append("page_specs contains a non-object page")
            continue
        missing_page_keys = {
            "id", "title", "data_block", "renderer_handler", "analysis_lens", "required_output"
        } - set(page)
        if missing_page_keys:
            errors.append(f"page {page.get('id')} misses keys: {sorted(missing_page_keys)}")
    details["pages"] = [{"id": page.get("id"), "title": page.get("title")} for page in pages]

    quality = load_yaml(PROFILE_DIR / "quality_rules.yaml")
    output_rule_ids = {
        item.get("id") for item in quality.get("output_gate", []) if isinstance(item, dict)
    }
    missing_rules = EXPECTED_OUTPUT_RULES - output_rule_ids
    if missing_rules:
        errors.append(f"quality rules missing: {sorted(missing_rules)}")
    details["quality_rule_count"] = len(output_rule_ids)

    try:
        details["template"] = validate_zip_asset(
            PROFILE_DIR / "assets" / "monthly_report_template.pptx", "pptx"
        )
        details["demo_dataset"] = validate_zip_asset(
            PROFILE_DIR / "assets" / "demo_monthly_data.xlsx", "xlsx"
        )
    except ValueError as exc:
        errors.append(str(exc))

    compile_errors: list[str] = []
    for path in (ROOT / "payload").rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
        except (OSError, SyntaxError, UnicodeError) as exc:
            compile_errors.append(f"{path.relative_to(ROOT)}: {exc}")
    if compile_errors:
        errors.extend(compile_errors)
    details["compiled_python_files"] = len(list((ROOT / "payload").rglob("*.py")))

    secret_findings = scan_secrets()
    if secret_findings:
        errors.append("possible secrets found in: " + ", ".join(secret_findings))

    return {"ok": not errors, "errors": errors, "warnings": warnings, "details": details}


def main() -> int:
    result = validate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
