"""Evidence-bound delivery metadata for the template-only macro baseline.

File/package validation does not establish current-data or business validity.
Retain the diagnostic artifact without publishing a formal business report.
"""

from __future__ import annotations

import re
import json
import hashlib
from pathlib import Path
from typing import Any


RETAINED_GATES = {"macro_retained_business", "pptx_structure", "powerpoint_render", "macro_layout"}

DRAFT_GATES = {"macro_draft_business", "pptx_structure", "powerpoint_render", "macro_layout"}


def verified_draft_state(state: dict[str, Any], run_id: str) -> bool:
    """Require explicit mode and every independent gate on the same bytes."""
    delivery = state.get("draft_delivery") or {}
    fingerprint = str(delivery.get("artifact_sha256") or "")
    artifact_path = delivery.get("artifact_path")
    bound = {item.get("validator") for item in state.get("artifact_validations", [])
             if item.get("passed") is True and item.get("path") == artifact_path
             and isinstance(item.get("detail"), dict)
             and item["detail"].get("artifact_sha256") == fingerprint}
    return bool(re.fullmatch(r"macro-\d{8}-\d{6}-[a-f0-9]{8}", run_id)
                and state.get("run_id") == run_id
                and state.get("delivery_mode") == "public_draft"
                and state.get("public_draft_confirmed") is True
                and state.get("status") == "draft_ready"
                and state.get("formal_delivery_allowed") is False
                and state.get("draft_delivery_allowed") is True
                and state.get("business_status") == "draft_passed"
                and (state.get("validation") or {}).get("status") == "passed"
                and (state.get("draft_validation") or {}).get("status") == "passed"
                and (state.get("draft_validation") or {}).get("artifact_sha256") == fingerprint
                and re.fullmatch(r"[a-f0-9]{64}", fingerprint)
                and artifact_path
                and delivery.get("url") == f"/api/macro-report/draft/{run_id}"
                and DRAFT_GATES.issubset(bound))


def verified_draft_artifact(state: dict[str, Any], run_root: Path, run_id: str) -> dict[str, Any]:
    """Resolve only a verified draft's own artifact; no public output fallback."""
    if not verified_draft_state(state, run_id):
        raise ValueError("公开数据草稿尚未通过独立草稿、结构与Office验收，下载已阻断。")
    delivery = state["draft_delivery"]
    root = Path(run_root).resolve()
    artifact = (root / str(delivery.get("artifact_path", ""))).resolve()
    ledger = (root / str(delivery.get("ledger_path", ""))).resolve()
    if (root not in artifact.parents or root not in ledger.parents
            or not artifact.is_file() or not ledger.is_file() or artifact.suffix.lower() != ".pptx"):
        raise ValueError("草稿产物或台账不存在，或路径不属于本轮运行。")
    expected = delivery["artifact_sha256"]
    ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
    if (hashlib.sha256(artifact.read_bytes()).hexdigest() != expected
            or hashlib.sha256(ledger.read_bytes()).hexdigest() != delivery.get("ledger_sha256")
            or ledger_data.get("pptx_sha256") != expected
            or ledger_data.get("delivery_mode") != "public_draft"
            or ledger_data.get("formal_delivery_allowed") is not False
            or ledger_data.get("draft_content_complete") is not True):
        raise ValueError("公开数据草稿或台账指纹已变化，下载已阻断。")
    evidence = delivery.get("evidence_sha256") or {}
    if not evidence:
        raise ValueError("公开数据草稿缺少原始来源凭据指纹。")
    for relative, digest in evidence.items():
        try:
            current = macro_evidence_fingerprint(root / relative, root)
        except (ValueError, OSError) as exc:
            raise ValueError("草稿来源凭据路径无效。") from exc
        if not digest or current != digest:
            raise ValueError("草稿来源凭据已变化，不能沿用旧验收下载。")
    return {"success": True, "run_id": run_id, "pptx_url": delivery["url"],
            "sha256": expected, "path": str(artifact), "delivery_mode": "public_draft",
            "formal_delivery_allowed": False}


def macro_evidence_fingerprint(path: Path, run_root: Path) -> str | None:
    """Fingerprint files or an exact source-receipt directory and its list."""
    root = Path(run_root).resolve()
    target = Path(path).resolve()
    target.relative_to(root)
    if target.is_file():
        return hashlib.sha256(target.read_bytes()).hexdigest()
    if not target.is_dir():
        return None
    entries = []
    for item in sorted(target.rglob("*")):
        item.resolve().relative_to(root)
        if item.is_file():
            entries.append([item.relative_to(target).as_posix(), hashlib.sha256(item.read_bytes()).hexdigest()])
    return hashlib.sha256(json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def office_measurement_payload(execution: dict[str, Any]) -> dict[str, Any]:
    """Read the invocation's JSON response, never a saved prior result."""
    stdout = str(execution.get("stdout") or "").strip()
    for candidate in [stdout, *reversed(stdout.splitlines())]:
        try:
            decoded = json.loads(candidate)
            if isinstance(decoded, dict):
                return decoded
        except ValueError:
            continue
    return {}


def verified_office_measurement(execution: dict[str, Any], payload: dict[str, Any],
                                report: dict[str, Any], artifact_sha256: str) -> bool:
    """Bind a successful fresh Office invocation to its full measurement file.

    Layout overflow can fail separately even when Office reopen/render passes.
    A failed subprocess or stale report must never establish an Office pass.
    """
    return bool(
        execution.get("success") is True
        and re.fullmatch(r"[a-f0-9]{64}", artifact_sha256)
        and payload.get("office_passed") is True
        and report.get("office_passed") is True
        and payload.get("artifact_sha256") == artifact_sha256
        and report.get("artifact_sha256") == artifact_sha256
        and payload.get("validated_at")
        and report.get("validated_at") == payload.get("validated_at")
        and all(payload.get(key) == 33 and report.get(key) == 33
                for key in ("slides", "rendered", "roundtrip_slides"))
    )


def formal_download_blocked(filename: str, runtime_root: Path) -> bool:
    """Honor a retrospective business block even for an old cached URL."""
    match = re.match(r"^((?:skill|macro)-\d{8}-\d{6}-[a-f0-9]{8})-", filename)
    if not match:
        return False
    state_path = runtime_root / match.group(1) / "run-state.json"
    if not state_path.is_file():
        return match.group(1).startswith("macro-")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    if match.group(1).startswith("macro-"):
        return state.get("formal_delivery_allowed") is not True or state.get("business_status") != "passed"
    return state.get("formal_delivery_allowed") is False


def baseline_delivery(report_month: str, ledger: dict[str, Any]) -> dict[str, Any]:
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", report_month):
        raise ValueError("宏观基准稿缺少有效报告月份")
    if ledger.get("report_month") != report_month:
        raise ValueError("宏观基准稿月份与台账不一致")
    boundary = str(ledger.get("data_boundary", ""))
    if "模板" not in boundary:
        raise ValueError("模板基准执行器未返回明确的数据边界")
    counts = ledger.get("summary") or {}
    year, month = report_month.split("-")
    answer = (
        f"## {year}年{int(month)}月宏观经济月报：基准稿已生成，业务验收待补齐\n\n"
        f"已生成{counts.get('slides', 0)}页、{counts.get('charts', 0)}个原生图表和"
        f"{counts.get('tables', 0)}个表格，文件结构及PowerPoint打开、渲染检查通过。\n\n"
        "本次只使用模板内嵌历史序列生成基准预测，未检索截至执行日的最新权威数据。"
        "原模板正文与目标月预测的一致性尚未完成验收。目标期新增点不是已发布实际值。\n\n"
        "业务验收未通过，正式导出已阻断，诊断文件保留。仍需补齐权威取数、按季度/分类/季节轴分别更新数据、统一汇总表及逐页结论。"
    )
    quality = {
        "overall_status": "阻断",
        "score": None,
        "scope": "macro_template_baseline",
        "formal_delivery_allowed": False,
        "impact": "文件可打开不代表业务已完成；本次仅为模板历史基准稿，不建议正式使用。",
        "checks": [
            {"name": "文件结构与打开检查", "status": "通过", "evidence": "PPTX结构及PowerPoint打开、逐页渲染检查通过。"},
            {"name": "最新权威数据检索", "status": "待补充", "evidence": "本次执行器仅使用模板内嵌历史序列，没有外部取数证据。"},
            {"name": "预测方法与正文一致性", "status": "待核验", "evidence": "基准预测尚不能证明逐页业务结论已更新且有充分依据。"},
            {"name": "图表口径与汇总表", "status": "阻断", "evidence": "通用月度滚动执行器未区分季度、横截面及季节轴，不能通过业务验收。"},
        ],
    }
    return {"answer": answer, "quality": quality, "business_status": "incomplete", "formal_delivery_allowed": False}


def verified_retained_state(state: dict[str, Any], run_id: str) -> bool:
    """Require explicit mode and every independent gate on the same bytes."""
    delivery = state.get("retained_delivery") or {}
    fingerprint = str(delivery.get("artifact_sha256") or "")
    artifact_path = delivery.get("artifact_path")
    bound = {item.get("validator") for item in state.get("artifact_validations", [])
             if item.get("passed") is True and item.get("path") == artifact_path
             and isinstance(item.get("detail"), dict)
             and item["detail"].get("artifact_sha256") == fingerprint}
    return bool(re.fullmatch(r"macro-\d{8}-\d{6}-[a-f0-9]{8}", run_id)
                and state.get("run_id") == run_id
                and state.get("delivery_mode") == "historical_retained"
                and state.get("history_retention_confirmed") is True
                and state.get("status") in {"partial_completed", "completed", "retained_ready"}
                and state.get("formal_delivery_allowed") is False
                and state.get("retained_delivery_allowed") is True
                and state.get("business_status") == "retained_passed"
                and (state.get("validation") or {}).get("status") == "passed"
                and (state.get("retained_validation") or {}).get("status") == "passed"
                and (state.get("retained_validation") or {}).get("artifact_sha256") == fingerprint
                and re.fullmatch(r"[a-f0-9]{64}", fingerprint)
                and artifact_path
                and delivery.get("url") == f"/api/macro-report/retained/{run_id}"
                and RETAINED_GATES.issubset(bound))


def verified_retained_artifact(state: dict[str, Any], run_root: Path, run_id: str) -> dict[str, Any]:
    """Resolve only a verified retained's own artifact; no public output fallback."""
    if not verified_retained_state(state, run_id):
        raise ValueError("历史延续版尚未通过独立历史延续版、结构与Office验收，下载已阻断。")
    delivery = state["retained_delivery"]
    root = Path(run_root).resolve()
    artifact = (root / str(delivery.get("artifact_path", ""))).resolve()
    ledger = (root / str(delivery.get("ledger_path", ""))).resolve()
    if (root not in artifact.parents or root not in ledger.parents
            or not artifact.is_file() or not ledger.is_file() or artifact.suffix.lower() != ".pptx"):
        raise ValueError("历史延续版产物或台账不存在，或路径不属于本轮运行。")
    expected = delivery["artifact_sha256"]
    ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
    if (hashlib.sha256(artifact.read_bytes()).hexdigest() != expected
            or hashlib.sha256(ledger.read_bytes()).hexdigest() != delivery.get("ledger_sha256")
            or ledger_data.get("pptx_sha256") != expected
            or ledger_data.get("delivery_mode") != "historical_retained"
            or ledger_data.get("formal_delivery_allowed") is not False
            or ledger_data.get("retained_content_complete") is not True):
        raise ValueError("历史延续版或台账指纹已变化，下载已阻断。")
    evidence = delivery.get("evidence_sha256") or {}
    if not evidence:
        raise ValueError("历史延续版缺少原始来源凭据指纹。")
    for relative, digest in evidence.items():
        try:
            current = macro_evidence_fingerprint(root / relative, root)
        except (ValueError, OSError) as exc:
            raise ValueError("历史延续版来源凭据路径无效。") from exc
        if not digest or current != digest:
            raise ValueError("历史延续版来源凭据已变化，不能沿用旧验收下载。")
    return {"success": True, "run_id": run_id, "pptx_url": delivery["url"],
            "sha256": expected, "path": str(artifact), "delivery_mode": "historical_retained",
            "formal_delivery_allowed": False}


