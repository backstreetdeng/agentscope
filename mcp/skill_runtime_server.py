"""Standard MCP surface for the complete-package Skill runtime.

The web agent uses native AgentScope adapters for low latency.  This server
exposes the same package, task-graph, forecast, presentation, and validation
capabilities to any MCP-compatible agent.  A run_id is an explicit durable
handle; server process memory is never the source of truth.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, Awaitable, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server.fastmcp import FastMCP

from skill_runtime import SkillRegistry, SkillRunContext
from skill_runtime.tools import (
    ForecastSeriesTool,
    PresentationInspectTool,
    PresentationPowerPointValidateTool,
    PresentationReplaceTextTool,
    PresentationUpdateChartTool,
    PresentationValidateTool,
    SkillCheckpointTool,
    SkillCopyAssetTool,
    SkillPackageInspectTool,
    SkillPlanTasksTool,
    SkillReadResourceTool,
    SkillRunScriptTool,
    SkillUpdateTaskTool,
    SkillValidateRunTool,
    WorkspaceListTool,
    WorkspaceReadTextTool,
    WorkspaceWriteTextTool,
)


SKILL_ROOT = Path(os.getenv("SKILL_REGISTRY_ROOT", PROJECT_ROOT / "skills")).resolve()
RUNTIME_ROOT = Path(
    os.getenv("SKILL_RUNTIME_ROOT", PROJECT_ROOT / "runtime" / "skill-runs")
).resolve()
REGISTRY = SkillRegistry([SKILL_ROOT])

READ_ONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
WRITE_WORKSPACE = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _context(run_id: str) -> SkillRunContext:
    state_path = RUNTIME_ROOT / str(run_id) / "run-state.json"
    if not state_path.is_file():
        raise ValueError(f"Skill run 不存在：{run_id}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    package = REGISTRY.get(str(state.get("skill_id") or ""))
    context = SkillRunContext(package, RUNTIME_ROOT, run_id=str(run_id))
    if state.get("package_hash") != package.package_hash:
        raise ValueError(
            "该任务对应的 Skill 包版本已经变化；请新建任务运行，避免混用不同版本资产。"
        )
    return context


async def _invoke(tool_factory: Callable[[SkillRunContext], Any], run_id: str, **kwargs: Any) -> str:
    chunk = await tool_factory(_context(run_id)).call(**kwargs)
    blocks = getattr(chunk, "content", [])
    return "\n".join(str(getattr(block, "text", block)) for block in blocks)


def build_server() -> FastMCP:
    server = FastMCP(
        "complete_skill_runtime",
        instructions=(
            "加载完整 Skill 包并执行持久化任务图。先 skill_activate，再检查包、建立任务图、"
            "调用文件/预测/PPT 工具，最后必须通过 presentation_validate 与 skill_validate_run。"
        ),
        host=os.getenv("SKILL_MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("SKILL_MCP_PORT", "8820")),
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )

    @server.resource("skill://registry")
    def skill_registry_resource() -> str:
        """Return the discoverable complete Skill packages."""
        packages = {item.skill_id: item for item in REGISTRY.discover().values()}
        return _json(
            [
                {
                    "skill_id": package.skill_id,
                    "name": package.name,
                    "description": package.description,
                    "package_hash": package.package_hash,
                }
                for package in packages.values()
            ]
        )

    @server.resource("skill://{skill_id}/manifest")
    def skill_manifest_resource(skill_id: str) -> str:
        """Return one Skill package manifest without loading binary content."""
        package = REGISTRY.get(skill_id)
        return _json(
            {
                "skill_id": package.skill_id,
                "name": package.name,
                "description": package.description,
                "package_hash": package.package_hash,
                "artifact_template": package.artifact_template,
                "dependencies": package.dependencies,
                "resources": package.resources(),
            }
        )

    @server.tool(name="skill_registry_list", annotations=READ_ONLY)
    async def skill_registry_list() -> str:
        """List validated complete Skill packages available to this runtime."""
        packages = {item.skill_id: item for item in REGISTRY.discover().values()}
        return _json(
            [
                {
                    "skill_id": package.skill_id,
                    "name": package.name,
                    "description": package.description,
                    "package_hash": package.package_hash,
                    "resource_count": len(package.resources()),
                    "artifact_template": package.artifact_template,
                }
                for package in packages.values()
            ]
        )

    @server.tool(name="skill_activate", annotations=WRITE_WORKSPACE)
    async def skill_activate(skill_id: str) -> str:
        """Mount one complete package and create a durable isolated run workspace."""
        package = REGISTRY.get(skill_id)
        context = SkillRunContext(package, RUNTIME_ROOT)
        return _json(
            {
                "run_id": context.run_id,
                "skill_id": package.skill_id,
                "package_hash": package.package_hash,
                "workspace": str(context.root),
                "runtime_instructions": package.runtime_prompt(context.run_id),
            }
        )

    @server.tool(name="skill_package_inspect", annotations=READ_ONLY)
    async def skill_package_inspect(run_id: str) -> str:
        """Inspect the mounted package, assets, dependencies and workspace."""
        return await _invoke(SkillPackageInspectTool, run_id)

    @server.tool(name="skill_read_resource", annotations=READ_ONLY)
    async def skill_read_resource(run_id: str, relative_path: str, max_chars: int = 20000) -> str:
        """Read a text resource from the mounted package; binary assets return metadata."""
        return await _invoke(
            SkillReadResourceTool, run_id, relative_path=relative_path, max_chars=max_chars
        )

    @server.tool(name="skill_plan_tasks", annotations=WRITE_WORKSPACE)
    async def skill_plan_tasks(run_id: str, tasks: list[dict[str, Any]]) -> str:
        """Create a persistent, verifiable task graph authored by the agent."""
        return await _invoke(SkillPlanTasksTool, run_id, tasks_json=json.dumps(tasks))

    @server.tool(name="skill_update_task", annotations=WRITE_WORKSPACE)
    async def skill_update_task(
        run_id: str,
        task_id: str,
        status: str,
        summary: str = "",
        evidence: list[str] | None = None,
    ) -> str:
        """Update a task node using observable evidence from tool results."""
        return await _invoke(
            SkillUpdateTaskTool,
            run_id,
            task_id=task_id,
            status=status,
            summary=summary,
            evidence_json=json.dumps(evidence or []),
        )

    @server.tool(name="skill_checkpoint", annotations=WRITE_WORKSPACE)
    async def skill_checkpoint(
        run_id: str,
        summary: str,
        next_action: str = "",
        evidence: list[str] | None = None,
    ) -> str:
        """Persist a recoverable checkpoint without recording hidden chain of thought."""
        return await _invoke(
            SkillCheckpointTool,
            run_id,
            summary=summary,
            next_action=next_action,
            evidence_json=json.dumps(evidence or []),
        )

    @server.tool(name="skill_copy_asset", annotations=WRITE_WORKSPACE)
    async def skill_copy_asset(run_id: str, source_relative_path: str, output_name: str) -> str:
        """Copy a read-only package asset into the run workspace before editing."""
        return await _invoke(
            SkillCopyAssetTool,
            run_id,
            source_relative_path=source_relative_path,
            output_name=output_name,
        )

    @server.tool(name="workspace_list", annotations=READ_ONLY)
    async def workspace_list(run_id: str, prefix: str = "") -> str:
        """List durable input, working and output files for an active run."""
        return await _invoke(WorkspaceListTool, run_id, prefix=prefix)

    @server.tool(name="workspace_read_text", annotations=READ_ONLY)
    async def workspace_read_text(run_id: str, path: str, max_chars: int = 50000) -> str:
        """Read a safe text file from an active run workspace."""
        return await _invoke(WorkspaceReadTextTool, run_id, path=path, max_chars=max_chars)

    @server.tool(name="workspace_write_text", annotations=WRITE_WORKSPACE)
    async def workspace_write_text(
        run_id: str, path: str, content: str, artifact_kind: str = ""
    ) -> str:
        """Write a safe text artifact or intermediate file into a run workspace."""
        return await _invoke(
            WorkspaceWriteTextTool,
            run_id,
            path=path,
            content=content,
            artifact_kind=artifact_kind,
        )

    @server.tool(name="skill_run_script", annotations=WRITE_WORKSPACE)
    async def skill_run_script(
        run_id: str,
        relative_path: str,
        args: list[str] | None = None,
        timeout_seconds: int = 180,
    ) -> str:
        """Execute a trusted script shipped inside the mounted package's scripts directory."""
        return await _invoke(
            SkillRunScriptTool,
            run_id,
            relative_path=relative_path,
            args_json=json.dumps(args or [], ensure_ascii=False),
            timeout_seconds=timeout_seconds,
        )

    @server.tool(name="presentation_inspect", annotations=READ_ONLY)
    async def presentation_inspect(run_id: str, path: str, include_text: bool = True) -> str:
        """Inspect slide text, native charts, series, categories and tables."""
        return await _invoke(
            PresentationInspectTool, run_id, path=path, include_text=include_text
        )

    @server.tool(name="presentation_replace_text", annotations=WRITE_WORKSPACE)
    async def presentation_replace_text(
        run_id: str, path: str, replacements: dict[str, str]
    ) -> str:
        """Replace exact text in an editable workspace presentation copy."""
        return await _invoke(
            PresentationReplaceTextTool,
            run_id,
            path=path,
            replacements_json=json.dumps(replacements, ensure_ascii=False),
        )

    @server.tool(name="presentation_update_chart", annotations=WRITE_WORKSPACE)
    async def presentation_update_chart(
        run_id: str,
        path: str,
        slide_number: int,
        chart_number: int,
        categories: list[str],
        series: list[dict[str, Any]],
    ) -> str:
        """Update a native editable chart in a workspace presentation copy."""
        return await _invoke(
            PresentationUpdateChartTool,
            run_id,
            path=path,
            slide_number=slide_number,
            chart_number=chart_number,
            categories_json=json.dumps(categories, ensure_ascii=False),
            series_json=json.dumps(series, ensure_ascii=False),
        )

    @server.tool(name="forecast_series", annotations=READ_ONLY)
    async def forecast_series(
        run_id: str,
        periods: list[str],
        values: list[float],
        horizon: int,
        method: str = "linear_trend",
        season_length: int = 12,
    ) -> str:
        """Run a transparent baseline forecast within an active Skill run."""
        return await _invoke(
            ForecastSeriesTool,
            run_id,
            periods_json=json.dumps(periods, ensure_ascii=False),
            values_json=json.dumps(values),
            horizon=horizon,
            method=method,
            season_length=season_length,
        )

    @server.tool(name="presentation_validate", annotations=READ_ONLY)
    async def presentation_validate(
        run_id: str,
        path: str,
        expected_slides: int = 0,
        minimum_charts: int = 0,
    ) -> str:
        """Validate PPTX package integrity, editability and structural requirements."""
        return await _invoke(
            PresentationValidateTool,
            run_id,
            path=path,
            expected_slides=expected_slides,
            minimum_charts=minimum_charts,
        )

    @server.tool(name="presentation_powerpoint_validate", annotations=READ_ONLY)
    async def presentation_powerpoint_validate(run_id: str, path: str) -> str:
        """Open and render the deck with desktop Microsoft PowerPoint for compatibility QA."""
        return await _invoke(PresentationPowerPointValidateTool, run_id, path=path)

    @server.tool(name="skill_validate_run", annotations=READ_ONLY)
    async def skill_validate_run(run_id: str, required_artifacts: list[str] | None = None) -> str:
        """Independently validate the task graph and required output artifacts."""
        return await _invoke(
            SkillValidateRunTool,
            run_id,
            required_artifacts_json=json.dumps(required_artifacts or []),
        )

    return server


mcp = build_server()


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "streamable-http")
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError(f"不支持的 MCP_TRANSPORT：{transport}")
    mcp.run(transport=transport)
