"""AgentScope 2.0.3 多智能体业务协作 Web 服务。

设计依据：
    - doc/乘用车市场战略决策AI智能体.html：系统首页、场景卡片、右侧 Agent 状态面板。
    - doc/市场战略决策智能体开发.html：输入执行区、智能体执行过程、分析结果区。
    - doc/中汽中心AI-UI设计规范.md：深蓝主色、灰白背景、8px 卡片、6px 按钮、4px 输入框。

运行方式：
    python app.py
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse
from uuid import uuid4
import urllib.error
import urllib.request

from dotenv import load_dotenv
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from utils.passenger_forecast_jobs import PassengerForecastJobs
from utils.weekly_report_jobs import WeeklyReportJobs
from utils.weekly_report_research import run_section as run_weekly_section

# Load machine paths before constructing module-level Skill/job objects.
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

HOST = os.getenv("AGENT_SERVER_NAME", "0.0.0.0")
PORT = 7860
INTELLIGENCE_DATA_DIR = Path(__file__).resolve().parent / "assets" / "data"
AGENT_RUN_LOCK = Lock()
LATEST_AGENT_RUN: dict[str, Any] = {}
LATEST_AGENT_RUN_LOCK = Lock()
PROJECT_RUNS_FILE = Path(__file__).resolve().parent / "data" / "project_runs.json"
PROJECT_RUNS_LOCK = Lock()
MONTHLY_JOB_DIR = Path(__file__).resolve().parent / "runtime" / "monthly-report-jobs"
PASSENGER_FORECAST_SKILL_DIR = Path(os.getenv(
    "PASSENGER_FORECAST_SKILL_DIR",
    r"E:/AI/migration-backup/5.4 晓亚\乘用车市场预测-0922\passenger-car-market-forecast",
))
PASSENGER_FORECAST_REFERENCES = (
    "SKILL.md",
    "references/input-contract.md",
    "references/monthly-input.md",
    "references/annual-monthly.md",
    "references/nev-penetration.md",
    "references/output-formats.md",
)


def load_passenger_forecast_skill_prompt() -> str:
    """Load the business-owned forecast Skill without turning its project inputs into defaults."""

    sections: list[str] = []
    for relative in PASSENGER_FORECAST_REFERENCES:
        path = PASSENGER_FORECAST_SKILL_DIR / relative
        if path.is_file():
            sections.append("## " + relative + "\n" + path.read_text(encoding="utf-8"))
    if not sections:
        raise FileNotFoundError("未找到 passenger-car-market-forecast Skill，请检查配置路径。")
    return "以下是本轮必须遵循的业务 Skill：\n\n" + "\n\n".join(sections)


class AgentEventLoopRunner:
    """为 Web 服务维持单一常驻 asyncio 事件循环。

    AgentScope/OpenAIChatModel 内部使用异步 HTTP 客户端。若每个 HTTP 请求都用
    ``asyncio.run(...)`` 新建并关闭事件循环，客户端的异步关闭任务可能落到已关闭
    的循环，从而产生 ``Event loop is closed``。本类让所有 Agent 调用复用同一条
    常驻循环；它只使用 Python 标准库，不依赖 AgentScope 的未稳定底层 API。
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: Thread | None = None
        self._ready = Event()
        self._lock = Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive() and self._loop and not self._loop.is_closed():
                return
            self._ready.clear()
            self._thread = Thread(target=self._run_loop, name="agentscope-web-loop", daemon=True)
            self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("Agent 异步事件循环启动超时。")

    def run(self, coroutine: Any) -> Any:
        self.start()
        loop = self._loop
        if loop is None or loop.is_closed():
            raise RuntimeError("Agent 异步事件循环不可用。")
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result()

    def submit(self, coroutine: Any) -> Any:
        """Schedule coroutine work without blocking the HTTP request thread."""
        self.start()
        loop = self._loop
        if loop is None or loop.is_closed():
            raise RuntimeError("Agent 异步事件循环不可用。")
        return asyncio.run_coroutine_threadsafe(coroutine, loop)

    def stop(self) -> None:
        loop = self._loop
        thread = self._thread
        if not loop or loop.is_closed():
            return
        loop.call_soon_threadsafe(loop.stop)
        if thread and thread.is_alive():
            thread.join(timeout=5)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            from integrations.market_data_api import close_clients
            loop.run_until_complete(close_clients())
            loop.close()


AGENT_LOOP_RUNNER = AgentEventLoopRunner()

# 候选文件当前放在 backup 目录中；未来也可能被复制到项目根目录并命名为 app.py。
# 这里先确定真实项目根目录，再导入 main/tools/utils，避免把 backup 误当成工程根。
APP_FILE = Path(__file__).resolve()
PROJECT_DIR = APP_FILE.parent.parent if APP_FILE.parent.name.lower() == "backup" else APP_FILE.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

MACRO_LEDGER_DIR = PROJECT_DIR / "data" / "macro_monthly"
MACRO_LEDGER_META_FILE = MACRO_LEDGER_DIR / "ledger-status.json"
MACRO_LEDGER_LOCK = Lock()
MAX_MACRO_LEDGER_BYTES = 50 * 1024 * 1024


def load_macro_ledger_status() -> dict[str, Any]:
    """读取唯一当前宏观月报台账的状态。"""
    with MACRO_LEDGER_LOCK:
        if not MACRO_LEDGER_META_FILE.is_file():
            return {"available": False}
        try:
            metadata = json.loads(MACRO_LEDGER_META_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {"available": False}
        stored_name = str(metadata.get("stored_name", ""))
        ledger_path = MACRO_LEDGER_DIR / stored_name
        if not stored_name or not ledger_path.is_file():
            return {"available": False}
        metadata["available"] = True
        metadata["download_url"] = "/api/macro-ledger/download"
        return metadata


def save_macro_ledger(filename: str, data: bytes) -> dict[str, Any]:
    """校验并保存唯一当前台账；替换时将上一版移入历史目录。"""
    safe_name = Path(filename).name.strip()
    suffix = Path(safe_name).suffix.lower()
    if not safe_name or suffix not in {".xlsx", ".xlsm"}:
        raise ValueError("请上传 .xlsx 或 .xlsm 格式的标准台账。")
    if not data.startswith(b"PK"):
        raise ValueError("文件不是有效的 Excel 工作簿。")

    try:
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_vba=suffix == ".xlsm")
        sheets = [
            {
                "name": sheet.title,
                "rows": int(sheet.max_row or 0),
                "columns": int(sheet.max_column or 0),
            }
            for sheet in workbook.worksheets
        ]
        workbook.close()
    except Exception as exc:
        raise ValueError(f"无法读取 Excel 台账：{exc}") from exc
    if not sheets:
        raise ValueError("台账中没有可用工作表。")

    now = datetime.now()
    stored_name = f"current-ledger{suffix}"
    metadata = {
        "available": True,
        "original_name": safe_name,
        "stored_name": stored_name,
        "size_bytes": len(data),
        "uploaded_at": now.isoformat(timespec="seconds"),
        "uploaded_at_label": now.strftime("%Y-%m-%d %H:%M"),
        "sheet_count": len(sheets),
        "data_rows": sum(max(0, item["rows"] - 1) for item in sheets),
        "sheets": sheets,
        "validation_status": "基础校验通过",
        "download_url": "/api/macro-ledger/download",
    }

    with MACRO_LEDGER_LOCK:
        MACRO_LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        if MACRO_LEDGER_META_FILE.is_file():
            try:
                previous = json.loads(MACRO_LEDGER_META_FILE.read_text(encoding="utf-8"))
                previous_path = MACRO_LEDGER_DIR / str(previous.get("stored_name", ""))
                if previous_path.is_file():
                    history_dir = MACRO_LEDGER_DIR / "history"
                    history_dir.mkdir(exist_ok=True)
                    archived_name = f"{now.strftime('%Y%m%d-%H%M%S')}-{Path(str(previous.get('original_name') or previous_path.name)).name}"
                    previous_path.replace(history_dir / archived_name)
            except (OSError, ValueError, TypeError):
                pass
        temp_path = MACRO_LEDGER_DIR / f".{uuid4().hex}.upload"
        temp_path.write_bytes(data)
        temp_path.replace(MACRO_LEDGER_DIR / stored_name)
        temp_meta = MACRO_LEDGER_DIR / f".{uuid4().hex}.json"
        temp_meta.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_meta.replace(MACRO_LEDGER_META_FILE)
    return metadata

from openai import AuthenticationError
from agentscope.message import UserMsg

from main import (
    ENV_PATH,
    build_market_strategy_agent,
    build_user_insight_agent,
    expand_env,
    load_json_config,
    strip_thinking,
)
from skills.market_analysis_skill import MarketAnalysisSkill
from integrations.market_mcp_plugins import load_market_mcp_plugins
from integrations.reputation_live import load_reputation
from integrations.new_car_live import load_new_car
from integrations.policy_live import load_policy_overview
from integrations.rights_live import overview as rights_overview, call_rights, export as rights_export
from skills.market_analysis_skill.runtime import (
    SkillEvent,
    normalize_external_evidence_marker_format,
    normalize_top15_summary_wording,
    strip_internal_evidence_markers,
)
from tools.custom_tools import clear_tool_call_events, get_tool_call_events, record_tool_call
from tools.monthly_report_browser import MONTHLY_REPORT_BROWSER, MonthlyReportBrowserConnector, _page_card_codes, _card_has_current_period
from skill_runtime import SkillRegistry, SkillRunContext, build_skill_runtime_tools
from utils.audio_tagging_engine import DEFAULT_TAG_TAXONOMY, run_audio_tagging_workflow
from utils.html_ppt_builder import build_consulting_html_ppt
from utils.monthly_report_pptx import build_monthly_report_pptx
from utils.monthly_report_narrative import (
    NARRATIVE_RULE_VERSION,
    apply_narratives_to_ppt,
    generate_monthly_narratives,
    validate_narrative_package,
    narrative_markdown,
)
from utils.quality_gate import QUALITY_RULES, evaluate_report_quality
from utils.macro_report_delivery import baseline_delivery, formal_download_blocked
from utils.macro_report_jobs import MacroJobBlocked, MacroReportJobManager


PPT_OUTPUT_DIR = PROJECT_DIR / "outputs" / "ppt"
PASSENGER_MONTHLY_SKILL_DIR = (
    PROJECT_DIR / "skills" / "market-analysis-skill" / "passenger-car-monthly-report"
)
PASSENGER_MONTHLY_TEMPLATE_PATH = (
    PASSENGER_MONTHLY_SKILL_DIR / "assets" / "乘用车月报PPT兼容模板.pptx"
)
PASSENGER_MONTHLY_MAPPING_PATH = (
    PASSENGER_MONTHLY_SKILL_DIR / "assets" / "乘用车月报-数据源映射指标.xlsx"
)
PASSENGER_MONTHLY_EXAMPLES_PATH = (
    PASSENGER_MONTHLY_SKILL_DIR / "assets" / "expert-headline-examples.json"
)
PASSENGER_MONTHLY_PACKAGE_DIR = (PROJECT_DIR / "outputs" / "monthly-report-data").resolve()
# 模板是版式母版；跨月份导出先按本轮BI卡片更新图表和表格。
PASSENGER_MONTHLY_CAPABILITY_ID = "passenger_car_monthly_report"
MACRO_MONTHLY_CAPABILITY_ID = "macro_monthly_report"
MACRO_MONTHLY_SKILL_DIR = PROJECT_DIR / "skills" / "macro-monthly-report"
SKILL_RUNTIME_ROOT = PROJECT_DIR / "runtime" / "skill-runs"
SKILL_REGISTRY = SkillRegistry([PROJECT_DIR / "skills"])
MCP_PLUGIN_BY_CAPABILITY = {
    "policy": "policy",
    "rights": "rights",
    "newcar": "new-car",
    "reputation": "reputation",
}
ZHIPU_ENV_PATH = PROJECT_DIR / ".env.zhipu"
HTML_REPORT_SKILL_RUNNER = (
    Path.home()
    / ".openclaw"
    / "workspace-report-agent"
    / "skills"
    / "html-report-generator"
    / "executors"
    / "run.py"
)


def resolve_analysis_type(requested: str, capabilities: list[str]) -> str:
    """Make the selected capability list authoritative for special routing."""

    normalized = {str(item).strip() for item in capabilities if str(item).strip()}
    monthly_selected = PASSENGER_MONTHLY_CAPABILITY_ID in normalized
    macro_selected = MACRO_MONTHLY_CAPABILITY_ID in normalized
    if monthly_selected and macro_selected:
        raise ValueError("“乘用车月报智能生成”和“宏观经济月报”不能在同一任务中同时执行。")
    if requested == PASSENGER_MONTHLY_CAPABILITY_ID and not monthly_selected:
        raise ValueError("未选择“乘用车月报智能生成”，不能调用月报专用数据源与PPT链路。")
    if requested == MACRO_MONTHLY_CAPABILITY_ID and not macro_selected:
        raise ValueError("未选择“宏观经济月报”，不能调用宏观月报专用链路。")
    if monthly_selected:
        return PASSENGER_MONTHLY_CAPABILITY_ID
    if macro_selected:
        return MACRO_MONTHLY_CAPABILITY_ID
    return requested


def activate_skill_runtime(skill_id: str) -> tuple[SkillRunContext, str, list[Any]]:
    """Mount a complete Skill package and expose its generic runtime tools."""

    package = SKILL_REGISTRY.get(skill_id)
    context = SkillRunContext(package, SKILL_RUNTIME_ROOT)
    instruction = package.runtime_prompt(context.run_id)
    if skill_id == "macro-monthly-report":
        instruction += """

# 宏观月报运行时执行约束

先读取 references/source-queries.json。取数阶段只使用其中列出的
agent_reach_search 查询模板，每条最多调用一次；不要调用 any_search，也不要围绕
单条来源循环重试。完成取数后立即把来源、指标、实际/预测标记写入
working/ledger.json。随后分两步执行：先用 presentation_replace_text 更新文案，再
用 presentation_update_chart 更新已明确映射的原生图表。若 Skill 包中的
scripts/apply_ledger_updates.py 能补齐台账里的 old/new 文本映射，调用
skill_run_script 执行它。最后必须调用 presentation_validate、
presentation_powerpoint_validate 和 skill_validate_run。

每完成一个任务节点立刻调用 skill_update_task；缺失的数据要按 Skill 的预测规则
标注，不得为了继续流程编造来源。不要在最终回答中复述操作计划，工具完成前继续执行。
"""
    tools = build_skill_runtime_tools(context)
    return context, instruction, tools


def load_macro_monthly_skill_prompt() -> str:
    """Compatibility helper used by lightweight tests and diagnostics.

    Production execution uses :func:`activate_skill_runtime` so the model gets
    the entire package and package-aware tools, not a Markdown-only prompt.
    """

    if retained and payload.get("history_retention_confirmed") is not True:
        raise MacroJobBlocked("历史延续版需要显式确认历史图表与本期未更新标注。")
    package = SKILL_REGISTRY.get("macro-monthly-report")
    return package.runtime_prompt("diagnostic")


def _macro_report_month(question: str) -> str:
    """Extract the only required business input for the macro monthly Skill."""

    matched = re.search(r"(20\d{2})\s*(?:年|[-/.])\s*(0?[1-9]|1[0-2])\s*(?:月)?", question)
    if matched:
        return f"{matched.group(1)}-{int(matched.group(2)):02d}"
    now = datetime.now()
    return f"{now.year}-{now.month:02d}"


def _skill_chunk_json(chunk: Any) -> dict[str, Any]:
    content = getattr(chunk, "content", [])
    text = getattr(content[0], "text", "") if content else ""
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Skill 工具未返回对象结果。")
    return payload


async def run_macro_monthly_skill(
    question: str,
    config: dict[str, Any],
    *,
    run_id: str | None = None,
    jobs: MacroReportJobManager | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the typed package pipeline, never the template-only baseline.

    A failed source/update gate retains the source receipts and its original
    run id. Structural validity alone is deliberately insufficient to publish.
    """
    import importlib.util
    from dataclasses import replace
    from utils.macro_report_delivery import macro_evidence_fingerprint

    payload = payload or {}
    delivery_mode = str(payload.get("delivery_mode") or "formal")
    public_draft = delivery_mode == "public_draft"
    retained = delivery_mode == "historical_retained"
    if delivery_mode not in {"formal", "public_draft", "historical_retained"} or (public_draft and payload.get("public_draft_confirmed") is not True):
        raise MacroJobBlocked("公开数据草稿需要用户显式确认，不会自动降低正式月报门禁。")
    package = SKILL_REGISTRY.get("macro-monthly-report")
    if public_draft or retained:
        # The package is immutable: retain all runtime validators, replacing
        # only the independently different draft-content gate for this run.
        package = replace(package, policy={**package.policy, "required_artifact_validators": [
            ("macro_retained_business" if retained else "macro_draft_business") if name == "macro_business" else name
            for name in package.policy.get("required_artifact_validators", [])]})
    context = SkillRunContext(package, SKILL_RUNTIME_ROOT, run_id=run_id)
    original_state = context.load_state()
    if original_state.get("package_hash") != package.package_hash:
        raise MacroJobBlocked("Skill 包已升级；原运行仍保留原版本证据，请启动新任务，不混用检查点。")
    if original_state.get("delivery_mode") is not None and original_state["delivery_mode"] != delivery_mode:
        raise MacroJobBlocked("恢复运行的交付模式不同，请启动独立任务，不能混用正式版与草稿检查点。")
    tools = build_skill_runtime_tools(context)
    tool_map = {tool.name: tool for tool in tools}
    report_month = str(payload.get("report_month") or _macro_report_month(question))
    cutoff_date = str(payload.get("cutoff_date") or datetime.now().date().isoformat())
    mode = str(payload.get("mode") or "forecast").replace("historical-update", "historical_update")
    historical = mode == "historical_update"
    if mode not in {"forecast", "historical_update"} or payload.get("slides") or (historical and public_draft) or (retained and not historical):
        raise MacroJobBlocked("执行器支持完整预测或历史更新；历史更新不能混用公开草稿检查点。")
    report_year, report_month_number = report_month.split("-")
    output_name = f"{report_year}年{int(report_month_number)}月宏观经济分析报告{'_公开数据草稿' if public_draft else ''}.pptx"
    output_path = f"outputs/{output_name}"
    ledger_path = "working/macro-ledger.json"
    contract_path = "working/template-contract.json"
    source_path = "working/data-package.json"
    source_receipts_path = "working/macro-sources/pages"
    request = {"question": question, "report_month": report_month, "cutoff_date": cutoff_date, "mode": mode}
    if public_draft:
        request.update(delivery_mode=delivery_mode, public_draft_confirmed=True)
    if retained:
        request.update(delivery_mode=delivery_mode, history_retention_confirmed=True)
    request_file = context.inputs_dir / "request.json"
    if request_file.exists() and json.loads(request_file.read_text(encoding="utf-8")) != request:
        raise MacroJobBlocked("恢复请求与原运行的月份、截止日或模式不同，请启动新任务。")
    request_file.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    original_state.update(delivery_mode=delivery_mode, public_draft_confirmed=public_draft,
                          formal_delivery_allowed=False, draft_delivery_allowed=False,
                          retained_delivery_allowed=False, history_retention_confirmed=retained)
    context.save_state(original_state)
    resuming_missing = retained and payload.get("resume_missing_pages") is True
    if resuming_missing:
        state=context.load_state()
        for stage in list(state.get("stage_fingerprints", {})):
            if stage != "inventory":state["stage_fingerprints"].pop(stage, None)
        state["artifact_validations"]=[]
        context.save_state(state)
    stages = [
        ("inventory", "盘点33页模板及类型化数据契约"),
        ("sources", "检索并验证最新权威实际数据"),
        ("normalize", "按口径和频率标准化数据"),
        *([("forecast", "按序列生成可解释预测")] if not public_draft else []),
        ("chart_update", "同步更新图表与汇总表"),
        ("narrative", "从最终数据更新逐页结论"),
        ("business_gate", "独立验收公开事实、口径与缺口标注" if public_draft else "独立验收来源、口径、预测与文案"),
        ("structure_gate", "验证可编辑PPTX结构"),
        ("office_gate", "Microsoft PowerPoint逐页渲染验收"),
        ("layout_gate", "检查实际文字边界及正文图表交叠"),
        ("finalize", "草稿总验收并发布同一run_id产物" if public_draft else "总验收并发布同一run_id产物"),
    ]
    if not original_state.get("plan"):
        context.set_plan([{"id": name, "title": title, "success_criteria": title + "并保留证据",
                           "depends_on": [stages[index - 1][0]] if index else []}
                          for index, (name, title) in enumerate(stages)])

    def emit(phase: str, message: str, progress: int) -> None:
        if jobs:
            jobs.check_cancelled(context.run_id)
            jobs.update(context.run_id, phase, message, progress)
        context.checkpoint(message, {"phase": phase, "progress": progress})

    def save_json(relative: str, value: dict[str, Any]) -> None:
        target = context.workspace_path(relative)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)

    def completed(stage: str, message: str, evidence: list[str]) -> None:
        context.update_task(stage, "completed", message, evidence)
        fingerprints = {}
        for relative in evidence:
            try:
                file = context.workspace_path(relative)
                fingerprint = macro_evidence_fingerprint(file, context.root)
                if fingerprint is not None:
                    fingerprints[relative] = fingerprint
            except Exception:
                continue
        state = context.load_state()
        state.setdefault("stage_fingerprints", {})[stage] = fingerprints
        context.save_state(state)
        if jobs:
            jobs.checkpoint(context.run_id, stage, {"evidence": evidence, "sha256": fingerprints})

    def reusable(stage: str, *paths: str) -> bool:
        state = context.load_state()
        task = next((item for item in state.get("plan", []) if item.get("id") == stage), {})
        fingerprints = state.get("stage_fingerprints", {}).get(stage, {})
        return task.get("status") == "completed" and all(
            fingerprints.get(path) is not None
            and fingerprints.get(path) == macro_evidence_fingerprint(context.workspace_path(path), context.root)
            for path in paths)

    def result(answer: str, passed: bool, issues: list[Any] | None = None, delivery_url: str = "") -> dict[str, Any]:
        formal_passed = passed and not public_draft and not retained
        checks = [{"name": "业务内容验收", "status": "通过" if passed else "阻断",
                   "evidence": "已验证权威来源、逐页口径及文案" if passed else "；".join(str(item.get("message", item)) if isinstance(item, dict) else str(item) for item in (issues or []))}]
        return {"answer": answer, "agent": "market_strategy", "model_provider": config.get("active_provider", ""),
                "run_id": context.run_id, "delivery_mode": delivery_mode,
                "report_completion": context.load_state().get("report_completion"),
                "pending_pages": context.load_state().get("pending_pages", []),
                "business_status": ("retained_passed" if retained else "draft_passed" if public_draft else "passed") if passed else "incomplete",
                "formal_delivery_allowed": formal_passed,
                "retained_delivery_allowed": retained and passed,
                "retained_delivery_url": delivery_url if retained and passed else "",
                "draft_delivery_allowed": public_draft and passed,
                "draft_delivery_url": delivery_url if public_draft and passed else "",
                "tool_events": get_tool_call_events(),
                "quality": {"overall_status": ("草稿验收通过" if public_draft else "通过") if passed else "阻断", "score": None,
                            "formal_delivery_allowed": formal_passed, "delivery_mode": delivery_mode, "checks": checks},
                "skill": {"active": True, "name": "macro-monthly-report", "display_name": "宏观经济月报",
                          "analysis_type": "macro_monthly_report", "output_gate": ("草稿验收通过" if public_draft else "通过") if passed else "业务验收阻断"},
                "skill_run": {"run_id": context.run_id, "workspace": str(context.root), "state": context.load_state(),
                              "delivery_mode": delivery_mode, "delivery_url": delivery_url,
                              "formal_delivery_allowed": formal_passed}}

    def block(message: str, issues: list[Any], phase: str) -> None:
        context.update_task(phase, "blocked", message, [source_path, ledger_path])
        state = context.load_state()
        state.update(status="needs_repair", business_status="incomplete", formal_delivery_allowed=False)
        context.save_state(state)
        detail = "\n".join(f"- {item.get('request_id', '')} {item.get('message', item)}" if isinstance(item, dict) else f"- {item}" for item in issues)
        answer = f"## {report_year}年{int(report_month_number)}月宏观经济月报未通过验收\n\n{message}\n\n{detail}\n\n已保留来源和检查点；不会沿用模板旧文案或发布未经验证的PPT。"
        raise MacroJobBlocked(message, issues=issues, result=result(answer, False, issues))

    async def script(relative: str, arguments: list[str], timeout: int = 180) -> dict[str, Any]:
        # The package script tool contains a bounded synchronous subprocess.
        # Keep it off the shared AgentScope loop (passenger jobs may use it).
        execution = _skill_chunk_json(await asyncio.to_thread(
            lambda: asyncio.run(tool_map["skill_run_script"].call(relative, json.dumps(arguments, ensure_ascii=False), timeout))))
        save_json("working/" + Path(relative).stem + "-execution.json", execution)
        if jobs:
            jobs.check_cancelled(context.run_id)
        return execution

    try:
        emit("inventory", "正在读取全部模板、映射与类型化数据契约。", 5)
        if not reusable("inventory", contract_path):
            context.update_task("inventory", "running")
            execution = await script("scripts/macro_history.py" if historical else "scripts/inspect_macro_template.py", [contract_path], 90)
            if not execution.get("success"):
                block("模板契约盘点失败。", [{"message": execution.get("stderr") or execution.get("stdout")}], "inventory")
            completed("inventory", "全部页、图表和来源请求已盘点。", [contract_path])
        contract = json.loads(context.workspace_path(contract_path, must_exist=True).read_text(encoding="utf-8"))
        requests = contract.get("source_requests") or contract.get("requests")
        if not requests:
            block("模板契约缺少真实来源请求，不能沿用基准稿执行器。", [{"message": "inventory.source_requests 为空"}], "inventory")
        if historical:
            # Archived quarters are unchanged, never turned into monthly GDP.
            # Reviewed cumulative-flow derivations share original PBC documents
            # with M1/M2; do not repeatedly ask a locator for unpublished monthly prose.
            derived_ids = {"s24-shape9::current", *(f"s24-shape17::category{i}" for i in range(5))}
            requests = [r for r in requests if r["frequency"] != "quarterly" and r["id"] not in derived_ids]
            outlook_charts = {"s13-shape17", "s14-shape15", "s15-shape9", "s19-shape13", "s21-shape11", "s22-shape9", "s24-shape9"}
            requests = [{**r, "history_count": 3 if r["chart_id"] in outlook_charts or r["chart_id"] == "s26-shape11" else 1} for r in requests]
            history = json.loads(context.workspace_path("working/history.json", must_exist=True).read_text(encoding="utf-8"))
            emit("inventory", f"新版36图语义映射完成；复用{len(history['observations'])}个历史点，{len(history['conflicts'])}处差异单独核验。", 10)

        emit("sources", "正在按指标口径检索最新权威来源，逐条保存引用与实际值。", 12)
        if not reusable("sources", source_path, source_receipts_path):
            context.update_task("sources", "running")
            source_file = package.resolve("scripts/macro_sources.py")
            module_name = f"macro_sources_{context.run_id.replace('-', '_')}"
            specification = importlib.util.spec_from_file_location(module_name, source_file)
            if specification is None or specification.loader is None:
                raise RuntimeError("宏观来源模块不可加载。")
            module = importlib.util.module_from_spec(specification)
            sys.modules[module_name] = module
            specification.loader.exec_module(module)

            def source_progress(message: str, percent: int) -> None:
                emit("sources", message, 12 + min(100, max(0, percent)) * 28 // 100)

            previous=json.loads(context.workspace_path(source_path).read_text(encoding="utf-8")) if resuming_missing and context.workspace_path(source_path).exists() else None
            if resuming_missing:
                old_ledger=json.loads(context.workspace_path(ledger_path).read_text(encoding="utf-8"))
                pending=set(old_ledger.get("retained_requests", []))
                pending_requests=[r for r in requests if r["id"] in pending]
                emit("sources", f"仅补采{len(old_ledger.get('pending_pages', []))}个未更新页的{len(pending_requests)}项；其余已取证数据复用。", 12)
                if pending_requests:
                    fresh=await module.collect_sources(report_month,cutoff_date,pending_requests,context.root,model_config=config,progress=source_progress,reuse_root=SKILL_RUNTIME_ROOT)
                    evidence=previous.get("evidence_observations",previous.get("observations",[]))+fresh.get("evidence_observations",fresh.get("observations",[]))
                    unique={json.dumps(o,ensure_ascii=False,sort_keys=True):o for o in evidence}
                    source_data={**fresh,"evidence_observations":list(unique.values()),"observations":list(unique.values()),"resume_scope":{"request_ids":sorted(pending),"pages":old_ledger.get("pending_pages",[])}}
                else:source_data=previous
            elif retained:
                try:source_data=await module.collect_retained_sources(report_month,cutoff_date,requests,context.root,reuse_root=SKILL_RUNTIME_ROOT)
                except ValueError as exc:
                    if "仍需要本期已核验" not in str(exc):raise
                    source_data=await module.collect_sources(report_month,cutoff_date,requests,context.root,model_config=config,progress=source_progress,reuse_root=SKILL_RUNTIME_ROOT)
            else:
                source_data=await module.collect_sources(report_month,cutoff_date,requests,context.root,model_config=config,progress=source_progress,reuse_root=SKILL_RUNTIME_ROOT,**({"public_draft":True} if public_draft else {}))
            source_data.update(report_month=report_month, cutoff_date=cutoff_date, mode=mode, delivery_mode=delivery_mode)
            if retained:
                pages={}
                for path in context.workspace_path(source_receipts_path).glob("*.json"):
                    page=json.loads(path.read_text(encoding="utf-8"));pages[page["receipt_id"]]=page
                checked=module.verify_source_corroboration(source_data,contract,pages)
                bad={i.get("request_id") for i in checked.get("issues",[])}
                source_data["rejected_evidence"]=checked.get("issues",[])
                source_data["evidence_observations"]=[o for o in source_data.get("evidence_observations",source_data.get("observations",[])) if o.get("request_id") not in bad]
                source_data["observations"]=[o for o in checked["observations"] if o.get("request_id") not in bad]
            save_json(source_path, source_data)
            record_tool_call("macro_authoritative_sources", "success" if source_data.get("status") == "ready" else "blocked",
                             f"run_id={context.run_id}; verified={source_data.get('coverage', {}).get('verified', 0)}/{len(requests)}; cutoff={cutoff_date}")
            if jobs:
                jobs.checkpoint(context.run_id, "sources", {"data_package": source_path, "status": source_data.get("status")}, completed=source_data.get("status") == "ready")
            if ((public_draft and int(source_data.get("coverage", {}).get("verified", 0)) <= 0)
                    or (not public_draft and not historical and source_data.get("status") != "ready")):
                block("权威实际数据尚未完整获取，已保留可复用来源；不能以模板旧值补齐。",
                      source_data.get("issues") or [{"message": "来源包未达到 ready 状态"}], "sources")
            completed("sources", "已保存已验证公开数据与明确缺口。" if public_draft else "来源引用与已发布实际值已验证并保存。", [source_path, source_receipts_path])
        source_data = json.loads(context.workspace_path(source_path, must_exist=True).read_text(encoding="utf-8"))
        if ((public_draft and int(source_data.get("coverage", {}).get("verified", 0)) <= 0)
                or (not public_draft and not historical and source_data.get("status") != "ready")):
            block("恢复的来源包尚未通过验收。", source_data.get("issues") or [{"message": "来源包未就绪"}], "sources")

        emit("typed_update", "正在按可核验公开事实生成草稿，清空未取证旧值并标注缺口；不生成预测。" if public_draft else "正在执行类型化标准化、预测、图表/汇总表和逐页文案同步更新。", 44)
        if not reusable("narrative", ledger_path, output_path, source_path, source_receipts_path):
            context.update_task("normalize", "running")
            build_script = "scripts/build_macro_historical.py" if historical else "scripts/build_macro_draft.py" if public_draft else "scripts/build_macro_report.py"
            execution = await script(build_script, [report_month, source_path, output_path, ledger_path], 240)
            if not execution.get("success"):
                failure_ledger = context.workspace_path(ledger_path)
                issues = json.loads(failure_ledger.read_text(encoding="utf-8")).get("issues", []) if failure_ledger.exists() else []
                block("类型化月报更新未通过，已保留数据包及执行详情。", issues or [{"message": execution.get("stderr") or execution.get("stdout")}], "normalize")
            for stage in (("normalize", "chart_update", "narrative") if public_draft else ("normalize", "forecast", "chart_update", "narrative")):
                completed(stage, "类型化执行器已完成该步骤，结果待独立业务验收。", [ledger_path, output_path, source_path, source_receipts_path])
        presentation = context.workspace_path(output_path, must_exist=True)
        context.register_artifact(presentation, "presentation")

        emit("business_gate", "正在逐页校验已取证事实、未取证旧值清除、缺口标注和草稿边界。" if public_draft else "正在逐页校验真实来源、频率/单位、预测边界、汇总表和主旨句。", 70)
        if not reusable("business_gate", "working/business-validation.json", output_path, ledger_path, source_path, source_receipts_path):
            context.update_task("business_gate", "running")
            validator_script = "scripts/validate_macro_historical.py" if historical else "scripts/validate_macro_draft.py" if public_draft else "scripts/validate_macro_report.py"
            execution = await script(validator_script, [output_path, ledger_path], 120)
            output_lines = str(execution.get("stdout") or "").strip().splitlines()
            business = {}
            # Accept both pretty JSON and a final JSON line after real progress
            # events. Never convert a non-JSON success string into a pass.
            for line in [str(execution.get("stdout") or "").strip(), *reversed(output_lines)]:
                try:
                    candidate = json.loads(line)
                    if isinstance(candidate, dict):
                        business = candidate
                        break
                except ValueError:
                    continue
            save_json("working/business-validation.json", business)
            if public_draft and business.get("artifact_sha256", business.get("pptx_sha256")) != hashlib.sha256(presentation.read_bytes()).hexdigest():
                block("草稿业务验收未绑定当前PPT文件指纹。", [{"code": "draft_business_hash_mismatch"}], "business_gate")
            if public_draft:
                business["artifact_sha256"] = business.get("artifact_sha256", business.get("pptx_sha256"))
            context.record_artifact_validation(presentation, "macro_retained_business" if retained else "macro_draft_business" if public_draft else "macro_business", bool(business.get("passed")), business)
            if not execution.get("success") or not business.get("passed"):
                block("宏观月报独立业务验收未通过。", business.get("issues") or business.get("errors") or [{"message": execution.get("stderr") or execution.get("stdout")}], "business_gate")
            completed("business_gate", "权威来源、类型化图表、汇总表及逐页文案一致性通过。", ["working/business-validation.json", output_path, ledger_path, source_path, source_receipts_path])

        emit("structure_gate", "正在验证PPTX包完整性、原生可编辑图表及外部依赖。", 82)
        if not reusable("structure_gate", "working/structure-validation.json", output_path):
            context.update_task("structure_gate", "running")
            structure = _skill_chunk_json(await asyncio.to_thread(lambda: asyncio.run(
                tool_map["presentation_validate"].call(output_path, int(contract.get("slide_count", 33)), int(contract.get("chart_count", 37))))))
            save_json("working/structure-validation.json", structure)
            if not structure.get("passed"):
                block("PPTX结构验收未通过。", [{"message": structure}], "structure_gate")
            if public_draft or retained:
                context.record_artifact_validation(presentation, "pptx_structure", True,
                    {**structure, "artifact_sha256": hashlib.sha256(presentation.read_bytes()).hexdigest()})
            completed("structure_gate", "原生PPTX结构、页数与图表通过。", ["working/structure-validation.json", output_path])

        emit("office_gate", "正在Microsoft PowerPoint实机打开并逐页渲染，检查文件可用性。", 89)
        fresh_layout = None
        if not reusable("office_gate", "working/office-validation.json", output_path):
            context.update_task("office_gate", "running")
            active_office = await asyncio.to_thread(lambda: subprocess.run(
                ["tasklist.exe", "/FI", "IMAGENAME eq POWERPNT.EXE", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, errors="replace", timeout=10, check=False))
            if active_office.returncode != 0 or "POWERPNT.EXE" in active_office.stdout.upper():
                block("PowerPoint正被使用或无法确认独立验收环境；已保留产物，请关闭PowerPoint后从检查点恢复。",
                      [{"code": "office_busy", "message": "不会关闭用户已打开的PowerPoint演示文稿。"}], "office_gate")
            # Macro-specific validation owns only its own Office documents and
            # saves/reopens a diagnostic copy without changing the deliverable.
            execution = await script("scripts/validate_macro_layout.py", [output_path, "working/macro-layout-validation.json", ledger_path], 240)
            from utils.macro_report_delivery import office_measurement_payload, verified_office_measurement
            office_payload = office_measurement_payload(execution)
            layout_file = context.workspace_path("working/macro-layout-validation.json")
            fresh_layout = json.loads(layout_file.read_text(encoding="utf-8")) if layout_file.is_file() else {}
            office_passed = verified_office_measurement(
                execution, office_payload, fresh_layout,
                hashlib.sha256(presentation.read_bytes()).hexdigest())
            office = {"passed": office_passed, "slides": office_payload.get("slides"),
                      "rendered": office_payload.get("rendered"), "roundtrip_slides": office_payload.get("roundtrip_slides"),
                      "artifact_sha256": office_payload.get("artifact_sha256"), "render_dir": "working/macro-layout/rendered",
                      "issues": office_payload.get("issues", [])}
            save_json("working/office-validation.json", office)
            context.record_artifact_validation(presentation, "powerpoint_render", office_passed, office)
            if not office.get("passed"):
                block("Microsoft PowerPoint打开与渲染验收未通过。", [{"message": office}], "office_gate")
            completed("office_gate", "Microsoft PowerPoint逐页渲染通过。", ["working/office-validation.json", output_path, str(office.get("render_dir", ""))])

        emit("layout_gate", "正在测量最终PPT的真实文字边界，检查正文溢出和图表交叠。", 94)
        if not reusable("layout_gate", "working/macro-layout-validation.json", output_path, ledger_path):
            context.update_task("layout_gate", "running")
            if fresh_layout is None:
                execution = await script("scripts/validate_macro_layout.py", [output_path, "working/macro-layout-validation.json", ledger_path], 240)
                layout_file = context.workspace_path("working/macro-layout-validation.json")
                layout = json.loads(layout_file.read_text(encoding="utf-8")) if layout_file.is_file() else {}
                from utils.macro_report_delivery import office_measurement_payload, verified_office_measurement
                invocation_completed = verified_office_measurement(
                    execution, office_measurement_payload(execution), layout,
                    hashlib.sha256(presentation.read_bytes()).hexdigest())
            else:
                layout = fresh_layout
                invocation_completed = execution.get("success") is True
            layout_passed = (invocation_completed and layout.get("passed") is True and layout.get("office_passed") is True
                             and layout.get("artifact_sha256") == hashlib.sha256(presentation.read_bytes()).hexdigest())
            context.record_artifact_validation(presentation, "macro_layout", layout_passed, layout)
            if not layout_passed:
                block("宏观月报实际版式验收未通过；已保留产物与逐页问题清单。",
                      layout.get("issues") or [{"message": execution.get("stderr") or execution.get("stdout")}], "layout_gate")
            completed("layout_gate", "正文实际边界、表格及图表交叠检查通过。", ["working/macro-layout-validation.json", output_path, ledger_path])

        emit("finalize", "业务与文件验收完成，正在总验收并登记同一run_id交付物。", 97)
        if not reusable("business_gate", "working/business-validation.json", output_path, ledger_path, source_path, source_receipts_path):
            block("业务验收后来源凭据或产物已变化，请从检查点重新验收。",
                  [{"code": "business_evidence_changed", "message": "不复用被改动或缺失的原始来源凭据。"}], "business_gate")
        completed("finalize", "准备执行独立总验收。", [output_path, ledger_path, source_path])
        validation = context.validate([output_path, ledger_path, source_path])
        if validation.get("status") != "passed":
            block("完整Skill运行总验收未通过。", [{"message": validation}], "finalize")
        ledger = json.loads(context.workspace_path(ledger_path, must_exist=True).read_text(encoding="utf-8"))
        original_sha256 = hashlib.sha256(presentation.read_bytes()).hexdigest()
        if original_sha256 != ledger.get("pptx_sha256"):
            block("验收文件内容已变化，不能发布；请从检查点重新验收。",
                  [{"code": "artifact_changed_after_validation", "message": "PPT内容与独立业务台账指纹不一致"}], "finalize")
        if public_draft:
            if (ledger.get("delivery_mode") != "public_draft" or ledger.get("formal_delivery_allowed") is not False
                    or ledger.get("draft_content_complete") is not True):
                block("草稿台账缺少独立数据边界证明，不能发布。", [{"code": "draft_boundary_missing"}], "finalize")
            delivery_url = f"/api/macro-report/draft/{context.run_id}"
            state = context.load_state()
            state.update(status="draft_ready", business_status="draft_passed", formal_delivery_allowed=False,
                         draft_delivery_allowed=True, delivery_mode="public_draft", public_draft_confirmed=True,
                         draft_validation={"status": "passed", "artifact_sha256": original_sha256},
                         draft_delivery={"artifact_path": output_path, "artifact_sha256": original_sha256,
                            "ledger_path": ledger_path,
                            "ledger_sha256": hashlib.sha256(context.workspace_path(ledger_path).read_bytes()).hexdigest(),
                            "evidence_sha256": {relative: macro_evidence_fingerprint(context.workspace_path(relative), context.root)
                                                 for relative in (source_path, source_receipts_path, "inputs/request.json")},
                            "url": delivery_url})
            context.save_state(state)
            from utils.macro_report_delivery import verified_draft_artifact
            verified_draft_artifact(state, context.root, context.run_id)
            context.checkpoint("公开数据草稿独立验收通过；不是正式完整月报", {"delivery_url": delivery_url, "sha256": original_sha256})
            coverage = source_data.get("coverage", {})
            answer = (f"## {report_year}年{int(report_month_number)}月宏观经济月报公开数据草稿已生成\n\n"
                      f"信息截止日：{cutoff_date}。已读取 {coverage.get('verified', 0)}/{len(requests)} 项可核验公开指标；"
                      "保留33页原生可编辑图表和表格，未取证指标明确留空并标注缺口，没有沿用模板旧值，也没有生成预测。"
                      "草稿已通过独立真实性、结构、Microsoft PowerPoint打开渲染及版式验收，可下载查看；不是正式完整月报。")
            return result(answer, True, delivery_url=delivery_url)
        if retained:
            if (ledger.get("delivery_mode") != "historical_retained" or ledger.get("formal_delivery_allowed") is not False
                    or ledger.get("retained_content_complete") is not True):
                block("历史延续版台账缺少独立数据边界证明，不能发布。", [{"code": "retained_boundary_missing"}], "finalize")
            delivery_url = f"/api/macro-report/retained/{context.run_id}"
            state = context.load_state()
            state.update(status="partial_completed" if ledger.get("pending_pages") else "completed",
                         report_completion="partial_completed" if ledger.get("pending_pages") else "completed",
                         pending_pages=ledger.get("pending_pages",[]), business_status="retained_passed", formal_delivery_allowed=False,
                         retained_delivery_allowed=True, delivery_mode="historical_retained", history_retention_confirmed=True,
                         retained_validation={"status": "passed", "artifact_sha256": original_sha256},
                         retained_delivery={"artifact_path": output_path, "artifact_sha256": original_sha256,
                            "ledger_path": ledger_path,
                            "ledger_sha256": hashlib.sha256(context.workspace_path(ledger_path).read_bytes()).hexdigest(),
                            "evidence_sha256": {relative: macro_evidence_fingerprint(context.workspace_path(relative), context.root)
                                                 for relative in (source_path, source_receipts_path, "inputs/request.json")},
                            "url": delivery_url})
            context.save_state(state)
            from utils.macro_report_delivery import verified_retained_artifact
            verified_retained_artifact(state, context.root, context.run_id)
            context.checkpoint("历史延续版独立验收通过；不是正式完整月报", {"delivery_url": delivery_url, "sha256": original_sha256})
            coverage = ledger.get("coverage", {})
            answer = (f"{report_year}年{int(report_month_number)}月宏观经济分析报告：{'部分完成' if ledger.get('pending_pages') else '完成'}。信息截止{cutoff_date}。"
                      f"本期已核验{coverage.get('verified',0)}/{coverage.get('required',0)}项；"
                      f"{len(ledger.get('pending_pages',[]))}个未更新页保留模板数据，标注暂无可核验数据及历史日期。继续任务仅补采这些页。"
                      "33页原生可编辑图表与表格已通过独立事实、结构、PowerPoint渲染和版式验收。")
            return result(answer, True, delivery_url=delivery_url)
        PPT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        published = PPT_OUTPUT_DIR / f"{context.run_id}-{safe_filename(presentation.stem)}.pptx"
        shutil.copy2(presentation, published)
        published_sha256 = hashlib.sha256(published.read_bytes()).hexdigest()
        if published_sha256 != original_sha256:
            block("发布副本与验收产物内容不一致，正式发布阻断。",
                  [{"code": "published_artifact_hash_mismatch", "message": "发布副本内容指纹不匹配"}], "finalize")
        delivery_url = "/outputs/ppt/" + quote(published.name)
        state = context.load_state()
        state.update(business_status="passed", formal_delivery_allowed=True,
                     delivery={"artifact_path": output_path, "artifact_sha256": original_sha256,
                               "ledger_path": ledger_path,
                               "ledger_sha256": hashlib.sha256(context.workspace_path(ledger_path).read_bytes()).hexdigest(),
                               "published_filename": published.name, "published_sha256": published_sha256,
                               "url": delivery_url})
        context.save_state(state)
        context.checkpoint("已发布通过业务与Office验收的PPT", {"delivery_url": delivery_url, "sha256": published_sha256})
        answer = (f"## {report_year}年{int(report_month_number)}月宏观经济月报已完成\n\n"
                  f"信息截止日：{cutoff_date}；模式：{'预测版' if mode == 'forecast' else '历史更新'}。"
                  "已完成权威实际数据取证、类型化预测、图表和汇总表更新、逐页文案与独立业务验收。"
                  "文件通过PPTX结构、Microsoft PowerPoint打开、逐页渲染及实际文字边界检查；实际值与预测值在报告中分别标注。")
        return result(answer, True, delivery_url=delivery_url)
    except Exception as exc:
        if not isinstance(exc, MacroJobBlocked):
            state = context.load_state()
            state.update(status="needs_repair", business_status="incomplete", formal_delivery_allowed=False)
            context.save_state(state)
            context.checkpoint("执行中断，保留来源与所有检查点", {"error": f"{type(exc).__name__}: {exc}"})
        raise


def resolve_mcp_plugin_ids(
    capabilities: list[str],
    requested_plugin_ids: list[str] | None = None,
) -> list[str]:
    """Make capability checkboxes the single source of truth for MCP plugins."""

    selected = [
        MCP_PLUGIN_BY_CAPABILITY[item]
        for item in capabilities
        if item in MCP_PLUGIN_BY_CAPABILITY
    ]
    if requested_plugin_ids is not None:
        requested = [str(item).strip() for item in requested_plugin_ids if str(item).strip()]
        if set(requested) != set(selected):
            raise ValueError("插件调用清单与前端勾选项不一致，已拒绝执行。")
    return selected


def build_final_answer_retry_config(config: dict[str, Any]) -> dict[str, Any]:
    """构造 MiniMax-M3 未产出正文时的最终交付重试配置。

    首轮继续保留 MiniMax-M3 的自适应思考能力。仅当首轮没有产生任何可展示正文时，
    才使用 MiniMax OpenAI 兼容接口公开支持的 ``thinking={"type": "disabled"}``
    重试，避免模型再次停留在推理阶段而没有报告正文。这里仍通过 AgentScope 2.0.3
    稳定的 ``extra_body`` 参数透传厂商字段，不使用任何 dev 接口。
    """

    retry_config = deepcopy(config)
    provider_name = str(retry_config.get("active_provider", ""))
    providers = retry_config.get("providers", {})
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        return retry_config

    model_name = str(expand_env(provider.get("model", ""))).strip()
    if model_name != "MiniMax-M3":
        return retry_config

    extra_body = dict(provider.get("extra_body") or {})
    extra_body["reasoning_split"] = True
    extra_body["thinking"] = {"type": "disabled"}
    provider["extra_body"] = extra_body
    return retry_config
REPORT_FILE_TYPES = {
    ".txt": "文字报告",
    ".md": "Markdown报告",
    ".html": "HTML PPT",
    ".pptx": "可编辑 PPTX",
}


def build_intelligence_export(domain: str, record_ids: list[str]) -> tuple[bytes, str]:
    """Create an Excel export with columns in the supplied template order."""
    config = {
        "policy": ("policy-intelligence.json", "政策明细", "政策情报明细.xlsx"),
    }
    if domain not in config:
        raise ValueError("不支持的情报类型")

    source_name, sheet_name, filename = config[domain]
    source_path = INTELLIGENCE_DATA_DIR / source_name
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    headers = [str(value) for value in payload.get("headers", [])]
    records = payload.get("records", [])
    if not headers or not isinstance(records, list):
        raise ValueError("情报数据文件结构不完整")

    id_key = "记录编号"
    if record_ids:
        by_id = {str(record.get(id_key, "")): record for record in records}
        records = [by_id[record_id] for record_id in record_ids if record_id in by_id]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False

    header_fill = PatternFill("solid", fgColor="2F6BFF")
    header_font = Font(name="Microsoft YaHei", size=10, bold=True, color="FFFFFF")
    body_font = Font(name="Microsoft YaHei", size=10, color="1F2937")
    thin = Side(style="thin", color="E4EAF3")
    border = Border(bottom=thin, right=thin)

    for column_index, header in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=column_index, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

    for row_index, record in enumerate(records, start=2):
        for column_index, header in enumerate(headers, start=1):
            value = record.get(header, "")
            if isinstance(value, list):
                value = "；".join(str(item) for item in value)
            if value is None:
                value = ""
            cell = sheet.cell(row=row_index, column=column_index, value=str(value))
            if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
                cell.data_type = "s"
            cell.font = body_font
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = border
        sheet.row_dimensions[row_index].height = 42

    sheet.row_dimensions[1].height = 42
    for column_index, header in enumerate(headers, start=1):
        sample_values = [header]
        sample_values.extend(str(record.get(header, "")) for record in records[:100])
        width = min(42, max(11, max(len(value) for value in sample_values) * 1.15))
        if header in {"记录编号", "省份", "城市", "区县", "车型", "动力类型", "补贴金额"}:
            width = min(width, 20)
        sheet.column_dimensions[get_column_letter(column_index)].width = width

    if headers:
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(1, len(records) + 1)}"

    output = BytesIO()
    workbook.save(output)
    return output.getvalue(), filename

HTML = (PROJECT_DIR / 'home.html').read_text(encoding='utf-8')
LEGACY_WORKBENCH_HTML = (PROJECT_DIR / 'legacy_workbench.html').read_text(encoding='utf-8')
STRATEGY_ANALYSIS_HTML = (PROJECT_DIR / 'strategy-analysis.html').read_text(encoding='utf-8')
NEW_CAR_DETAIL_HTML = (PROJECT_DIR / 'new-car-detail.html').read_text(encoding='utf-8')


class AgentDemoHandler(BaseHTTPRequestHandler):
    """极简 HTTP 服务，避免引入额外 Web 框架。"""

    server_version = "AgentScopeAutoDecisionDemo/0.2"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        request_path = parsed.path

        if request_path == '/forecast-engine-view':
            self._send_html((PROJECT_DIR / 'pages/forecast-engine.html').read_text(encoding='utf-8'))
            return
        if request_path.startswith('/api/forecast-engine/'):
            from integrations.forecast_engine_web import FORECAST_WEB_JOBS, status as forecast_status
            try:
                if request_path == '/api/forecast-engine/status': self._send_json(forecast_status())
                elif request_path == '/api/forecast-engine/jobs': self._send_json(FORECAST_WEB_JOBS.get(parse_qs(parsed.query).get('run_id',[''])[0]))
                else: self._send_json({'error':'未找到新版预测接口。'},status=404)
            except (ValueError,OSError) as exc: self._send_json({'error':str(exc)},status=400)
            return

        if request_path == '/weekly-report.html':
            self._send_html((PROJECT_DIR / 'weekly-report.html').read_text(encoding='utf-8'))
            return
        if request_path.startswith('/api/weekly-report/'):
            query = parse_qs(parsed.query)
            try:
                if request_path == '/api/weekly-report/status':
                    weekly_status = WEEKLY_REPORT_JOBS.status()
                    weekly_config = load_json_config()
                    weekly_status['default_model'] = weekly_config.get('active_provider', 'minimax')
                    weekly_status['models'] = [{'id': key, 'label': value.get('display_name') or {'minimax': 'MiniMax M3', 'bailian_token_plan': '百炼 Qwen3.7 Plus'}.get(key, key)} for key, value in (weekly_config.get('providers') or {}).items() if value.get('enabled') is not False]
                    self._send_json(weekly_status)
                elif request_path == '/api/weekly-report/jobs':
                    self._send_json(WEEKLY_REPORT_JOBS.get(query.get('run_id', [''])[0]))
                elif request_path == '/api/weekly-report/preview':
                    path = WEEKLY_REPORT_JOBS.download(query.get('run_id', [''])[0], 'html')
                    self._send_html(path.read_text(encoding='utf-8'))
                elif request_path == '/api/weekly-report/download':
                    path = WEEKLY_REPORT_JOBS.download(query.get('run_id', [''])[0], query.get('artifact', [''])[0])
                    mime = 'text/html; charset=utf-8' if path.suffix == '.html' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                    self._send_binary(path.read_bytes(), mime, path.name)
                else:
                    self._send_json({'error': '未找到周报接口。'}, status=404)
            except (ValueError, OSError) as exc:
                self._send_json({'error': str(exc)}, status=400)
            return

        if request_path.startswith('/api/forecast/'):
            query = parse_qs(parsed.query)
            try:
                if request_path == '/api/forecast/history':
                    self._send_json(FORECAST_JOBS.history(query.get('history_id', [''])[0], query.get('include_records', [''])[0] == '1'))
                elif request_path == '/api/forecast/jobs':
                    self._send_json(FORECAST_JOBS.get(query.get('run_id', [''])[0]))
                elif request_path == '/api/forecast/download':
                    path = FORECAST_JOBS.download(query.get('run_id', [''])[0], query.get('artifact', [''])[0])
                    mime = {'.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation', '.csv': 'text/csv; charset=utf-8'}[path.suffix.lower()]
                    self._send_binary(path.read_bytes(), mime, path.name)
                else:
                    self._send_json({'error': '未找到预测接口。'}, status=404)
            except (ValueError, OSError) as exc:
                self._send_json({'error': str(exc)}, status=400)
            return

        if request_path == "/":
            self._send_html(HTML)
            return

        if request_path in ('/legacy/workbench.html', '/legacy/workbench'):
            self._send_html(LEGACY_WORKBENCH_HTML)
            return

        if request_path in ('/strategy-analysis.html', '/strategy-analysis'):
            self._send_html(STRATEGY_ANALYSIS_HTML)
            return

        if request_path in ('/new-car-detail', '/new-car-detail.html'):
            self._send_html((PROJECT_DIR / 'new-car-detail.html').read_text(encoding='utf-8'))
            return

        if request_path in ('/reputation-detail', '/reputation-detail.html'):
            self._send_html((PROJECT_DIR / 'reputation-detail.html').read_text(encoding='utf-8'))
            return

        if request_path in ('/reputation-insight', '/reputation-insight.html'):
            self._send_html((PROJECT_DIR / 'reputation-insight.html').read_text(encoding='utf-8'))
            return

        if request_path.startswith("/outputs/") or request_path.startswith("/skills/html-ppt-skill/assets/"):
            self._send_file(request_path)
            return

        if request_path.startswith('/assets/'):
            asset_relative = request_path[len('/assets/'):]
            asset_path = PROJECT_DIR / 'assets' / asset_relative
            if asset_path.is_file():
                self._send_file('/' + str(asset_path.relative_to(PROJECT_DIR)).replace('\\', '/'))
                return
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if request_path == "/api/config":
            config = load_json_config()
            provider_name = config.get("active_provider", "")
            provider = config.get("providers", {}).get(provider_name, {})
            self._send_json({
                "active_provider": provider_name,
                "model": expand_env(provider.get("model", "")),
                "endpoint": expand_env(provider.get("base_url") or provider.get("host") or ""),
                "agents": config.get("agents", {}),
            })
            return

        if request_path == "/api/intelligence/policy-overview":
            load_dotenv(ENV_PATH, override=True)
            try:
                result = AGENT_LOOP_RUNNER.run(load_policy_overview(load_json_config()))
                self._send_json(result)
            except Exception:
                # Do not expose credentials or transport details in browser errors.
                self._send_json({"success": False, "error": "政策 MCP 数据查询失败，请检查连接、权限或稍后刷新。"}, status=502)
            return

        if request_path == '/api/intelligence/policy-query':
            from integrations.market_data_api import get_snapshot
            try:
                load_dotenv(ENV_PATH, override=True)
                result = AGENT_LOOP_RUNNER.run(get_snapshot(load_json_config(), 'policies', plugin_id='policy'))
                result['records'] = result.pop('items')
                self._send_json(result)
            except Exception:
                self._send_json({'success': False, 'error': '政策数据查询失败，请稍后重试'}, status=502)
            return

        if request_path in {"/api/intelligence/rights-overview", "/api/intelligence/rights-query"}:
            load_dotenv(ENV_PATH, override=True)
            try:
                config = load_json_config()
                if request_path.endswith("rights-overview"):
                    result = AGENT_LOOP_RUNNER.run(rights_overview(config))
                else:
                    params = json.loads(parse_qs(parsed.query).get("params", ["{}"]) [0])
                    result = AGENT_LOOP_RUNNER.run(call_rights(config, "rights_search_offers", {"params": params}))
                self._send_json(result)
            except Exception:
                self._send_json({"success": False, "error": "云端权益 MCP 查询失败，请检查加密通道、权限或刷新重试。"}, status=502)
            return

        if request_path == "/api/mcp-plugins":
            load_dotenv(ENV_PATH, override=True)
            config = load_json_config()
            bundle = AGENT_LOOP_RUNNER.run(load_market_mcp_plugins(config))
            self._send_json(bundle.as_dict())
            return

        if request_path == "/api/reports":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0]
            self._send_json(list_generated_reports(query))
            return

        if request_path == "/api/audio-tags/config":
            self._send_json({"taxonomy": DEFAULT_TAG_TAXONOMY})
            return

        if request_path == "/api/quality-gate/rules":
            self._send_json({"rules": QUALITY_RULES})
            return

        if request_path == "/api/market-skill/status":
            self._send_json(MarketAnalysisSkill(load_json_config()).status())
            return

        if request_path == "/api/monthly-report-connector/status":
            status = MONTHLY_REPORT_BROWSER.status()
            status['narrative_rule_version'] = NARRATIVE_RULE_VERSION
            status['narrative_release_revalidation'] = True
            status['source_contract_version'] = '2026-10-09-month-reuse-v2'
            self._send_json(status)
            return

        if request_path == "/api/macro-ledger/status":
            self._send_json(load_macro_ledger_status())
            return

        if request_path == "/api/macro-ledger/download":
            self._send_macro_ledger()
            return

        if request_path in {"/api/new-car/dashboard", "/api/new-car/list", "/api/new-car/planned", "/api/new-car/detail", "/api/new-car/sales"}:
            params = parse_qs(parsed.query)
            operation = request_path.rsplit("/", 1)[-1]
            try:
                load_dotenv(ENV_PATH, override=True)
                payload = AGENT_LOOP_RUNNER.run(load_new_car(
                    load_json_config(), operation,
                    params.get("model", [""])[0].strip(),
                    params.get("brand", [""])[0].strip(),
                    params.get("energy_type", [""])[0].strip(),
                ))
                self._send_json(payload)
            except Exception as exc:
                self._send_json({"success": False, "source": "unavailable", "rows": [],
                                 "error": "新车 MCP 查询失败，请检查服务连接后刷新重试",
                                 "error_type": type(exc).__name__}, HTTPStatus.BAD_GATEWAY)
            return

        if request_path in {"/api/reputation/overview", "/api/reputation/reviews",
                            "/api/new-car/reputation", "/api/new-car/reputation-tree",
                            "/api/new-car/reputation-reviews"}:
            query = parse_qs(parsed.query)
            params = {k: v[0] for k, v in query.items()}
            operation = {"/api/reputation/overview": "overview", "/api/reputation/reviews": "reviews",
                         "/api/new-car/reputation": "summary", "/api/new-car/reputation-tree": "tree",
                         "/api/new-car/reputation-reviews": "evidence"}[request_path]
            try:
                if operation == "reviews":
                    params["limit"] = min(100, max(1, int(params.get("limit", 20))))
                    params["offset"] = max(0, int(params.get("offset", 0)))
                    if not params.get("source"):
                        params.pop("source", None)
                load_dotenv(ENV_PATH, override=True)
                self._send_json(AGENT_LOOP_RUNNER.run(load_reputation(load_json_config(), operation, params)))
            except (ValueError, TypeError):
                self._send_json({"success": False, "source": "unavailable", "error": "口碑查询参数无效或服务返回不完整，请检查后重试"}, status=400)
            except Exception as exc:
                self._send_json({"success": False, "source": "unavailable", "error": "口碑 MCP 查询失败，请检查服务连接后重试",
                                 "error_type": type(exc).__name__}, status=502)
            return

        if request_path == "/api/agent-run/latest":
            with LATEST_AGENT_RUN_LOCK:
                self._send_json(dict(LATEST_AGENT_RUN))
            return

        if request_path == "/api/projects":
            params = parse_qs(parsed.query)
            project_id = params.get("id", [""])[0].strip()
            projects = load_project_runs()
            if project_id:
                project = next((item for item in projects if item.get("id") == project_id), None)
                if project is None:
                    self._send_json({"error": "项目记录不存在。"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json(project)
                return
            self._send_json({"items": [project_list_item(item) for item in projects]})
            return

        if request_path.startswith("/api/monthly-report/jobs/"):
            run_id = unquote(request_path.rsplit("/", 1)[-1]).strip()
            job = MONTHLY_REPORT_JOBS.get(run_id)
            if job is None:
                self._send_json({"error": "未找到月报后台任务。"}, status=404)
                return
            self._send_json(job)
            return

        if request_path.startswith("/api/macro-report/draft/"):
            run_id = unquote(request_path.rsplit("/", 1)[-1]).strip()
            try:
                delivery = verified_macro_draft_delivery(run_id)
                file_path = Path(delivery["path"])
                data = file_path.read_bytes()
                if hashlib.sha256(data).hexdigest() != delivery["sha256"]:
                    raise ValueError("草稿文件下载时指纹变化，已阻断。")
            except (ValueError, OSError, TypeError) as exc:
                self._send_json({"error": str(exc), "code": "macro_draft_not_verified"}, status=409)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.presentationml.presentation")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Content-Disposition", f"attachment; filename=macro_public_draft.pptx; filename*=UTF-8''{quote(file_path.name)}")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if request_path.startswith("/api/macro-report/retained/"):
            run_id = unquote(request_path.rsplit("/", 1)[-1]).strip()
            try:
                delivery = verified_macro_retained_delivery(run_id)
                file_path = Path(delivery["path"])
                data = file_path.read_bytes()
                if hashlib.sha256(data).hexdigest() != delivery["sha256"]:
                    raise ValueError("历史延续版文件下载时指纹变化，已阻断。")
            except (ValueError, OSError, TypeError) as exc:
                self._send_json({"error": str(exc), "code": "macro_retained_not_verified"}, status=409)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.presentationml.presentation")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Content-Disposition", f"attachment; filename=macro_historical_retained.pptx; filename*=UTF-8''{quote(file_path.name)}")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if request_path.startswith("/api/macro-report/jobs/"):
            run_id = unquote(request_path.rsplit("/", 1)[-1]).strip()
            job = MACRO_REPORT_JOBS.get(run_id)
            if job is None:
                self._send_json({"error": "未找到宏观月报后台任务。"}, status=404)
                return
            self._send_json(job)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/projects":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        params = parse_qs(parsed.query)
        project_id = params.get("id", [""])[0].strip()
        if not project_id:
            self._send_json({"error": "项目 ID 不能为空。"}, status=400)
            return
        try:
            deleted = delete_project_run(project_id)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=409)
            return
        if deleted is None:
            self._send_json({"error": "未找到项目。"}, status=404)
            return
        self._send_json({"success": True, "deleted_id": project_id})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == '/api/forecast-engine/jobs':
            from integrations.forecast_engine_web import FORECAST_WEB_JOBS
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 16000: raise ValueError('预测请求为空或过大。')
                payload=json.loads(self.rfile.read(length).decode('utf-8'))
                if not isinstance(payload,dict): raise ValueError('预测请求必须为对象。')
                self._send_json(FORECAST_WEB_JOBS.start(payload,AGENT_LOOP_RUNNER.run),status=202)
            except (ValueError,OSError) as exc: self._send_json({'error':str(exc)},status=400)
            return
        if parsed.path.startswith('/api/weekly-report/'):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > 64000:
                    self._send_json({'error': '周报请求为空或过大。'}, status=413)
                    self.close_connection = True
                    return
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                if not isinstance(payload, dict):
                    raise ValueError('周报请求必须为对象。')
                if parsed.path == '/api/weekly-report/jobs':
                    self._send_json(WEEKLY_REPORT_JOBS.start(payload), status=202)
                elif parsed.path == '/api/weekly-report/jobs/resume':
                    self._send_json(WEEKLY_REPORT_JOBS.resume(str(payload.get('run_id', ''))), status=202)
                elif parsed.path == '/api/weekly-report/jobs/cancel':
                    self._send_json(WEEKLY_REPORT_JOBS.cancel(str(payload.get('run_id', ''))))
                else:
                    self._send_json({'error': '未找到周报接口。'}, status=404)
            except (ValueError, OSError) as exc:
                self._send_json({'error': str(exc)}, status=400)
            except Exception as exc:
                self._send_json({'error': type(exc).__name__ + ': ' + str(exc)}, status=500)
            return
        if parsed.path.startswith('/api/forecast/'):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                limit = FORECAST_JOBS.MAX_UPLOAD_BYTES if parsed.path == '/api/forecast/history' else 64000
                if length <= 0 or length > limit:
                    self._send_json({'error': '请求为空或超过允许大小。'}, status=413)
                    self.close_connection = True
                    return
                body = self.rfile.read(length)
                if parsed.path == '/api/forecast/history':
                    query = parse_qs(parsed.query)
                    self._send_json(FORECAST_JOBS.upload(query.get('filename', [''])[0], body, query.get('unit', [''])[0]))
                elif parsed.path in {'/api/forecast/jobs', '/api/forecast/jobs/resume'}:
                    payload = json.loads(body.decode('utf-8'))
                    if not isinstance(payload, dict):
                        raise ValueError('预测请求必须为对象。')
                    job = FORECAST_JOBS.resume(str(payload.get('run_id', ''))) if parsed.path.endswith('/resume') else FORECAST_JOBS.start(payload)
                    self._send_json(job, status=202)
                else:
                    self._send_json({'error': '未找到预测接口。'}, status=404)
            except (ValueError, OSError) as exc:
                self._send_json({'error': str(exc)}, status=400)
            except Exception as exc:
                self._send_json({'error': type(exc).__name__ + ': ' + str(exc)}, status=500)
            return
        if self.path not in {"/api/assistant/chat", "/api/chat", "/api/ppt", "/api/audio-tags/run", "/api/quality-gate", "/api/market-skill/validate", "/api/intelligence/export", "/api/projects/update", "/api/macro-ledger", "/api/monthly-report/jobs", "/api/monthly-report/jobs/cancel", "/api/monthly-report/jobs/resume", "/api/macro-report/jobs", "/api/macro-report/jobs/cancel", "/api/macro-report/jobs/resume"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        length = int(self.headers.get("Content-Length", "0"))
        if self.path == "/api/assistant/chat" and (length <= 0 or length > 300000):
            self._send_json({"error": "会话请求为空或过长，请新建会话。"}, status=400)
            return
        if self.path == "/api/macro-ledger":
            if length <= 0:
                self._send_json({"error": "请选择需要上传的标准台账。"}, status=400)
                return
            if length > MAX_MACRO_LEDGER_BYTES:
                self._send_json({"error": "台账文件不能超过 50 MB。"}, status=413)
                return
            filename = unquote(self.headers.get("X-File-Name", "")).strip()
            data = self.rfile.read(length)
            try:
                self._send_json(save_macro_ledger(filename, data))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
            except Exception as exc:
                self._send_json({"error": f"台账保存失败：{exc}"}, status=500)
            return

        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(body or "{}")

        try:
            if self.path == "/api/assistant/chat":
                messages = payload.get("messages")
                if not isinstance(messages, list) or not 1 <= len(messages) <= 20:
                    raise ValueError("会话应包含 1—20 条消息，请新建会话后继续。")
                history = []
                for message in messages:
                    if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
                        raise ValueError("会话消息格式不正确。")
                    content = message.get("content")
                    if not isinstance(content, str) or not content.strip() or len(content) > 12000:
                        raise ValueError("单条消息不能为空或超过 12000 字。")
                    history.append({"role": message["role"], "content": content.strip()})
                if history[-1]["role"] != "user" or sum(len(item["content"]) for item in history) > 60000:
                    raise ValueError("会话过长或缺少当前问题，请新建会话。")
                from integrations.home_assistant import answer_home_question
                load_dotenv(ENV_PATH, override=True)
                # No AGENT_RUN_LOCK here: the home assistant is just an LLM
                # call with optional MCP discovery, and it must stay responsive
                # while weekly/monthly jobs run their own agents in parallel.
                try:
                    result = AGENT_LOOP_RUNNER.run(answer_home_question(load_json_config(), history))
                except AuthenticationError:
                    self._send_json({"error": "MiniMax 服务鉴权失败，请检查服务端模型配置。"}, status=401)
                    return
                except Exception:
                    self._send_json({"error": "AI 服务暂时无法完成回答，请稍后重试或缩小问题范围。"}, status=502)
                    return
                self._send_json(result)
                return
            if self.path == "/api/macro-report/jobs":
                job = start_macro_background_job(payload)
                self._send_json(job, status=202)
                return

            if self.path in {"/api/macro-report/jobs/cancel", "/api/macro-report/jobs/resume"}:
                run_id = str(payload.get("run_id", "")).strip()
                if not run_id:
                    self._send_json({"error": "run_id 不能为空。"}, status=400)
                    return
                job = MACRO_REPORT_JOBS.cancel(run_id) if self.path.endswith("/cancel") else MACRO_REPORT_JOBS.resume(run_id)
                if job is None:
                    self._send_json({"error": "未找到宏观月报后台任务。"}, status=404)
                    return
                self._send_json(job)
                return

            if self.path == "/api/monthly-report/jobs":
                capabilities = payload.get("capabilities", [])
                if not isinstance(capabilities, list):
                    self._send_json({"error": "capabilities 必须是能力 ID 数组。"}, status=400)
                    return
                capabilities = [str(item) for item in capabilities]
                analysis_type = resolve_analysis_type(
                    str(payload.get("analysis_type", "")).strip(),
                    capabilities,
                )
                if analysis_type != PASSENGER_MONTHLY_CAPABILITY_ID:
                    self._send_json({"error": "该后台任务接口仅用于乘用车月报技能。"}, status=400)
                    return
                requested_plugins = payload.get("mcp_plugins")
                if requested_plugins is not None and not isinstance(requested_plugins, list):
                    self._send_json({"error": "mcp_plugins 必须是插件 ID 数组。"}, status=400)
                    return
                payload["capabilities"] = capabilities
                payload["mcp_plugins"] = resolve_mcp_plugin_ids(capabilities, requested_plugins)
                try:
                    job = MONTHLY_REPORT_JOBS.start(payload)
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                    return
                self._send_json(job, status=202)
                return

            if self.path in {"/api/monthly-report/jobs/cancel", "/api/monthly-report/jobs/resume"}:
                run_id = str(payload.get("run_id", "")).strip()
                if not run_id:
                    self._send_json({"error": "run_id 不能为空。"}, status=400)
                    return
                job = (
                    MONTHLY_REPORT_JOBS.cancel(run_id)
                    if self.path.endswith("/cancel")
                    else MONTHLY_REPORT_JOBS.resume(run_id)
                )
                if job is None:
                    self._send_json({"error": "未找到月报后台任务。"}, status=404)
                    return
                self._send_json(job)
                return

            if self.path == "/api/intelligence/export":
                domain = str(payload.get("domain", "")).strip()
                record_ids = payload.get("recordIds", [])
                if not isinstance(record_ids, list):
                    record_ids = []
                record_ids = [str(value) for value in record_ids[:5000]]
                if domain == "rights":
                    load_dotenv(ENV_PATH, override=True)
                    params = payload.get("rightsParams")
                    if not isinstance(params, dict) or not params.get("data_version"):
                        raise ValueError("请先查询云端权益，再按同一版本导出")
                    data, filename = AGENT_LOOP_RUNNER.run(rights_export(load_json_config(), params))
                else:
                    if domain != 'policy': raise ValueError('不支持的数据域')
                    from integrations.market_data_api import export_data
                    load_dotenv(ENV_PATH, override=True)
                    data, filename = AGENT_LOOP_RUNNER.run(export_data(load_json_config(), 'policies/export',
                        {'record_ids': record_ids, 'data_version': payload.get('dataVersion')}, 'policy'))
                self._send_binary(
                    data,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    filename,
                )
                return

            if self.path == "/api/audio-tags/run":
                instruction = str(payload.get("instruction", "")).strip()
                selected_tags = payload.get("selected_tags", [])
                if not isinstance(selected_tags, list):
                    selected_tags = []
                selected_tags = [str(tag) for tag in selected_tags]
                result = run_audio_tagging_workflow(
                    instruction or "执行访谈类音频处理工作流，并生成用户标签洞察。",
                    selected_tags,
                )
                self._send_json(result)
                return

            if self.path == "/api/quality-gate":
                tool_events = payload.get("tool_events", [])
                if not isinstance(tool_events, list):
                    tool_events = []
                self._send_json(evaluate_report_quality(
                    str(payload.get("report", "")),
                    str(payload.get("question", "")),
                    tool_events,
                ))
                return

            if self.path == "/api/projects/update":
                project_id = str(payload.get("id", "")).strip()
                quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
                if not project_id:
                    self._send_json({"error": "项目 ID 不能为空。"}, status=400)
                    return
                updated = update_project_run(project_id, quality)
                if not updated:
                    self._send_json({"error": "未找到项目。"}, status=404)
                    return
                self._send_json({"success": True, "project": project_list_item(updated)})
                return

            if self.path == "/api/market-skill/validate":
                capabilities = payload.get("capabilities", [])
                if not isinstance(capabilities, list):
                    self._send_json({"error": "capabilities 必须是能力 ID 数组。"}, status=400)
                    return
                requested_analysis_type = resolve_analysis_type(
                    str(payload.get("analysis_type", "")).strip(),
                    [str(item) for item in capabilities],
                )
                if requested_analysis_type == "passenger_car_monthly_report":
                    result = AGENT_LOOP_RUNNER.run(MONTHLY_REPORT_BROWSER.preflight(
                        open_page=True, report_month=str(payload.get("report_month") or ""),
                        force_refresh=payload.get("force_refresh") is True))
                    result.update({
                        "name": "乘用车月报智能生成",
                        "analysis_type": requested_analysis_type,
                    })
                    if not result.get("page_ready"):
                        result["error"] = result.get("message", "数据源检查未通过。")
                        self._send_json(result, status=409)
                        return
                    self._send_json(result)
                    return
                skill = MarketAnalysisSkill(load_json_config())
                context = skill.prepare(
                    str(payload.get("question", "请生成中国乘用车月度市场分析报告。")),
                    "market_monthly_report",
                    payload.get("dataset_path"),
                    payload.get("sheet_name"),
                )
                self._send_json(context.as_response())
                return

            if self.path == "/api/ppt":
                markdown = str(payload.get("markdown", "")).strip()
                title = str(payload.get("title", "乘用车市场战略决策AI智能体PPT")).strip()
                capabilities = payload.get("capabilities", [])
                if not isinstance(capabilities, list):
                    self._send_json({"error": "capabilities 必须是能力 ID 数组。"}, status=400)
                    return
                analysis_type = resolve_analysis_type(
                    str(payload.get("analysis_type", "")).strip(),
                    [str(item) for item in capabilities],
                )
                if analysis_type in {"forecast", "market_forecast", "forecast_engine"}:
                    self._send_json({"error": "新版市场预测尚未完成真实数据回测和业务审核，不允许作为正式PPT交付。", "code": "forecast_real_data_acceptance_pending"}, status=409)
                    return
                if analysis_type == "macro_monthly_report":
                    run_id = str(payload.get("run_id", "")).strip()
                    try:
                        self._send_json(verified_macro_delivery(run_id))
                    except ValueError as exc:
                        self._send_json({"error": str(exc), "code": "macro_business_gate_not_passed"}, status=409)
                    return
                if analysis_type == "passenger_car_monthly_report":
                    run_id = str(payload.get("run_id", "")).strip()
                    if not run_id:
                        self._send_json({"error": "缺少本轮月报 run_id，请重新执行月报分析后生成PPT。"}, status=400)
                        return
                    result = generate_passenger_monthly_pptx(run_id, title)
                    self._send_json(result)
                    return
                if not markdown:
                    self._send_json({"error": "PPT Markdown 内容不能为空。"}, status=400)
                    return
                result = generate_ppt_from_markdown(
                    markdown,
                    title,
                    analysis_type,
                    payload.get("dataset_path"),
                    payload.get("sheet_name"),
                )
                self._send_json(result)
                return

            question = str(payload.get("question", "")).strip()
            agent_key = str(payload.get("agent", "market_strategy")).strip() or "market_strategy"
            capabilities = payload.get("capabilities", [])
            if not isinstance(capabilities, list):
                self._send_json({"error": "capabilities 必须是能力 ID 数组。"}, status=400)
                return
            capabilities = [str(item) for item in capabilities]
            analysis_type = resolve_analysis_type(
                str(payload.get("analysis_type", "")).strip(),
                capabilities,
            )
            model_provider = str(payload.get("model_provider", "")).strip()
            mcp_plugin_ids = payload.get("mcp_plugins")
            if mcp_plugin_ids is not None and not isinstance(mcp_plugin_ids, list):
                self._send_json({"error": "mcp_plugins 必须是插件 ID 数组。"}, status=400)
                return
            mcp_plugin_ids = resolve_mcp_plugin_ids(capabilities, mcp_plugin_ids)
            if not question:
                self._send_json({"error": "问题不能为空。"}, status=400)
                return
            if analysis_type == MACRO_MONTHLY_CAPABILITY_ID:
                # Compatibility for clients still posting to /api/chat:
                # submit the same durable pipeline and return immediately.
                self._send_json(start_macro_background_job(payload), status=202)
                return
            # AgentScope 2.0.3 的本地工具审计事件由 tools.custom_tools 暂存；
            # 串行化 chat 请求可避免并发演示时不同请求的工具日志相互串线。
            with AGENT_RUN_LOCK:
                result = AGENT_LOOP_RUNNER.run(
                    run_agent_once(
                        agent_key,
                        question,
                        analysis_type,
                        payload.get("dataset_path"),
                        payload.get("sheet_name"),
                        model_provider,
                        mcp_plugin_ids,
                    ),
                )
            project = store_project_run(result, question, analysis_type, model_provider, capabilities)
            result["project"] = project_list_item(project)
            store_latest_agent_run(result, question, analysis_type)
            self._send_json(result)
        except ValueError as exc:
            self._send_json({"error": str(exc), "code": "invalid_capability_binding"}, status=400)
        except AuthenticationError:
            self._send_json({
                "error": "模型服务鉴权失败：请检查所选模型的 API Key 与 OpenAI 兼容端点是否匹配。"
            }, status=401)
        except Exception as exc:
            self._send_json({"error": type(exc).__name__ + ": " + str(exc)}, status=500)

    def log_message(self, fmt: str, *args: Any) -> None:
        print("[web] " + self.address_string() + " - " + (fmt % args))

    def _send_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, request_path: str) -> None:
        """只允许访问 outputs 与 html-ppt-skill 静态资产。"""
        relative = unquote(request_path).lstrip("/").replace("\\", "/")
        output_root = (PROJECT_DIR / "outputs").resolve()
        skill_asset_root = (PROJECT_DIR / "skills" / "html-ppt-skill" / "assets").resolve()
        home_asset_root = (PROJECT_DIR / "assets").resolve()
        file_path = (PROJECT_DIR / relative).resolve()
        allowed = False
        try:
            if output_root in file_path.parents:
                allowed = True
            if skill_asset_root in file_path.parents:
                allowed = True
            if home_asset_root in file_path.parents:
                allowed = True
        except Exception:
            allowed = False

        if not allowed or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        suffix = file_path.suffix.lower()
        if suffix == ".pptx" and formal_download_blocked(file_path.name, SKILL_RUNTIME_ROOT):
            self._send_json({"error": "该宏观月报未通过业务验收，正式下载已阻断；文件保留用于修复。", "code": "macro_business_gate_not_passed"}, status=409)
            return
        macro_download = None
        if suffix == ".pptx":
            macro_run = re.match(r"^(macro-\d{8}-\d{6}-[a-f0-9]{8})-", file_path.name)
            if macro_run:
                try:
                    macro_download = verified_macro_delivery(macro_run.group(1))
                    if unquote(macro_download["pptx_url"]).rsplit("/", 1)[-1] != file_path.name:
                        raise ValueError("请求文件不是本轮已验收发布产物。")
                except (ValueError, OSError) as exc:
                    self._send_json({"error": str(exc), "code": "macro_artifact_not_verified"}, status=409)
                    return
        content_type_map = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
        content_type = content_type_map.get(suffix, "text/plain; charset=utf-8")
        data = file_path.read_bytes()
        if macro_download and hashlib.sha256(data).hexdigest() != macro_download["sha256"]:
            self._send_json({"error": "下载文件内容已变化，与验收指纹不一致。", "code": "macro_artifact_changed"}, status=409)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        if suffix in {".css", ".js", ".json"}:
            self.send_header("Cache-Control", "no-store, max-age=0")
        if suffix == ".pptx":
            safe_download_name = quote(file_path.name)
            self.send_header(
                "Content-Disposition",
                f"attachment; filename=market_monthly_report.pptx; filename*=UTF-8''{safe_download_name}",
            )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_macro_ledger(self) -> None:
        status = load_macro_ledger_status()
        if not status.get("available"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        file_path = MACRO_LEDGER_DIR / str(status.get("stored_name", ""))
        if not file_path.is_file() or file_path.parent.resolve() != MACRO_LEDGER_DIR.resolve():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = file_path.read_bytes()
        safe_name = quote(str(status.get("original_name") or file_path.name))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition", f"attachment; filename=macro-ledger{file_path.suffix}; filename*=UTF-8''{safe_name}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_binary(self, data: bytes, content_type: str, filename: str) -> None:
        safe_download_name = quote(filename)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header(
            "Content-Disposition",
            f"attachment; filename=intelligence-export.xlsx; filename*=UTF-8''{safe_download_name}",
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def extract_report_search_text(path: Path) -> str:
    """提取报告正文片段，用于业务侧模糊检索。

    这里不解析完整 PPT 结构，只抽取可读文本，保持 Demo 足够轻量；
    后续可替换为 SQLite 全文索引、向量检索或 MCP 文件库检索。
    """
    if path.suffix.lower() == ".pptx":
        try:
            from pptx import Presentation

            presentation = Presentation(path)
            raw = " ".join(
                shape.text
                for slide in presentation.slides
                for shape in slide.shapes
                if getattr(shape, "has_text_frame", False) and shape.text
            )
        except Exception:
            return ""
        return re.sub(r"\s+", " ", raw).strip()

    raw = path.read_text(encoding="utf-8", errors="ignore")[:160000]
    if path.suffix.lower() == ".html":
        raw = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
        raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.IGNORECASE)
        raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def build_report_snippet(text: str, keyword: str) -> str:
    """根据关键词生成一段命中摘要，便于业务人员快速判断是否打开报告。"""
    if not text:
        return ""
    if not keyword:
        return text[:180]
    lower_text = text.lower()
    lower_keyword = keyword.lower()
    index = lower_text.find(lower_keyword)
    if index < 0:
        return text[:180]
    start = max(0, index - 70)
    end = min(len(text), index + len(keyword) + 130)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + text[start:end] + suffix


def list_generated_reports(query: str) -> dict[str, Any]:
    """扫描 outputs/ppt 下的历史报告，返回前端报告资产库列表。"""
    keyword = query.strip()
    items: list[dict[str, Any]] = []
    if not PPT_OUTPUT_DIR.exists():
        return {"query": keyword, "items": items}

    for path in PPT_OUTPUT_DIR.rglob("*"):
        suffix = path.suffix.lower()
        if not path.is_file() or suffix not in REPORT_FILE_TYPES:
            continue
        try:
            relative_to_ppt = path.relative_to(PPT_OUTPUT_DIR)
            if "template" in relative_to_ppt.parts:
                continue
            search_text = extract_report_search_text(path)
            haystack = "\n".join([path.name, str(relative_to_ppt), search_text]).lower()
            if keyword and keyword.lower() not in haystack:
                continue
            stat = path.stat()
            relative_to_project = path.relative_to(PROJECT_DIR)
            item = {
                "name": path.name,
                "type": REPORT_FILE_TYPES.get(suffix, suffix),
                "ext": suffix,
                "relative_path": relative_to_project.as_posix(),
                "url": "/" + relative_to_project.as_posix(),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "mtime": stat.st_mtime,
                "snippet": build_report_snippet(search_text, keyword),
            }
            items.append(item)
        except OSError:
            continue

    items.sort(key=lambda item: item["mtime"], reverse=True)
    for item in items:
        item.pop("mtime", None)
    return {"query": keyword, "items": items[:80]}


def safe_filename(text: str) -> str:
    """生成适合 Windows 文件系统的短文件名。"""
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("_")[:60]
    return cleaned or "agent_report_ppt"


def load_project_runs() -> list[dict[str, Any]]:
    """读取持久化的智能体任务记录，损坏文件按空列表处理。"""

    with PROJECT_RUNS_LOCK:
        if not PROJECT_RUNS_FILE.is_file():
            return []
        try:
            payload = json.loads(PROJECT_RUNS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    if not isinstance(payload, list):
        return []
    return sorted(
        (item for item in payload if isinstance(item, dict)),
        key=lambda item: str(item.get("created_at", "")),
        reverse=True,
    )


def project_category(agent: str, analysis_type: str) -> str:
    if agent == "user_insight_config" or analysis_type in {"user", "user_insight"}:
        return "用户洞察"
    if analysis_type in {"forecast", "market_forecast"}:
        return "市场预测"
    if analysis_type == "auto_weekly_report":
        return "资讯快报"
    return "市场分析"


def report_title(answer: str, question: str) -> str:
    heading = re.search(r"^#{1,3}\s+(.+?)\s*$", answer, flags=re.MULTILINE)
    source = heading.group(1) if heading else question
    cleaned = re.sub(r"[*_`#]+", "", source).strip()
    return (cleaned[:72] + "…") if len(cleaned) > 72 else (cleaned or "未命名分析任务")


def report_summary(answer: str) -> str:
    for block in re.split(r"\n\s*\n", answer):
        cleaned = re.sub(r"^[#>*\-\s]+", "", block).strip()
        cleaned = re.sub(r"[*_`|]", "", cleaned)
        if cleaned and len(cleaned) >= 12:
            return (cleaned[:132] + "…") if len(cleaned) > 132 else cleaned
    return "报告已生成，可进入项目查看完整结果。"


def project_list_item(project: dict[str, Any]) -> dict[str, Any]:
    detail_only = {"answer", "tool_events", "skill", "skill_run", "quality", "capabilities", "execution_stages"}
    return {key: value for key, value in project.items() if key not in detail_only}


def store_project_run(
    result: dict[str, Any],
    question: str,
    analysis_type: str,
    model_provider: str,
    capabilities: list[Any] | None = None,
    run_id: str = "",
    replace_existing: bool = False,
) -> dict[str, Any]:
    """将每次智能体分析持久化到项目台账，完整报告可按项目 ID 回看。"""

    answer = str(result.get("answer", ""))
    agent = str(result.get("agent", "market_strategy"))
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    skill = result.get("skill") if isinstance(result.get("skill"), dict) else {}
    skill_run = result.get("skill_run") if isinstance(result.get("skill_run"), dict) else {}
    skill_state = skill_run.get("state") if isinstance(skill_run.get("state"), dict) else {}
    runtime_status = str(skill_state.get("status", ""))
    runtime_validation = (
        skill_state.get("validation")
        if isinstance(skill_state.get("validation"), dict)
        else {}
    )
    runtime_passed = runtime_validation.get("status") == "passed"
    from utils.macro_report_delivery import verified_draft_state
    public_draft_ready = (result.get("delivery_mode") == "public_draft"
                          and result.get("draft_delivery_allowed") is True
                          and result.get("formal_delivery_allowed") is False
                          and verified_draft_state(skill_state, str(result.get("run_id") or skill_run.get("run_id") or "")))
    business_incomplete = result.get("business_status") == "incomplete" or skill_state.get("business_status") == "incomplete"
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    project = {
        "id": "proj-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid4().hex[:6],
        "title": report_title(answer, question),
        "question": question[:1200],
        "summary": report_summary(answer),
        "category": project_category(agent, analysis_type),
        "agent": agent,
        "agent_label": "用户洞察Agent" if agent == "user_insight_config" else "市场战略Agent",
        "analysis_type": analysis_type or "自动识别",
        "model_provider": model_provider or str(result.get("model_provider", "")) or "默认模型",
        "status": "执行中" if runtime_status in {"created", "running"} else "已暂停" if runtime_status == "cancelled" else "失败" if runtime_status == "failed" else "需要核对" if runtime_status == "needs_review" else "部分完成" if result.get("report_completion")=="partial_completed" else "草稿就绪" if public_draft_ready else "部分完成" if business_incomplete else "已完成" if not skill_run or runtime_passed else "待修复",
        "quality_status": (
            "草稿验收通过" if public_draft_ready else str(quality.get("overall_status") or "待补充") if business_incomplete else "Skill验收通过"
            if runtime_passed
            else "Skill验收未通过" if skill_run else str(skill.get("output_gate", "")) or "已生成"
        ),
        "answer_length": len(answer),
        "tool_count": len(result.get("tool_events", [])) if isinstance(result.get("tool_events"), list) else 0,
        "created_at": created_at,
        "answer": answer,
        "capabilities": [str(item) for item in (capabilities or []) if str(item).strip()],
        "tool_events": result.get("tool_events", []) if isinstance(result.get("tool_events"), list) else [],
        "skill": skill,
        "skill_run": skill_run,
        "quality": quality,
        "business_status": "draft_passed" if public_draft_ready else "incomplete" if business_incomplete else "",
        "delivery_mode": result.get("delivery_mode", "formal"),
        "report_completion": result.get("report_completion"),
        "pending_pages": result.get("pending_pages",[]),
        "retained_delivery_allowed": result.get("retained_delivery_allowed",False),
        "retained_delivery_url": result.get("retained_delivery_url", ""),
        "draft_delivery_allowed": public_draft_ready,
        "draft_delivery_url": result.get("draft_delivery_url", "") if public_draft_ready else "",
        "formal_delivery_allowed": result.get("formal_delivery_allowed", True),
        "execution_stages": (
            [
                {
                    "id": str(item.get("id", "")),
                    "status": str(item.get("status", "pending")),
                    "summary": str(item.get("summary") or item.get("title") or ""),
                }
                for item in skill_state.get("plan", [])
            ]
            if skill_state.get("plan")
            else [
            {"id": "intent", "status": "done", "summary": "已识别任务意图与分析范围。"},
            {"id": "tools", "status": "done", "summary": "已完成工具、数据与证据准备。"},
            {"id": "reasoning", "status": "done", "summary": "已按业务框架完成结构化分析。"},
            {"id": "quality", "status": "done", "summary": "已执行数据质量门禁。"},
            {"id": "report", "status": "done", "summary": "完整报告已生成并归档。"},
            ]
        ),
        "detail_url": "",
        "run_id": run_id,
    }
    project["detail_url"] = ("/weekly-report.html?run_id=" + quote(run_id)
                             if analysis_type == "auto_weekly_report" and run_id
                             else "/strategy-analysis.html?project=" + quote(project["id"]))

    with PROJECT_RUNS_LOCK:
        PROJECT_RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
        projects: list[dict[str, Any]] = []
        if PROJECT_RUNS_FILE.is_file():
            try:
                current = json.loads(PROJECT_RUNS_FILE.read_text(encoding="utf-8"))
                if isinstance(current, list):
                    projects = [item for item in current if isinstance(item, dict)]
            except (OSError, ValueError):
                projects = []
        if run_id:
            existing = next((item for item in projects if item.get("run_id") == run_id), None)
            if existing is not None:
                if not replace_existing:
                    return existing
                project["id"] = existing["id"]
                project["created_at"] = existing.get("created_at", created_at)
                project["updated_at"] = created_at
                project["detail_url"] = ("/weekly-report.html?run_id=" + quote(run_id)
                                         if analysis_type == "auto_weekly_report" and run_id
                                         else "/strategy-analysis.html?project=" + quote(project["id"]))
                projects = [item for item in projects if item.get("run_id") != run_id]
        projects.insert(0, project)
        projects = projects[:500]
        temp_path = PROJECT_RUNS_FILE.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(PROJECT_RUNS_FILE)
    return project


def update_project_run(project_id: str, quality: dict[str, Any]) -> dict[str, Any] | None:
    """补写浏览器端完成的质量门禁结果，保证历史任务可原样回放。"""

    with PROJECT_RUNS_LOCK:
        if not PROJECT_RUNS_FILE.is_file():
            return None
        try:
            payload = json.loads(PROJECT_RUNS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, list):
            return None
        updated = None
        for item in payload:
            if isinstance(item, dict) and str(item.get("id", "")) == project_id:
                # Older browser code may equate package validation with 100%
                # business validity. Do not let it erase the server's boundary.
                if item.get("business_status") == "incomplete" and quality.get("overall_status") == "通过":
                    quality = item.get("quality") or {"overall_status": "阻断"}
                if item.get("delivery_mode") == "public_draft":
                    quality = item.get("quality") or {"overall_status": "草稿验收通过", "formal_delivery_allowed": False}
                item["quality"] = quality
                item["quality_status"] = str(quality.get("overall_status", "")) or item.get("quality_status", "已生成")
                updated = item
                break
        if updated is None:
            return None
        temp_path = PROJECT_RUNS_FILE.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(PROJECT_RUNS_FILE)
        return updated


def delete_project_run(project_id: str) -> dict[str, Any] | None:
    """删除项目台账记录；运行中的任务必须先结束或取消。"""

    with PROJECT_RUNS_LOCK:
        if not PROJECT_RUNS_FILE.is_file():
            return None
        try:
            payload = json.loads(PROJECT_RUNS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, list):
            return None

        deleted = next(
            (
                item
                for item in payload
                if isinstance(item, dict) and str(item.get("id", "")) == project_id
            ),
            None,
        )
        if deleted is None:
            return None
        if str(deleted.get("status", "")).strip() == "执行中":
            raise ValueError("任务仍在执行，请先取消或等待任务结束后再删除。")

        remaining = [
            item
            for item in payload
            if not (isinstance(item, dict) and str(item.get("id", "")) == project_id)
        ]
        temp_path = PROJECT_RUNS_FILE.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(PROJECT_RUNS_FILE)
        return deleted


def store_latest_agent_run(result: dict[str, Any], question: str, analysis_type: str) -> None:
    """保存最近一次运行的非敏感审计摘要，便于前端和联调排障。

    不记录 API Key、完整系统提示词或模型内部思考过程；报告仅保留短前览，完整正文仍
    由本轮 /api/chat 响应返回给调用方。
    """

    answer = str(result.get("answer", ""))
    audit = {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "agent": result.get("agent", ""),
        "analysis_type": analysis_type or "自动识别",
        "question": question[:500],
        "answer_length": len(answer),
        "answer_preview": answer[:1200],
        "tool_events": result.get("tool_events", []),
        "skill": result.get("skill"),
    }
    with LATEST_AGENT_RUN_LOCK:
        LATEST_AGENT_RUN.clear()
        LATEST_AGENT_RUN.update(audit)


def generate_ppt_from_markdown(
    markdown: str,
    title: str,
    analysis_type: str = "",
    dataset_path: str | Path | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """生成独立 HTML PPT。

    优先使用项目内 consulting-html-ppt-generator 生成咨询风 deck；如果本地生成器异常，
    再回退到原 html-report-generator，保证前端按钮可用。
    """
    PPT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = safe_filename(title) + "_" + stamp
    markdown_path = PPT_OUTPUT_DIR / (base_name + ".md")
    markdown_path.write_text(markdown, encoding="utf-8")

    if analysis_type == "market_monthly_report":
        skill_context = MarketAnalysisSkill(load_json_config()).prepare(
            "生成乘用车市场月度报告",
            analysis_type,
            dataset_path,
            sheet_name,
        )
        if skill_context.dataset_path is None:
            raise RuntimeError("月报 Skill 未找到可用验数数据集，无法生成可编辑 PPTX。")
        pptx_path = PPT_OUTPUT_DIR / (base_name + ".pptx")
        result = build_monthly_report_pptx(
            markdown,
            pptx_path,
            skill_context.dataset_path,
            sheet_name=skill_context.selected_sheet or sheet_name,
        )
        result["markdown_path"] = str(markdown_path.relative_to(PROJECT_DIR)).replace("\\", "/")
        result["pptx_url"] = "/" + str(pptx_path.relative_to(PROJECT_DIR)).replace("\\", "/")
        result["input_gate"] = skill_context.input_gate()
        return result

    html_path = PPT_OUTPUT_DIR / (base_name + ".html")

    try:
        result = build_consulting_html_ppt(markdown, title, html_path, PROJECT_DIR)
        result["markdown_path"] = str(markdown_path.relative_to(PROJECT_DIR)).replace("\\", "/")
        result["html_url"] = "/" + str(html_path.relative_to(PROJECT_DIR)).replace("\\", "/")
        return result
    except Exception as exc:
        if not HTML_REPORT_SKILL_RUNNER.is_file():
            raise RuntimeError("咨询风 HTML PPT 生成失败，且未找到兜底执行器：" + str(exc)) from exc

    completed = subprocess.run(
        [sys.executable, str(HTML_REPORT_SKILL_RUNNER), str(markdown_path), str(html_path)],
        cwd=str(HTML_REPORT_SKILL_RUNNER.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    raw = (completed.stdout or "").strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("html-report-generator 返回非 JSON 内容：" + raw[:500] + "；stderr=" + (completed.stderr or ""))

    if completed.returncode != 0 or not result.get("success"):
        raise RuntimeError(result.get("error") or "HTML PPT 生成失败")

    html = html_path.read_text(encoding="utf-8", errors="ignore")
    html = html.replace('class="slide active"', 'class="slide"', 1)
    html_path.write_text(html, encoding="utf-8")
    result["markdown_path"] = str(markdown_path.relative_to(PROJECT_DIR)).replace("\\", "/")
    result["html_url"] = "/" + str(html_path.relative_to(PROJECT_DIR)).replace("\\", "/")
    result["file_size"] = html_path.stat().st_size
    result["engine"] = "html-report-generator-fallback"
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest_passenger_monthly_package_path() -> Path:
    """Resolve the package produced by the latest exact monthly-report run."""

    with LATEST_AGENT_RUN_LOCK:
        source_package = (
            LATEST_AGENT_RUN.get("skill", {}).get("source_package", {})
            if isinstance(LATEST_AGENT_RUN.get("skill"), dict)
            else {}
        )
        raw_path = str(source_package.get("snapshot_path", "")).strip()
    if not raw_path:
        raise RuntimeError("尚未找到本轮标准化月报数据包，请先点击“开始分析”。")
    path = Path(raw_path).resolve()
    if path.parent != PASSENGER_MONTHLY_PACKAGE_DIR or not path.is_file():
        raise RuntimeError("本轮月报数据包路径无效，请重新执行数据源采集。")
    return path


def generate_passenger_monthly_pptx(run_id: str, title: str) -> dict[str, Any]:
    """Write the validated page narratives from one exact run into the PPT template."""

    job = MONTHLY_REPORT_JOBS.get(run_id)
    if not job:
        raise RuntimeError("未找到对应的月报任务，请重新执行月报分析。")
    if job.get("status") != "completed":
        raise RuntimeError("本轮月报尚未完成主旨句生成，暂不能生成PPT。")
    checkpoints = job.get("checkpoints", {})
    collection = checkpoints.get("data_collect", {})
    preflight = checkpoints.get("preflight", {})
    raw_package_path = collection.get("snapshot_path")
    recovering_package_path = raw_package_path is None or (
        isinstance(raw_package_path, str) and not raw_package_path.strip())
    if recovering_package_path:
        # Older saved JSON omitted its own path. Recover only the package this
        # exact run explicitly reused; never scan recent files or other jobs.
        if preflight.get("snapshot_reused") is not True or not preflight.get("report_month"):
            raise RuntimeError("本轮数据包路径缺失，且没有可核验的同轮复用记录；已保留数据和观点。")
        raw_package_path = preflight.get("data_package_path")

    def checkpoint_path(value: Any, label: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"本轮{label}检查点路径缺失或格式无效；已保留数据和观点。")
        path = Path(value.strip()).resolve()
        try:
            path.relative_to(PASSENGER_MONTHLY_PACKAGE_DIR.resolve())
        except ValueError as exc:
            raise RuntimeError(f"本轮{label}检查点路径超出月报目录；已停止导出。") from exc
        if not path.is_file():
            raise RuntimeError(f"本轮{label}检查点文件不存在；已保留其他检查点。")
        return path

    package_path = checkpoint_path(raw_package_path, "数据包")
    narrative_path = checkpoint_path(checkpoints.get("narrative", {}).get("path"), "主旨句")
    current_package_sha256 = _sha256_file(package_path) if package_path.is_file() else ""
    current_narrative_sha256 = _sha256_file(narrative_path) if narrative_path.is_file() else ""
    current_template_sha256 = _sha256_file(PASSENGER_MONTHLY_TEMPLATE_PATH) if PASSENGER_MONTHLY_TEMPLATE_PATH.is_file() else ""
    renderer_files = ('monthly_report_narrative.py', 'monthly_ppt_layout.py', 'monthly_source_pptx.py', 'monthly_source_rankings.py',
                      'monthly_page_facts.py', 'monthly_page_narratives.py', 'monthly_segment_facts.py')
    supplement_path = PASSENGER_MONTHLY_PACKAGE_DIR / run_id / 'ppt-data-supplement.json'
    current_supplement_sha256 = _sha256_file(supplement_path) if supplement_path.is_file() else ''
    current_renderer_sha256 = hashlib.sha256((''.join(
        _sha256_file(PROJECT_DIR / 'utils' / name) for name in renderer_files
    ) + current_supplement_sha256).encode('ascii')).hexdigest()
    prior_output = checkpoints.get("ppt_update", {})
    prior_path = Path(str(prior_output.get("output_path", ""))).resolve()
    prior_matches_inputs = (
        str(prior_output.get("source_package_sha256", "")) == current_package_sha256
        and str(prior_output.get("narrative_package_sha256", "")) == current_narrative_sha256
        and str(prior_output.get("template_sha256", "")) == current_template_sha256
        and str(prior_output.get("renderer_sha256", "")) == current_renderer_sha256
    )
    if prior_output and prior_matches_inputs and prior_path.is_file() and not recovering_package_path:
        try:
            prior_path.relative_to(PPT_OUTPUT_DIR.resolve())
        except ValueError:
            pass
        else:
            return {
                "success": True,
                "pptx_url": "/" + str(prior_path.relative_to(PROJECT_DIR)).replace("\\", "/"),
                "manifest_url": str(prior_output.get("manifest_url", "")),
                "report_month": prior_output.get("report_month", ""),
                "cards_usable": prior_output.get("cards_usable", 0),
                "cards_expected": prior_output.get("cards_expected", 45),
                "run_id": run_id,
                "headline_count": prior_output.get("headline_count", 0),
                "message": "已返回本轮任务之前生成并校验通过的PPT。",
            }
    package = json.loads(package_path.read_text(encoding="utf-8"))
    narrative = json.loads(narrative_path.read_text(encoding="utf-8"))
    if narrative.get("run_id") != run_id:
        raise RuntimeError("主旨句证据包与本轮任务不一致，已停止生成PPT。")
    expected = int(package.get("cards_expected", 45) or 45)
    usable = int(package.get("cards_usable", 0) or 0)
    report_month = str(package.get("report_month", "")).strip()
    if not package.get("generation_ready") or usable != expected or expected != 45:
        raise RuntimeError(f"标准化月报数据包不完整：可用 {usable}/{expected} 张卡片。")
    bound_months = (job.get("report_month"), job.get("payload", {}).get("report_month"),
                    collection.get("report_month"), preflight.get("report_month"))
    if any(month and month != report_month for month in bound_months):
        raise RuntimeError("数据包月份与本轮已锁定月份不一致，已停止生成PPT。")
    cards = package.get("cards", [])
    expected_codes = set(_page_card_codes())
    actual_codes = [card.get("code") for card in cards if isinstance(card, dict)] if isinstance(cards, list) else []
    diagnostics = MonthlyReportBrowserConnector._card_diagnostics(
        {str(card.get('code', '')): str(card.get('text', '')) for card in cards if isinstance(card, dict)}
        if isinstance(cards, list) else {}, report_month)
    if (len(actual_codes) != len(expected_codes) or set(actual_codes) != expected_codes
            or any(not _card_has_current_period(card['code'], str(card.get('text', '')), report_month)
                   and diagnostics[card['code']]['status'] != 'delayed_allowed' for card in cards)):
        raise RuntimeError("标准化月报数据包的45张卡片存在缺失、重复或月份校验失败，已停止生成PPT。")
    bound_hash = collection.get("source_package_sha256") or preflight.get("source_package_sha256")
    if bound_hash and bound_hash != current_package_sha256:
        raise RuntimeError("数据包内容与本轮检查点记录不一致，已停止生成PPT。")
    if not PASSENGER_MONTHLY_TEMPLATE_PATH.is_file():
        raise RuntimeError("未找到最新版乘用车月报兼容模板。")

    # The saved exact run must pass the current entity/scope/format gates at
    # release time as well. This is local: never recollects browser cards.
    validate_narrative_package(narrative, package, run_id=run_id,
                               mapping_path=PASSENGER_MONTHLY_MAPPING_PATH,
                               examples_path=PASSENGER_MONTHLY_EXAMPLES_PATH)

    if recovering_package_path:
        MONTHLY_REPORT_JOBS.save_output_checkpoint(run_id, "data_collect", {
            **collection,
            "snapshot_path": str(package_path),
            "source_package_sha256": current_package_sha256,
            "path_recovery": {
                "from": "preflight.data_package_path", "run_id": run_id,
                "report_month": report_month,
                "narrative_package_sha256": current_narrative_sha256,
                "validated_at": datetime.now().isoformat(timespec="seconds"),
            },
        })

    PPT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    month_label = f"{report_month[:4]}年{int(report_month[-2:])}月"
    base_name = safe_filename(f"{month_label}中国乘用车市场月度分析报告_AI生成版_{stamp}")
    output_path = PPT_OUTPUT_DIR / f"{base_name}.pptx"
    temp_path = PPT_OUTPUT_DIR / f".{uuid4().hex}.pptx"
    from utils.monthly_source_pptx import update_source_template, template_period, load_ppt_supplement
    data_template_path = PPT_OUTPUT_DIR / f".{uuid4().hex}.data.pptx"
    data_update = {'template_period': template_period(PASSENGER_MONTHLY_TEMPLATE_PATH), 'report_month':report_month,
                   'status':'accepted_template_period'}
    try:
        template_for_write = PASSENGER_MONTHLY_TEMPLATE_PATH
        if report_month != data_update['template_period']:
            ppt_package = load_ppt_supplement(package_path, supplement_path)
            data_update = update_source_template(PASSENGER_MONTHLY_TEMPLATE_PATH, data_template_path, ppt_package, PASSENGER_MONTHLY_MAPPING_PATH)
            template_for_write = data_template_path
        write_result = apply_narratives_to_ppt(template_for_write, temp_path, narrative)
    finally:
        data_template_path.unlink(missing_ok=True)
    temp_path.replace(output_path)

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_month": report_month,
        "cards_expected": expected,
        "cards_usable": usable,
        "source_package": str(package_path),
        "source_package_sha256": _sha256_file(package_path),
        "narrative_package": str(narrative_path),
        "narrative_package_sha256": _sha256_file(narrative_path),
        "run_id": run_id,
        "slides_written": write_result.get("slides_written", []),
        "retained_pages": write_result.get("retained_pages", []),
        "data_update": data_update,
        "source_grid_supplement": str(supplement_path) if supplement_path.is_file() else '',
        "source_grid_sha256": current_supplement_sha256,
        "headline_count": write_result.get("headline_count", 0),
        "template": str(PASSENGER_MONTHLY_TEMPLATE_PATH),
        "template_sha256": _sha256_file(PASSENGER_MONTHLY_TEMPLATE_PATH),
        "renderer_sha256": current_renderer_sha256,
        "output_sha256": _sha256_file(output_path),
        "legacy_excel_disabled": True,
        "release_mode": "run_scoped_monthly_data_and_narrative_update",
        "requested_title": title,
    }
    manifest_path = output_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_url = "/" + str(manifest_path.relative_to(PROJECT_DIR)).replace("\\", "/")
    MONTHLY_REPORT_JOBS.save_output_checkpoint(run_id, "ppt_update", {
        "output_path": str(output_path),
        "manifest_url": manifest_url,
        "report_month": report_month,
        "cards_usable": usable,
        "cards_expected": expected,
        "headline_count": write_result.get("headline_count", 0),
        "output_sha256": manifest["output_sha256"],
        "source_package_sha256": manifest["source_package_sha256"],
        "narrative_package_sha256": manifest["narrative_package_sha256"],
        "template_sha256": manifest["template_sha256"],
        "renderer_sha256": manifest["renderer_sha256"],
    })
    record_tool_call(
        "passenger_monthly_ppt_release",
        "success",
        f"report_month={report_month}; cards={usable}/{expected}; file={output_path.name}",
    )
    return {
        "success": True,
        "pptx_url": "/" + str(output_path.relative_to(PROJECT_DIR)).replace("\\", "/"),
        "manifest_url": manifest_url,
        "report_month": report_month,
        "cards_usable": usable,
        "cards_expected": expected,
        "run_id": run_id,
        "headline_count": write_result.get("headline_count", 0),
        "message": "已生成可编辑月报PPTX，目标月份数据与主旨句已核验，滞后页保留原样。",
    }


def monthly_report_check_score(checks: list[Any]) -> tuple[int, int, int]:
    """比较首稿与重写稿，避免不完整的重写结果覆盖更好的首稿。"""

    weight = {"通过": 3, "待补充": 1, "风险": -3, "阻断": -6}
    return (
        sum(weight.get(getattr(item, "status", ""), -2) for item in checks),
        sum(getattr(item, "status", "") == "通过" for item in checks),
        -sum(getattr(item, "status", "") in {"风险", "阻断"} for item in checks),
    )


def build_data_source_anomaly_report(package: dict[str, Any]) -> str:
    """Render the deterministic source gate result without asking the LLM.

    This response intentionally contains only observations from the current
    browser run.  It must never merge the legacy Excel monthly-report context.
    """

    code = str(package.get("code", "data_package_incomplete"))
    expected = int(package.get("cards_expected") or package.get("mapping_cards_expected") or 45)
    captured = int(package.get("cards_captured") or package.get("mapping_cards_matched") or 0)
    usable = int(package.get("cards_usable") or 0)
    missing = [str(item) for item in package.get("missing_cards", [])]
    unusable = [str(item) for item in package.get("unusable_cards", [])]
    stale = [str(item) for item in package.get("stale_cards", [])]

    lines = [
        "# 乘用车月报数据源检查未通过",
        "",
        "本次停止在数据校验阶段，未生成各页主旨句或 PPT，不会读取旧版月报 Excel。",
        "",
        f"- 检查状态：{code}",
        f"- 页面卡片：已识别 {captured}/{expected} 张，可用 {usable}/{expected} 张",
        f"- 当前报告月份：{package.get('report_month') or '尚未可靠识别'}",
        f"- 说明：{package.get('message') or '数据包未达到正式生成条件。'}",
    ]
    if missing:
        lines.extend(["", "## 未读取到的卡片", "", "、".join(missing)])
    if unusable:
        lines.extend(["", "## 已识别但未通过当期完整性校验的卡片", "", "、".join(unusable)])
        validation = package.get("card_validation", {})
        if isinstance(validation, list):
            validation = {str(item.get("code", "")): item for item in validation if isinstance(item, dict)}
        if isinstance(validation, dict) and validation:
            lines.extend(["", "| 卡片 | 目标月份 | 已读取的最新月份 | 未通过原因 |", "| --- | --- | --- | --- |"])
            for card_code in unusable:
                item = validation.get(card_code, {})
                if not isinstance(item, dict):
                    continue
                latest = item.get("latest_period") or item.get("latest_month") or "未确认"
                reason = str(item.get("message") or item.get("reason") or item.get("status") or "未记录详细原因")
                lines.append(f"| {card_code} | {package.get('report_month') or '未确认'} | {latest} | {reason.replace('|', '/')} |")
    if stale:
        lines.extend(["", "## 标记为未更新的卡片", "", "、".join(stale)])
    lines.extend(
        [
            "",
            "## 后续动作",
            "",
            "已保留本次数据与诊断。请先核对目标月份及上表的具体原因；页面中存在卡片不代表其已发布目标月份数据。"
            "同月已有完整数据包直接复用，部分缺失时只补采未通过项；月份未确认时停止采集，等待月份条件明确后恢复原任务。",
        ],
    )
    return "\n".join(lines)


def passenger_monthly_skill_response(package: dict[str, Any], *, output_gate: str) -> dict[str, Any]:
    """Build the new source-to-PPT skill audit payload."""

    return {
        "active": True,
        "name": "passenger-car-monthly-report",
        "display_name": "乘用车月报智能生成",
        "analysis_type": "passenger_car_monthly_report",
        "legacy_excel_disabled": True,
        "source_package": {
            "code": package.get("code", ""),
            "report_month": package.get("report_month", ""),
            "cards_expected": package.get("cards_expected", package.get("mapping_cards_expected", 45)),
            "cards_captured": package.get("cards_captured", package.get("mapping_cards_matched", 0)),
            "cards_usable": package.get("cards_usable", 0),
            "snapshot_path": package.get("snapshot_path", ""),
            "collection_mode": package.get("collection_mode", "reuse" if package.get("snapshot_reused") else "collect"),
            "snapshot_reused": bool(package.get("snapshot_reused")),
            "cards_reused": package.get("cards_reused", package.get("cards_expected", 45) if package.get("snapshot_reused") else 0),
            "cards_collected": package.get("cards_collected", 0),
            "reuse_decision": package.get("reuse_decision", {}),
            "delayed_cards": package.get("delayed_cards", []),
            "card_validation": package.get("card_validation", {}),
        },
        "input_gate": "通过" if package.get("generation_ready") else "阻断",
        "output_gate": output_gate,
        "pipeline": [
            "数据源采集",
            "标准化月报数据包",
            "多源交叉校验",
            "市场分析与主旨句生成",
            "确定性PPT更新",
            "输出校验与交付",
        ],
    }


def build_passenger_monthly_run_result(
    package: dict[str, Any],
    model_provider: str,
    narrative: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the deterministic monthly result from a persisted data package."""

    tool_name = "monthly_report_reuse_data_package" if package.get("snapshot_reused") else "monthly_report_read_all_cards"
    if not package.get("generation_ready"):
        return {
            "answer": build_data_source_anomaly_report(package),
            "agent": "market_strategy",
            "model_provider": model_provider,
            "tool_events": [
                {
                    "name": tool_name,
                    "status": "blocked",
                    "detail": (
                        f"report_month={package.get('report_month', '')}; "
                        f"mode={package.get('collection_mode', 'reuse' if package.get('snapshot_reused') else 'collect')}; "
                        f"code={package.get('code', '')}; "
                        f"usable={package.get('cards_usable', 0)}/"
                        f"{package.get('cards_expected', package.get('mapping_cards_expected', 45))}"
                    ),
                },
            ],
            "skill": passenger_monthly_skill_response(package, output_gate="数据源门禁阻断"),
        }

    answer = narrative_markdown(narrative) if narrative else (
        "# 乘用车月报数据准备完成\n\n"
        f"已形成 {package.get('cards_usable', 0)}/{package.get('cards_expected', 45)} 张卡片的"
        f"标准化月报数据包，报告月份为 {package.get('report_month', '未识别')}。"
        "主旨句证据包尚未生成，不能进入正式PPT更新。"
    )
    skill_response = passenger_monthly_skill_response(
        package,
        output_gate="通过" if narrative else "等待主旨句门禁",
    )
    if narrative:
        skill_response["narrative_evidence"] = {
            "path": narrative.get("path", ""),
            "slides": len(narrative.get("slides", [])),
            "evidence": len(narrative.get("evidence", [])),
        }
    return {
        "answer": answer,
        "agent": "market_strategy",
        "model_provider": model_provider,
        "tool_events": [
            {
                "name": tool_name,
                "status": "success",
                "detail": (
                    f"report_month={package.get('report_month', '')}; "
                        f"mode={package.get('collection_mode', 'reuse' if package.get('snapshot_reused') else 'collect')}; "
                        f"code={package.get('code', '')}; "
                    f"usable={package.get('cards_usable', 0)}/"
                    f"{package.get('cards_expected', 45)}"
                ),
            },
        ],
        "skill": skill_response,
    }


class MonthlyJobCancelled(RuntimeError):
    """Internal cooperative cancellation signal for a monthly-report job."""


class MonthlyReportJobManager:
    """Durable background runner for the passenger-car monthly workflow."""

    TERMINAL_STATUSES = {"completed", "failed", "cancelled", "input_required"}

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._worker_lock = Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancel_events: dict[str, Event] = {}
        self._threads: dict[str, Thread] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        for path in self.root.glob("month-*.json"):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
                run_id = str(state.get("run_id", ""))
                if run_id:
                    self._jobs[run_id] = state
            except (OSError, ValueError, TypeError):
                continue

    def _path(self, run_id: str) -> Path:
        return self.root / f"{run_id}.json"

    def _write_locked(self, state: dict[str, Any]) -> None:
        path = self._path(str(state["run_id"]))
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def _event_locked(
        self,
        state: dict[str, Any],
        phase: str,
        status: str,
        message: str,
        progress: int,
    ) -> None:
        events = state.setdefault("events", [])
        seq = int(events[-1].get("seq", 0)) + 1 if events else 1
        now = datetime.now().isoformat(timespec="seconds")
        events.append({
            "seq": seq,
            "at": now,
            "phase": phase,
            "status": status,
            "message": message,
            "progress": progress,
        })
        state.update({
            "phase": phase,
            "status": status if status in self.TERMINAL_STATUSES else "running",
            "message": message,
            "progress": progress,
            "updated_at": now,
            "heartbeat_at": now,
        })

    def _update(
        self,
        run_id: str,
        phase: str,
        status: str,
        message: str,
        progress: int,
        **values: Any,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._jobs[run_id]
            self._event_locked(state, phase, status, message, progress)
            state.update(values)
            self._write_locked(state)
            return deepcopy(state)

    def _save_checkpoint(
        self,
        run_id: str,
        phase: str,
        checkpoint: dict[str, Any],
        *,
        completed: bool = True,
    ) -> None:
        with self._lock:
            state = self._jobs[run_id]
            completed_phases = state.setdefault("completed_phases", [])
            if completed and phase not in completed_phases:
                completed_phases.append(phase)
            elif not completed and phase in completed_phases:
                completed_phases.remove(phase)
            state.setdefault("checkpoints", {})[phase] = checkpoint
            state["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._write_locked(state)

    def save_output_checkpoint(self, run_id: str, phase: str, checkpoint: dict[str, Any]) -> None:
        """Persist an idempotent post-analysis artifact against the original run."""

        self._save_checkpoint(run_id, phase, checkpoint)

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now()
        run_id = f"month-{now.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        requested_month = str(payload.get("report_month") or "").strip()
        if requested_month and not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", requested_month):
            raise ValueError("报告月份必须为 YYYY-MM，例如 2026-08。")
        safe_payload = {
            "report_month": requested_month,
            "force_refresh": payload.get("force_refresh") is True,
            "question": str(payload.get("question", "")).strip(),
            "analysis_type": "passenger_car_monthly_report",
            "model_provider": str(payload.get("model_provider", "minimax")).strip() or "minimax",
            "capabilities": [str(item) for item in payload.get("capabilities", [])],
            "mcp_plugins": [str(item) for item in payload.get("mcp_plugins", [])],
        }
        state = {
            "version": 1,
            "run_id": run_id,
            "kind": "passenger_car_monthly_report",
            "status": "queued",
            "phase": "queued",
            "progress": 0,
            "message": "月报任务已入队。",
            "created_at": now.isoformat(timespec="seconds"),
            "updated_at": now.isoformat(timespec="seconds"),
            "heartbeat_at": now.isoformat(timespec="seconds"),
            "payload": safe_payload,
            "events": [],
            "completed_phases": [],
            "checkpoints": {},
            "result": None,
            "error": None,
            "recoverable": True,
        }
        with self._lock:
            self._event_locked(state, "queued", "queued", "月报任务已入队，等待后台执行。", 2)
            self._jobs[run_id] = state
            self._cancel_events[run_id] = Event()
            self._write_locked(state)
        self._spawn(run_id)
        return self.get(run_id) or {}

    def _spawn(self, run_id: str) -> None:
        with self._lock:
            existing = self._threads.get(run_id)
            if existing and existing.is_alive():
                return
            thread = Thread(
                target=self._run,
                args=(run_id,),
                name=f"monthly-job-{run_id[-8:]}",
                daemon=True,
            )
            self._threads[run_id] = thread
            thread.start()

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._jobs.get(run_id)
            return deepcopy(state) if state else None

    def cancel(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._jobs.get(run_id)
            if state is None:
                return None
            if state.get("status") in self.TERMINAL_STATUSES:
                return deepcopy(state)
            cancel_event = self._cancel_events.setdefault(run_id, Event())
            cancel_event.set()
            current_progress = int(state.get("progress", 0))
        return self._update(run_id, "cancel", "running", "已提交取消请求，正在停止当前读取步骤。", current_progress)

    def resume(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._jobs.get(run_id)
            if state is None:
                return None
            if state.get("status") == "completed":
                return deepcopy(state)
            state["status"] = "queued"
            state["error"] = None
            state["recoverable"] = True
            self._cancel_events[run_id] = Event()
            self._event_locked(state, "resume", "queued", "已从最近检查点恢复月报任务。", int(state.get("progress", 2)))
            self._write_locked(state)
        self._spawn(run_id)
        return self.get(run_id)

    def recover_pending(self) -> None:
        with self._lock:
            pending = [
                run_id
                for run_id, state in self._jobs.items()
                if state.get("status") in {"queued", "running"}
            ]
            for run_id in pending:
                self._cancel_events[run_id] = Event()
                state = self._jobs[run_id]
                state["status"] = "queued"
                self._event_locked(
                    state,
                    "resume",
                    "queued",
                    "服务重启后已恢复未完成月报任务。",
                    int(state.get("progress", 2)),
                )
                self._write_locked(state)
        for run_id in pending:
            self._spawn(run_id)

    def _is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            return self._cancel_events.setdefault(run_id, Event()).is_set()

    def _run_async_step(
        self,
        run_id: str,
        phase: str,
        progress: int,
        description: str,
        coroutine_factory: Any,
        max_attempts: int = 2,
        reset_browser_on_retry: bool = False,
    ) -> Any:
        for attempt in range(1, max_attempts + 1):
            if self._is_cancelled(run_id):
                raise MonthlyJobCancelled("用户取消了月报任务。")
            self._update(
                run_id,
                phase,
                "running",
                description if attempt == 1 else f"{description}（第 {attempt} 次尝试）",
                progress,
            )
            future = AGENT_LOOP_RUNNER.submit(coroutine_factory())
            last_heartbeat = time.monotonic()
            while not future.done():
                if self._is_cancelled(run_id):
                    future.cancel()
                    raise MonthlyJobCancelled("用户取消了月报任务。")
                if time.monotonic() - last_heartbeat >= 15:
                    latest = self.get(run_id) or {}
                    latest_message = str(latest.get("message") or description)
                    heartbeat_suffix = "；后台仍在处理，任务连接正常。"
                    if latest_message.endswith(heartbeat_suffix):
                        latest_message = latest_message[:-len(heartbeat_suffix)]
                    self._update(
                        run_id,
                        phase,
                        "running",
                        latest_message + heartbeat_suffix,
                        max(progress, int(latest.get("progress", progress))),
                    )
                    last_heartbeat = time.monotonic()
                time.sleep(0.5)
            try:
                return future.result()
            except Exception:
                if attempt >= max_attempts:
                    raise
                self._update(
                    run_id,
                    phase,
                    "running",
                    (
                        f"{description}本次未完成，已保留月报专用浏览器登录会话并准备重试。"
                        if not reset_browser_on_retry
                        else f"{description}本次未完成，已重建连接并准备重试。"
                    ),
                    progress,
                )
                if reset_browser_on_retry:
                    try:
                        AGENT_LOOP_RUNNER.run(MONTHLY_REPORT_BROWSER.close())
                    except Exception:
                        pass
                time.sleep(2)
        raise RuntimeError("月报后台步骤未完成。")

    @staticmethod
    def _load_package(path_value: str) -> dict[str, Any] | None:
        if not path_value:
            return None
        try:
            path = Path(path_value).resolve()
            allowed = (PROJECT_DIR / "outputs" / "monthly-report-data").resolve()
            path.relative_to(allowed)
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                return None
            if isinstance(value.get("cards"), list):
                # The file actually read is authoritative, including legacy
                # packages without a self-path or moved/copied packages.
                value["snapshot_path"] = str(path)
            return value
        except (OSError, ValueError, TypeError):
            return None

    def _run(self, run_id: str) -> None:
        with self._worker_lock:
            try:
                state = self.get(run_id)
                if state is None:
                    return
                payload = state.get("payload", {})
                completed = set(state.get("completed_phases", []))
                checkpoints = state.get("checkpoints", {})
                self._update(run_id, "start", "running", "后台月报任务已启动。", 5)

                # Accepted data is a durable business checkpoint. Validate it
                # before touching Chrome; research/export do not need BI login.
                package = None
                if "data_collect" in completed and not payload.get("force_refresh"):
                    package = self._load_package(str(checkpoints.get("data_collect", {}).get("snapshot_path", "")))
                    target_month = str(payload.get("report_month") or checkpoints.get("data_collect", {}).get("report_month") or (package or {}).get("report_month", ""))
                    if package is not None and not MONTHLY_REPORT_BROWSER.ready_package_for_month(package, target_month):
                        package = None
                if package is not None:
                    preflight = MONTHLY_REPORT_BROWSER.package_preflight(package, target_month)
                else:
                    preflight = self._run_async_step(
                        run_id,
                        "preflight",
                        15,
                        "正在校验目标月份与已采集数据包；缺失数据时才连接浏览器",
                        lambda: MONTHLY_REPORT_BROWSER.preflight(
                            open_page=True,
                            report_month=str(payload.get("report_month", "")),
                            force_refresh=bool(payload.get("force_refresh")),
                        ),
                    )
                self._save_checkpoint(
                    run_id,
                    "preflight",
                    {
                        "code": preflight.get("code", ""),
                        "page_ready": bool(preflight.get("page_ready")),
                        "browser_required": preflight.get("browser_required", True),
                        "auth_session_state": preflight.get("auth_session_state", ""),
                        "snapshot_path": preflight.get("snapshot_path", ""),
                        "data_package_path": preflight.get("data_package_path", ""),
                        "preflight_snapshot_path": preflight.get("preflight_snapshot_path", ""),
                        "report_month": preflight.get("report_month", ""),
                        "snapshot_reused": bool(preflight.get("snapshot_reused")),
                        "month_confirmation": preflight.get("month_confirmation", {}),
                        "reuse_decision": preflight.get("reuse_decision", {}),
                        "collection_mode": preflight.get("collection_mode", ""),
                        "cards_reused": preflight.get("cards_reused", 0),
                        "cards_to_collect": preflight.get("cards_to_collect", 0),
                    },
                    completed=bool(preflight.get("page_ready")),
                )
                if not preflight.get("page_ready"):
                    self._update(
                        run_id,
                        "preflight",
                        "input_required",
                        str(preflight.get("message") or "请完成数据源登录和页面加载后恢复任务。"),
                        15,
                        result={"preflight": preflight},
                    )
                    return

                locked_month = str(preflight.get("report_month", ""))
                requested_month = str(payload.get("report_month", ""))
                if not locked_month or (requested_month and requested_month != locked_month):
                    self._update(run_id, "preflight", "input_required",
                                 "报告月份尚未确认或与指定月份不一致，已停止采集。", 15,
                                 result={"preflight": preflight}, recoverable=True)
                    return
                reuse_decision = preflight.get("reuse_decision", {})
                mode = preflight.get("collection_mode") or ("reuse" if preflight.get("snapshot_reused") else "collect")
                mode_label = {"reuse": "复用已有数据", "partial_collect": "只补采缺失卡片",
                              "collect": "采集当前月份数据", "force_refresh": "按明确要求刷新数据"}.get(mode, str(mode))
                reason = str(reuse_decision.get("message") or reuse_decision.get("reason") or "") if isinstance(reuse_decision, dict) else str(reuse_decision)
                self._update(run_id, "preflight", "running",
                             f"报告月份：{locked_month}；处理方式：{mode_label}。" + reason, 20,
                             report_month=locked_month, collection_mode=mode,
                             reuse_decision=reuse_decision,
                             cards_reused=int(preflight.get("cards_reused", 0)),
                             cards_to_collect=int(preflight.get("cards_to_collect", 0)))
                if package is None and "data_collect" in completed and not payload.get("force_refresh"):
                    package = self._load_package(str(checkpoints.get("data_collect", {}).get("snapshot_path", "")))
                    if package is not None and str(package.get("report_month", "")) != str(preflight.get("report_month", "")):
                        self._update(
                            run_id, "preflight", "input_required",
                            f"当前BI月份为 {preflight.get('report_month') or '未确认'}，与本任务已采集月份 {package.get('report_month')} 不一致。请切回原任务月份后恢复；已完成数据与主旨句保留，不会跨月份复用。",
                            15, result={"preflight": preflight},
                        )
                        return
                    if package is not None and not MONTHLY_REPORT_BROWSER.ready_package_for_month(package, str(preflight.get("report_month", ""))):
                        package = None
                if package is None and preflight.get("snapshot_reused"):
                    package = self._load_package(str(preflight.get("data_package_path") or preflight.get("snapshot_path", "")))
                    if package is not None and not MONTHLY_REPORT_BROWSER.ready_package_for_month(package, str(preflight.get("report_month", ""))):
                        package = None
                    if package is not None:
                        package["snapshot_reused"] = True
                        package["snapshot_reuse_reason"] = "same_report_month_verified"
                        package["collection_mode"] = "reuse"
                        package["cards_reused"] = package.get("cards_expected", 45)
                        package["cards_collected"] = 0
                        self._update(
                            run_id,
                            "data_collect",
                            "running",
                            (
                                f"已复用 {package.get('report_month', '同月份')} 历史任务的45/45标准化数据包，"
                                "跳过45张卡片重复读取。"
                            ),
                            45,
                        )
                if package is None:
                    package = self._run_async_step(
                        run_id,
                        "data_collect",
                        45,
                        f"报告月份：{locked_month}；{mode_label}，保存标准化数据包",
                        lambda: MONTHLY_REPORT_BROWSER.read_all_cards(
                            report_month=locked_month,
                            force_refresh=bool(payload.get("force_refresh")),
                        ),
                    )
                    self._save_checkpoint(run_id, "data_collect", {
                        "snapshot_path": package.get("snapshot_path", ""),
                        "report_month": package.get("report_month", ""),
                        "cards_expected": package.get("cards_expected", 45),
                        "cards_usable": package.get("cards_usable", 0),
                        "generation_ready": bool(package.get("generation_ready")),
                        "snapshot_reused": bool(package.get("snapshot_reused")),
                        "snapshot_reuse_reason": package.get("snapshot_reuse_reason", ""),
                        "collection_mode": package.get("collection_mode", mode),
                        "cards_reused": package.get("cards_reused", 0),
                        "cards_collected": package.get("cards_collected", 0),
                        "reuse_decision": package.get("reuse_decision", reuse_decision),
                    })
                elif "data_collect" not in completed:
                    self._save_checkpoint(run_id, "data_collect", {
                        "snapshot_path": package.get("snapshot_path", ""),
                        "report_month": package.get("report_month", ""),
                        "cards_expected": package.get("cards_expected", 45),
                        "cards_usable": package.get("cards_usable", 0),
                        "generation_ready": bool(package.get("generation_ready")),
                        "snapshot_reused": True,
                        "snapshot_reuse_reason": "same_report_month_verified",
                        "collection_mode": "reuse",
                        "cards_reused": package.get("cards_expected", 45),
                        "cards_collected": 0,
                        "reuse_decision": reuse_decision,
                    })
                else:
                    self._update(run_id, "data_collect", "running", "已从检查点加载标准化月报数据包。", 45)

                # The preflight period is immutable for this run. A collector
                # must never silently turn an August report into September.
                if str(package.get("report_month", "")) != locked_month:
                    package = {**package, "generation_ready": False,
                               "code": "report_month_mismatch",
                               "message": f"目标月份为 {locked_month}，数据包月份为 {package.get('report_month') or '未确认'}；已阻止跨月份生成。"}
                self._update(
                    run_id, "data_gate", "running",
                    f"报告月份：{locked_month}；正在校验卡片完整性：{package.get('cards_usable', 0)}/{package.get('cards_expected', 45)}。" +
                    (f"允许更新滞后卡片：{'、'.join(package['delayed_cards'])}；对应PPT内容保留原样。" if package.get('delayed_cards') else ''),
                    68, report_month=locked_month,
                    collection_mode=package.get("collection_mode", mode),
                    cards_reused=int(package.get("cards_reused", package.get("cards_expected", 45) if package.get("snapshot_reused") else 0)),
                    cards_collected=int(package.get("cards_collected", 0)),
                )
                self._save_checkpoint(run_id, "data_gate", {
                    "generation_ready": bool(package.get("generation_ready")),
                    "code": package.get("code", ""),
                    "report_month": locked_month,
                    "card_validation": package.get("card_validation", {}),
                    "delayed_cards": package.get("delayed_cards", []),
                }, completed=bool(package.get("generation_ready")))

                model_provider = str(payload.get("model_provider", "minimax"))
                narrative: dict[str, Any] | None = None
                narrative_runtime: dict[str, Any] = {}
                if package.get("generation_ready"):
                    narrative_checkpoint = checkpoints.get("narrative", {})
                    if "narrative" in completed and not payload.get("force_refresh"):
                        narrative = self._load_package(str(narrative_checkpoint.get("path", "")))
                        if narrative and (narrative.get("narrative_rule_version") != NARRATIVE_RULE_VERSION
                                          or not narrative.get('research')):
                            narrative = None
                    if narrative is None:
                        self._update(run_id, 'narrative', 'running',
                                     f'已加载逐页业务核验规则 {NARRATIVE_RULE_VERSION}；保留已验数据，只生成或修复观点。', 70)
                        def narrative_progress(message: str, progress: int) -> None:
                            self._update(run_id, "narrative", "running", message, progress)

                        async def narrative_workflow() -> dict[str, Any]:
                            load_dotenv(ENV_PATH, override=True)
                            if ZHIPU_ENV_PATH.is_file():
                                load_dotenv(ZHIPU_ENV_PATH, override=True)
                            config = load_json_config()
                            if model_provider:
                                allowed = {"minimax", "zhipu"}
                                if model_provider not in allowed or model_provider not in config.get("providers", {}):
                                    raise ValueError("不支持的模型选项。")
                                selected_provider = config["providers"][model_provider]
                                if selected_provider.get("enabled") is False:
                                    raise ValueError(
                                        str(selected_provider.get("availability_note"))
                                        or "当前模型暂不可由独立 AgentScope 任务调用。"
                                    )
                                config["active_provider"] = model_provider
                            plugin_ids = resolve_mcp_plugin_ids(
                                [str(item) for item in payload.get("capabilities", [])],
                                [str(item) for item in payload.get("mcp_plugins", [])],
                            )
                            clear_tool_call_events()
                            bundle = await load_market_mcp_plugins(
                                config,
                                agent_key="market_strategy",
                                selected_plugin_ids=plugin_ids,
                            )
                            for plugin_status in bundle.statuses:
                                if plugin_status.status == "disabled":
                                    continue
                                record_tool_call(
                                    "mcp_plugin_" + plugin_status.plugin_id.replace("-", "_"),
                                    "success" if plugin_status.status == "ready" else "warning",
                                    (
                                        f"{plugin_status.display_name}; status={plugin_status.status}; "
                                        f"tools={plugin_status.tool_count}; {plugin_status.detail}"
                                    ),
                                )
                            generated = await generate_monthly_narratives(
                                package,
                                run_id=run_id,
                                config=config,
                                plugin_tools=bundle.tools,
                                mapping_path=PASSENGER_MONTHLY_MAPPING_PATH,
                                examples_path=PASSENGER_MONTHLY_EXAMPLES_PATH,
                                output_dir=PASSENGER_MONTHLY_PACKAGE_DIR,
                                progress=narrative_progress,
                            )
                            return {
                                "narrative": generated,
                                "mcp_plugins": bundle.as_dict(),
                                "tool_events": get_tool_call_events(),
                            }

                        narrative_runtime = self._run_async_step(
                            run_id,
                            "narrative",
                            72,
                            "正在按页面异常调用证据工具并生成主旨句",
                            narrative_workflow,
                            max_attempts=2,
                            reset_browser_on_retry=False,
                        )
                        narrative = narrative_runtime["narrative"]
                        self._save_checkpoint(run_id, "narrative", {
                            "path": narrative.get("path", ""),
                            "slides": len(narrative.get("slides", [])),
                            "evidence": len(narrative.get("evidence", [])),
                            "research": narrative.get("research", {}),
                            "research_evidence": len(narrative.get("research_evidence", [])),
                            "evidence_gaps": narrative.get("evidence_gaps", []),
                            "mcp_plugins": narrative_runtime.get("mcp_plugins", {}),
                            "tool_events": narrative_runtime.get("tool_events", []),
                            "rule_version": NARRATIVE_RULE_VERSION,
                        })
                    else:
                        narrative_runtime = {
                            "mcp_plugins": narrative_checkpoint.get("mcp_plugins", {}),
                            "tool_events": narrative_checkpoint.get("tool_events", []),
                        }
                        self._update(run_id, "narrative", "running", "已从检查点加载逐页主旨句与证据包。", 88)

                result = build_passenger_monthly_run_result(package, model_provider, narrative)
                result["tool_events"].extend(narrative_runtime.get("tool_events", []))
                result["mcp_plugins"] = narrative_runtime.get("mcp_plugins", {})
                if narrative:
                    self._update(run_id, "result_prepare", "running", "逐页主旨句与证据已通过校验，正在整理分析结果。", 94)
                self._update(run_id, "archive", "running",
                             "正在保存月报分析结果。" if narrative else "正在保存数据门禁诊断与已读取卡片。",
                             96 if narrative else 68)
                question = str(payload.get("question", ""))
                capabilities = payload.get("capabilities", [])
                project = store_project_run(
                    result,
                    question,
                    "passenger_car_monthly_report",
                    model_provider,
                    capabilities,
                    run_id=run_id,
                )
                result["project"] = project_list_item(project)
                store_latest_agent_run(result, question, "passenger_car_monthly_report")
                self._save_checkpoint(run_id, "archive", {"project_id": project.get("id", "")})
                self._update(
                    run_id,
                    "completed" if narrative else "data_gate",
                    "completed" if narrative else "input_required",
                    (
                        "逐页主旨句与证据包已通过门禁，可生成PPT。"
                        if narrative else "数据源门禁未通过，已停止主旨句与PPT生成。"
                    ),
                    100 if narrative else 68,
                    result=result,
                    recoverable=not bool(narrative),
                    error=None if narrative else {"type": package.get("code", "data_package_incomplete"), "message": package.get("message", "数据门禁未通过")},
                )
            except MonthlyJobCancelled as exc:
                self._update(
                    run_id,
                    "cancelled",
                    "cancelled",
                    str(exc),
                    int((self.get(run_id) or {}).get("progress", 0)),
                    recoverable=True,
                )
            except Exception as exc:
                self._update(
                    run_id,
                    "failed",
                    "failed",
                    f"月报后台任务中断：{type(exc).__name__}: {exc}",
                    int((self.get(run_id) or {}).get("progress", 0)),
                    error={"type": type(exc).__name__, "message": str(exc)},
                    recoverable=True,
                )


async def run_agent_once(
    agent_key: str,
    question: str,
    analysis_type: str = "",
    dataset_path: str | Path | None = None,
    sheet_name: str | None = None,
    model_provider: str = "",
    mcp_plugin_ids: list[str] | None = None,
) -> dict[str, Any]:
    """按前端选择调用对应业务智能体。"""
    load_dotenv(ENV_PATH, override=True)
    if ZHIPU_ENV_PATH.is_file():
        load_dotenv(ZHIPU_ENV_PATH, override=True)
    load_dotenv(PROJECT_DIR / ".env.bailian", override=True)
    clear_tool_call_events()
    config = load_json_config()
    forecast_task = analysis_type in {"forecast", "market_forecast"}
    macro_monthly_task = analysis_type == MACRO_MONTHLY_CAPABILITY_ID
    skill_run_context: SkillRunContext | None = None
    skill_runtime_tools: list[Any] = []
    if model_provider:
        allowed_providers = {"deepseek_flash", "deepseek_pro", "zhipu", "bailian_token_plan"}
        if model_provider not in allowed_providers or model_provider not in config.get("providers", {}):
            raise ValueError("不支持的模型选项。")
        selected_provider = config["providers"][model_provider]
        if selected_provider.get("enabled") is False:
            raise ValueError(
                str(selected_provider.get("availability_note"))
                or "当前模型暂不可由独立 AgentScope 任务调用。"
            )
        config["active_provider"] = model_provider
        config['_requested_provider'] = model_provider

    from integrations.forecast_engine_runtime import is_forecast_question
    if forecast_task or analysis_type == "forecast_engine" or (agent_key == "market_strategy" and analysis_type not in {PASSENGER_MONTHLY_CAPABILITY_ID, MACRO_MONTHLY_CAPABILITY_ID, "market_monthly_report"} and is_forecast_question(question)):
        from integrations.forecast_engine_runtime import run_forecast_engine_agent
        return await run_forecast_engine_agent(config, question)

    # 新版乘用车月报是确定性编排任务，不允许落入旧 MarketAnalysisSkill 的
    # 关键词自动触发逻辑。旧逻辑会注入历史 Excel 摘要，造成跨年份、跨口径混用。
    if analysis_type == "passenger_car_monthly_report":
        package = await MONTHLY_REPORT_BROWSER.read_all_cards()
        return build_passenger_monthly_run_result(
            package,
            str(config.get("active_provider", "")),
        )

    # 宏观月报的 33 页图表更新由包内确定性执行器完成；模型只承担最终业务说明，
    # 避免把逐图表写入留给一次长 ReAct 循环而出现不可恢复的卡顿。
    if macro_monthly_task:
        return await run_macro_monthly_skill(question, config)

    plugin_bundle = await load_market_mcp_plugins(
        config,
        agent_key=agent_key if agent_key == "user_insight_config" else "market_strategy",
        selected_plugin_ids=mcp_plugin_ids,
    )
    for plugin_status in plugin_bundle.statuses:
        if plugin_status.status == "disabled":
            continue
        record_tool_call(
            "mcp_plugin_" + plugin_status.plugin_id.replace("-", "_"),
            "success" if plugin_status.status == "ready" else "warning",
            (
                f"{plugin_status.display_name}; status={plugin_status.status}; "
                f"tools={plugin_status.tool_count}; {plugin_status.detail}"
            ),
        )

    market_skill_context = None
    if agent_key == "user_insight_config":
        agent = build_user_insight_agent(config, market_mcp_tools=plugin_bundle.tools)
    else:
        agent_key = "market_strategy"
        if analysis_type == "market_monthly_report":
            raise ValueError("旧版 Excel 月报 Skill 已下架，请显式选择“乘用车月报智能生成”。")
        monthly_report_max_tokens = None
        if macro_monthly_task:
            skill_run_context, skill_instruction, skill_runtime_tools = activate_skill_runtime(
                "macro-monthly-report",
            )
            record_tool_call(
                "skill_runtime_activate",
                "success",
                (
                    f"skill={skill_run_context.package.skill_id}; "
                    f"run_id={skill_run_context.run_id}; "
                    f"resources={len(skill_run_context.package.resources())}"
                ),
            )
        else:
            skill_instruction = load_passenger_forecast_skill_prompt() if forecast_task else ""
        agent = build_market_strategy_agent(
            config,
            skill_instruction=skill_instruction,
            monthly_report=False,
            forecast_task=forecast_task,
            max_tokens_override=monthly_report_max_tokens,
            market_mcp_tools=plugin_bundle.tools,
            skill_runtime_tools=skill_runtime_tools,
            max_iters_override=32 if skill_run_context else None,
        )

    # Complete Skill runs can make many tool calls. Bound the outer ReAct turn
    # so a provider stream or a remote tool cannot leave the browser request
    # waiting indefinitely without a recoverable run-state outcome.
    try:
        reply = await asyncio.wait_for(
            agent.reply(UserMsg(name="业务用户", content=question)),
            timeout=300 if skill_run_context else 180,
        )
    except TimeoutError as exc:
        if skill_run_context:
            state = skill_run_context.load_state()
            state["status"] = "needs_repair"
            skill_run_context.save_state(state)
            skill_run_context.checkpoint(
                "智能体执行超时，保留当前任务图和产物以便恢复。",
                {"timeout_seconds": 300},
            )
        raise RuntimeError("智能体执行超时，已保留任务检查点；请从项目中恢复或重新运行。") from exc
    answer = strip_thinking(reply.get_text_content())
    if not answer:
        # MiniMax-M3 偶发只完成推理阶段而未进入正文。使用全新会话执行一次
        # “最终交付模式”重试，避免把不可展示的推理片段直接抛给业务侧。
        retry_config = build_final_answer_retry_config(config)
        if market_skill_context and market_skill_context.active:
            market_skill_context.events.append(
                SkillEvent("model-retry", "running", "首轮未返回可展示正文，正在使用最终交付模式重试一次。"),
            )
            retry_agent = build_market_strategy_agent(
                retry_config,
                skill_instruction=market_skill_context.prompt_context,
                monthly_report=True,
                max_tokens_override=monthly_report_max_tokens,
                market_mcp_tools=plugin_bundle.tools,
            )
        elif agent_key == "market_strategy":
            retry_agent = build_market_strategy_agent(
                retry_config,
                skill_instruction=(
                    skill_run_context.package.runtime_prompt(skill_run_context.run_id)
                    if skill_run_context
                    else load_passenger_forecast_skill_prompt() if forecast_task else ""
                ),
                forecast_task=forecast_task,
                market_mcp_tools=plugin_bundle.tools,
                skill_runtime_tools=skill_runtime_tools,
                max_iters_override=32 if skill_run_context else None,
            )
        else:
            retry_agent = build_user_insight_agent(retry_config, market_mcp_tools=plugin_bundle.tools)
        retry_reply = await retry_agent.reply(UserMsg(name="业务用户", content=question))
        answer = strip_thinking(retry_reply.get_text_content())
        if answer and market_skill_context and market_skill_context.active:
            market_skill_context.events.append(
                SkillEvent("model-retry", "success", "已获得可展示正文，继续执行月报输出门禁。"),
            )

    # Package-aware Skills are completed by observable run-state and artifact
    # validation, not by a model merely saying that it is done.  If the first
    # ReAct pass stops early, feed the persisted validation result back into the
    # same agent for bounded repair cycles.
    if skill_run_context and answer:
        for repair_round in range(1, 3):
            validation = skill_run_context.validate()
            if validation.get("status") == "passed":
                break
            failed = [
                item for item in validation.get("checks", []) if not item.get("passed")
            ]
            record_tool_call(
                "skill_runtime_reflect",
                "warning",
                f"round={repair_round}; failed={json.dumps(failed, ensure_ascii=False)[:220]}",
            )
            reflection_reply = await agent.reply(
                UserMsg(
                    name="Skill运行时验收器",
                    content=(
                        "本轮尚未达到 Skill 的可验证完成条件。失败项："
                        + json.dumps(failed, ensure_ascii=False)
                        + "。请读取 run-state，反思当前计划并继续调用已挂载的 Skill、预测、文件和 PowerPoint 工具修复。"
                        "不要只解释或重新输出文字报告；必须生成并验证要求的实际交付物，更新任务节点，最后调用 skill_validate_run。"
                    ),
                ),
            )
            reflected_answer = strip_thinking(reflection_reply.get_text_content())
            if reflected_answer:
                answer = reflected_answer

    skill_delivery_url = ""
    if skill_run_context:
        runtime_state = skill_run_context.load_state()
        if (runtime_state.get("validation") or {}).get("status") == "passed":
            presentation = next(
                (
                    item for item in reversed(runtime_state.get("artifacts") or [])
                    if item.get("kind") == "presentation"
                    and str(item.get("path", "")).lower().endswith(".pptx")
                ),
                None,
            )
            if presentation:
                source = skill_run_context.workspace_path(
                    str(presentation["path"]),
                    must_exist=True,
                )
                PPT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                published = PPT_OUTPUT_DIR / f"{skill_run_context.run_id}-{safe_filename(source.stem)}.pptx"
                shutil.copy2(source, published)
                skill_delivery_url = "/" + str(published.relative_to(PROJECT_DIR)).replace("\\", "/")
                record_tool_call(
                    "skill_runtime_publish",
                    "success",
                    f"run_id={skill_run_context.run_id}; output={skill_delivery_url}",
                )

    tool_events = get_tool_call_events()
    if not answer:
        raise RuntimeError(
            "所选模型未返回可展示的最终正文，系统已拦截不完整内容；"
            "请稍后重试，并检查模型服务状态与任务规模。"
        )

    if market_skill_context and market_skill_context.active:
        answer, wording_events = normalize_top15_summary_wording(answer, market_skill_context)
        for detail in wording_events:
            market_skill_context.events.append(SkillEvent("report-normalize", "success", detail))
        answer, marker_events = normalize_external_evidence_marker_format(answer, market_skill_context)
        for detail in marker_events:
            market_skill_context.events.append(SkillEvent("report-normalize", "success", detail))
        output_checks = market_skill.validate_report(answer, market_skill_context)
        first_answer = answer
        first_checks = list(output_checks)
        first_score = monthly_report_check_score(first_checks)
        failed_checks = [item for item in output_checks if item.status != "通过"]
        if failed_checks:
            # 首轮输出没有通过质量门禁时，执行一次同上下文的完整重写。这里不是
            # 续写残稿，而是要求模型从标题开始交付可直接入库的完整月报。
            market_skill_context.events.append(
                SkillEvent("report-repair", "running", "首轮月报未通过输出门禁，正在执行一次完整重写。"),
            )
            failed_evidence = "；".join(f"{item.name}：{item.evidence}" for item in failed_checks)
            # 新建一个 Agent 执行重写，避免首轮长报告已写入的会话历史挤占修订轮的
            # 输出空间，或让模型错误地把“重写”理解为继续追加残稿。
            repair_agent = build_market_strategy_agent(
                config,
                skill_instruction=market_skill_context.prompt_context,
                monthly_report=True,
                max_tokens_override=monthly_report_max_tokens,
                market_mcp_tools=plugin_bundle.tools,
            )
            repair_reply = await repair_agent.reply(
                UserMsg(
                    name="月报质量门禁",
                    content=(
                        "上一版月报未通过输出质量门禁（"
                        + failed_evidence
                        + "）。请基于已注入的数据摘要，重新从总标题开始输出一份完整、"
                        "独立的 Markdown 月报。必须覆盖 Skill 规定的全部固定标题，"
                        "只输出报告正文，不要解释修订过程，也不要续写或引用上一版残稿。"
                    ),
                ),
            )
            repaired_answer = strip_thinking(repair_reply.get_text_content())
            if repaired_answer:
                repaired_answer, repaired_wording_events = normalize_top15_summary_wording(
                    repaired_answer,
                    market_skill_context,
                )
                repaired_answer, repaired_marker_events = normalize_external_evidence_marker_format(
                    repaired_answer,
                    market_skill_context,
                )
                repaired_checks = market_skill.validate_report(repaired_answer, market_skill_context)
                if monthly_report_check_score(repaired_checks) > first_score:
                    answer = repaired_answer
                    for detail in repaired_wording_events:
                        market_skill_context.events.append(SkillEvent("report-normalize", "success", detail))
                    for detail in repaired_marker_events:
                        market_skill_context.events.append(SkillEvent("report-normalize", "success", detail))
                    market_skill_context.events.append(
                        SkillEvent("report-repair", "success", "已采用质量门禁结果更优的完整重写版本。"),
                    )
                else:
                    answer = first_answer
                    market_skill_context.output_checks = first_checks
                    market_skill_context.events.append(
                        SkillEvent("report-repair", "warning", "重写版本未优于首轮，已保留章节更完整的首轮版本。"),
                    )
            else:
                market_skill_context.events.append(
                    SkillEvent("report-repair", "warning", "完整重写未返回可展示正文，保留首轮结果并标记输出门禁。"),
                )

        # 输出门禁、证据编号格式化和必要的重写均针对“审计草稿”完成。业务交付
        # 不暴露〔E/R〕编号，避免在无法查看服务端来源链的 PPT 中产生误解。
        answer, delivery_events = strip_internal_evidence_markers(answer)
        for detail in delivery_events:
            market_skill_context.events.append(SkillEvent("report-delivery", "success", detail))

    if "tavily_search" in question and not any(item.get("name") == "tavily_search" for item in tool_events):
        answer += "\n\n---\n【工具审计提示】本轮问题要求使用 tavily_search，但后端未捕获到真实 tavily_search 工具调用。请检查模型是否选择了工具、TAVILY_API_KEY 是否配置，以及 AgentScope ReAct 是否进入工具调用流程。"
    if "any_search" in question and not any(item.get("name") == "any_search" for item in tool_events):
        answer += "\n\n---\n【工具审计提示】本轮问题要求使用 any_search，但后端未捕获到真实 any_search 工具调用。请检查模型是否选择了工具、ANYSEARCH_API_KEY 是否配置，以及 AgentScope ReAct 是否进入工具调用流程。"

    return {
        "answer": answer,
        "agent": agent_key,
        "model_provider": config.get("active_provider", ""),
        "tool_events": tool_events,
        "mcp_plugins": plugin_bundle.as_dict(),
        "skill": (
            {
                "active": True,
                "name": "passenger-car-market-forecast",
                "display_name": "乘用车市场预测",
                "output_gate": "年度值来自用户确认",
            }
            if forecast_task
            else {
                "active": True,
                "name": "macro-monthly-report",
                "display_name": "宏观经济月报",
                "output_gate": "内部逐页数据台账自动建立",
                "events": [
                    {
                        "stage": "audit-ledger",
                        "status": "success",
                        "detail": "数据台账由智能体在执行过程中自动建立，不要求业务上传。",
                    }
                ],
            }
            if macro_monthly_task
            else market_skill_context.as_response() if market_skill_context and market_skill_context.active else None
        ),
        "skill_run": (
            {
                "run_id": skill_run_context.run_id,
                "workspace": str(skill_run_context.root),
                "state": skill_run_context.load_state(),
                "delivery_url": skill_delivery_url,
            }
            if skill_run_context
            else None
        ),
    }


def archive_forecast_baseline(job, request):
    """Archive the executed baseline, including replayable task evidence."""
    forecast = job['result']
    lines = [f"# {forecast['year']}年乘用车月度基准试算", '',
             f"年度采用值：{forecast['annual_total']:,.2f}万辆；来源为用户确认。信息截止日：{forecast['as_of_date']}。",
             '执行方式：业务Skill确定性规则。已发布月份作为实际历史输入，未发布月份为规则预测；年度采用值由业务确认。', '',
             '|月份|数据性质|乘用车总量（万辆）|新能源渗透率|新能源（万辆）|非新能源（万辆）|',
             '|---|---|---:|---:|---:|---:|']
    for row in forecast['rows']:
        status = '已发布实际' if row['status'] == 'provided' else '规则预测·试算'
        penetration = '—' if row['penetration'] is None else f"{row['penetration']:.2f}%"
        lines.append(f"|{row['month']}月|{status}|{row['total']:.2f}|{penetration}|{row['nev']:.2f}|{row['traditional']:.2f}|")
    lines.extend(['', '假设与限制：'] + [str(v) for v in forecast.get('warnings', [])])
    lines.extend([''] + [f"[{a['label']}]({a['url']})" for a in job['artifacts']])
    state = json.loads((PROJECT_DIR / 'runtime/passenger-forecast' / job['run_id'] / 'run-state.json').read_text(encoding='utf-8'))
    result = {'answer': '\n'.join(lines), 'agent': 'market_strategy', 'model_provider': 'Skill规则执行器（基准试算）',
              'business_status': 'incomplete', 'formal_delivery_allowed': False,
              'quality': {'overall_status': '计算与文件验收通过；已发布月份保留为实际'},
              'tool_events': [{'name': s['id'], 'status': s['status'], 'detail': s['summary']} for s in job['steps']],
              'skill': {'active': True, 'name': 'passenger-car-market-forecast', 'display_name': '乘用车市场基准预测', 'output_gate': '基准计算通过，已发布月份保留为实际'},
              'skill_run': {'run_id': job['run_id'], 'state': state, 'delivery_url': next((a['url'] for a in job['artifacts'] if a['kind'] == 'pptx'), '')}}
    project = store_project_run(result, request.get('question') or '执行Excel历史销量基准预测', 'market_forecast', result['model_provider'], ['月度基准预测'], run_id=job['run_id'], replace_existing=True)
    return project['id']


FORECAST_JOBS = PassengerForecastJobs(PROJECT_DIR, PASSENGER_FORECAST_SKILL_DIR, archive_forecast_baseline)

MONTHLY_REPORT_JOBS = MonthlyReportJobManager(MONTHLY_JOB_DIR)


def _macro_execution_config(model_provider: str) -> dict[str, Any]:
    load_dotenv(ENV_PATH, override=True)
    if ZHIPU_ENV_PATH.is_file():
        load_dotenv(ZHIPU_ENV_PATH, override=True)
    load_dotenv(PROJECT_DIR / ".env.bailian", override=True)
    config = load_json_config()
    provider = model_provider or config.get("active_provider", "deepseek_flash")
    selected = (config.get("providers") or {}).get(provider)
    if not isinstance(selected, dict):
        raise ValueError("不支持的模型选项。")
    if selected.get("enabled") is False:
        raise ValueError(str(selected.get("availability_note") or "该模型凭证不能用于当前独立智能体。"))
    config["active_provider"] = provider
    return config


def start_macro_background_job(payload: dict[str, Any]) -> dict[str, Any]:
    capabilities = payload.get("capabilities", [])
    if not isinstance(capabilities, list):
        raise ValueError("capabilities 必须是能力 ID 数组。")
    capabilities = [str(item) for item in capabilities]
    analysis_type = resolve_analysis_type(str(payload.get("analysis_type", "")), capabilities)
    if analysis_type != MACRO_MONTHLY_CAPABILITY_ID:
        raise ValueError("该后台任务接口仅用于已勾选的宏观经济月报技能。")
    requested_plugins = payload.get("mcp_plugins")
    if requested_plugins is not None and not isinstance(requested_plugins, list):
        raise ValueError("mcp_plugins 必须是插件 ID 数组。")
    question = str(payload.get("question", "")).strip()
    if not question:
        raise ValueError("宏观月报任务问题不能为空。")
    _macro_execution_config(str(payload.get("model_provider", "")))
    clean = dict(payload)
    clean.update(capabilities=capabilities, mcp_plugins=resolve_mcp_plugin_ids(capabilities, requested_plugins),
                 report_month=str(payload.get("report_month") or _macro_report_month(question)))
    return MACRO_REPORT_JOBS.start(clean)


def _execute_macro_job(jobs: MacroReportJobManager, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    with AGENT_RUN_LOCK:
        clear_tool_call_events()
        config = _macro_execution_config(str(payload.get("model_provider", "")))
        return AGENT_LOOP_RUNNER.run(run_macro_monthly_skill(str(payload.get("question", "")), config,
                                                           run_id=run_id, jobs=jobs, payload=payload))


def _archive_macro_job(run_id: str, payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    project = store_project_run(result, str(payload.get("question", "")), MACRO_MONTHLY_CAPABILITY_ID,
                                str(payload.get("model_provider", "")), payload.get("capabilities", []),
                                run_id=run_id, replace_existing=True)
    store_latest_agent_run(result, str(payload.get("question", "")), MACRO_MONTHLY_CAPABILITY_ID)
    return project_list_item(project)


def verified_macro_delivery(run_id: str) -> dict[str, Any]:
    """The export button retrieves only the same verified, immutable run file."""
    if not re.fullmatch(r"macro-\d{8}-\d{6}-[a-f0-9]{8}", run_id):
        raise ValueError("缺少本轮宏观月报有效run_id；旧基准稿不能作为正式PPT导出。")
    job = MACRO_REPORT_JOBS.get(run_id)
    if not job or job.get("status") != "completed" or not MacroReportJobManager.verified(job.get("result") or {}):
        raise ValueError("本轮宏观月报尚未通过业务、结构与Office总验收，正式导出已阻断。")
    state_file = SKILL_RUNTIME_ROOT / run_id / "run-state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    if state.get("formal_delivery_allowed") is not True or state.get("business_status") != "passed" or (state.get("validation") or {}).get("status") != "passed":
        raise ValueError("持久化宏观月报总验收未通过。")
    validations = {item.get("validator") for item in state.get("artifact_validations", []) if item.get("passed")}
    if not {"macro_business", "pptx_structure", "powerpoint_render", "macro_layout"}.issubset(validations):
        raise ValueError("宏观月报缺少独立业务或文件验收证据。")
    url = str((job["result"].get("skill_run") or {}).get("delivery_url", ""))
    path = (PROJECT_DIR / unquote(url).lstrip("/")).resolve()
    if path.parent != PPT_OUTPUT_DIR.resolve() or not path.name.startswith(run_id + "-") or not path.is_file():
        raise ValueError("已验收宏观月报文件不存在或路径不属于本轮运行。")
    delivery = state.get("delivery") or {}
    if delivery.get("url") != url or delivery.get("published_filename") != path.name:
        raise ValueError("宏观月报缺少本轮发布指纹，不能导出旧稿或替换稿。")
    run_root = state_file.parent.resolve()
    original = (run_root / str(delivery.get("artifact_path", ""))).resolve()
    ledger = (run_root / str(delivery.get("ledger_path", ""))).resolve()
    if (run_root not in original.parents or run_root not in ledger.parents
            or not original.is_file() or not ledger.is_file()):
        raise ValueError("宏观月报原始验收产物或台账不存在，或路径不属于本轮运行。")
    expected = str(delivery.get("artifact_sha256", ""))
    if (not re.fullmatch(r"[a-f0-9]{64}", expected)
            or delivery.get("published_sha256") != expected
            or hashlib.sha256(original.read_bytes()).hexdigest() != expected
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
            or hashlib.sha256(ledger.read_bytes()).hexdigest() != delivery.get("ledger_sha256")
            or json.loads(ledger.read_text(encoding="utf-8")).get("pptx_sha256") != expected):
        raise ValueError("宏观月报或台账内容已变化，与已验收内容指纹不一致，正式导出阻断。")
    bound_gates = {item.get("validator") for item in state.get("artifact_validations", [])
                   if item.get("passed") and item.get("path") == delivery.get("artifact_path")}
    if not {"macro_business", "pptx_structure", "powerpoint_render", "macro_layout"}.issubset(bound_gates):
        raise ValueError("宏观月报验收证据未绑定同一交付文件。")
    return {"success": True, "run_id": run_id, "pptx_url": url, "sha256": expected,
            "report_month": job.get("payload", {}).get("report_month")}


def verified_macro_draft_delivery(run_id: str) -> dict[str, Any]:
    """Draft downloads are opt-in and separate from formal/public file routes."""
    from utils.macro_report_delivery import verified_draft_artifact
    if not re.fullmatch(r"macro-\d{8}-\d{6}-[a-f0-9]{8}", run_id):
        raise ValueError("缺少有效的公开数据草稿run_id。")
    job = MACRO_REPORT_JOBS.get(run_id)
    if (not job or job.get("status") != "draft_ready"
            or not MacroReportJobManager.verified_draft(job.get("result") or {}, job.get("payload") or {})):
        raise ValueError("本轮公开数据草稿尚未经过显式选择和完整草稿验收。")
    root = (SKILL_RUNTIME_ROOT / run_id).resolve()
    state = json.loads((root / "run-state.json").read_text(encoding="utf-8"))
    delivery = verified_draft_artifact(state, root, run_id)
    delivery["report_month"] = job.get("payload", {}).get("report_month")
    return delivery


def verified_macro_retained_delivery(run_id: str) -> dict[str, Any]:
    """Draft downloads are opt-in and separate from formal/public file routes."""
    from utils.macro_report_delivery import verified_retained_artifact
    if not re.fullmatch(r"macro-\d{8}-\d{6}-[a-f0-9]{8}", run_id):
        raise ValueError("缺少有效的历史延续版run_id。")
    job = MACRO_REPORT_JOBS.get(run_id)
    if (not job or job.get("status") not in {"partial_completed","completed","retained_ready"}
            or not MacroReportJobManager.verified_retained(job.get("result") or {}, job.get("payload") or {})):
        raise ValueError("本轮历史延续版尚未经过显式选择和完整历史延续版验收。")
    root = (SKILL_RUNTIME_ROOT / run_id).resolve()
    state = json.loads((root / "run-state.json").read_text(encoding="utf-8"))
    delivery = verified_retained_artifact(state, root, run_id)
    delivery["report_month"] = job.get("payload", {}).get("report_month")
    return delivery


MACRO_REPORT_JOBS = MacroReportJobManager(PROJECT_DIR / "runtime" / "macro-report-jobs", _execute_macro_job, _archive_macro_job)

def _weekly_section_runner(context, section, request, coverage, check_cancel):
    return run_weekly_section(context, section, request, coverage, check_cancel,
                              _macro_execution_config(request['model_provider']))


def _archive_weekly_report(job, request):
    start, end = job['report_period']
    lines = [f"# 中国汽车产业周度资讯快报 {start} 至 {end}", '',
             f"九大章节、十四个板块；已核验 {job['items']} 条资讯。三件套内容与来源验收通过。", '']
    lines.extend(f"[{item['label']}]({item['url']})" for item in job['artifacts'])
    result = {'answer': '\n'.join(lines), 'agent': 'market_strategy', 'model_provider': request['model_provider'],
              'quality': {'overall_status': 'passed', 'weekly_three_artifacts': 'passed'},
              'tool_events': [{'name': step['id'], 'status': step['status'], 'detail': step['summary']} for step in job['state']['plan']],
              'skill': {'active': True, 'name': 'auto-weekly-report', 'display_name': '周度资讯快报自动生成', 'output_gate': '三件套验收通过'},
              'skill_run': {'run_id': job['run_id'], 'package_hash': job['package_hash'], 'state': job['state'],
                            'artifacts': job['artifacts'], 'delivery_url': job['artifacts'][0]['url']}}
    project = store_project_run(result, request.get('question') or f'{start}至{end}周度资讯快报',
                                'auto_weekly_report', request['model_provider'], ['auto_weekly_report'],
                                run_id=job['run_id'], replace_existing=True)
    return project['id']


WEEKLY_REPORT_JOBS = WeeklyReportJobs(PROJECT_DIR, PROJECT_DIR / 'skills/auto-weekly-report',
                                     _macro_execution_config, _weekly_section_runner, _archive_weekly_report)



def main() -> None:
    """启动本地 Web 服务。"""
    load_dotenv(ENV_PATH, override=True)
    if ZHIPU_ENV_PATH.is_file():
        load_dotenv(ZHIPU_ENV_PATH, override=True)
    AGENT_LOOP_RUNNER.start()
    MONTHLY_REPORT_JOBS.recover_pending()
    MACRO_REPORT_JOBS.recover_pending()
    WEEKLY_REPORT_JOBS.recover_pending()
    httpd = ThreadingHTTPServer((HOST, PORT), AgentDemoHandler)
    print("AgentScope 多智能体 Web 服务已启动: http://" + HOST + ":" + str(PORT))
    print("界面已按中汽中心AI-UI设计规范重做，并支持双 Agent 选择。")
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        # Do not explicitly close the monthly-report browser here.  It contains
        # a user-established SMS-authenticated BI session and must outlive
        # ordinary task cleanup.  Service restarts are guarded separately.
        AGENT_LOOP_RUNNER.stop()


if __name__ == "__main__":
    main()
