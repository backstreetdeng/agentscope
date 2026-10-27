"""Skill discovery, package mounting, task graphs, and persistent run state.

This module deliberately contains no domain-specific monthly-report workflow.
It provides the same generic primitives for every Skill package: discover the
package, resolve package-relative resources, create an isolated run workspace,
persist an agent-authored task graph, and validate declared deliverables.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any
from uuid import uuid4

import yaml


class SkillRuntimeError(RuntimeError):
    """Raised when a Skill package or run violates the runtime contract."""


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _safe_relative_path(value: str) -> Path:
    normalized = str(value or "").replace("\\", "/").strip().lstrip("/")
    path = Path(normalized)
    if not normalized or any(part in {"", ".", ".."} for part in path.parts):
        raise SkillRuntimeError(f"非法的 Skill 相对路径：{value!r}")
    return path


def _inside(root: Path, candidate: Path) -> Path:
    root = root.resolve()
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SkillRuntimeError(f"路径超出允许范围：{candidate}") from exc
    return candidate


def _frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not match:
        raise SkillRuntimeError(f"SKILL.md 缺少 YAML frontmatter：{path}")
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        raise SkillRuntimeError(f"SKILL.md frontmatter 必须是对象：{path}")
    return metadata, text[match.end():]


@dataclass(frozen=True)
class SkillPackage:
    """A validated Skill folder and its discoverable metadata."""

    skill_id: str
    name: str
    description: str
    root: Path
    skill_markdown: str
    instructions: str
    interface: dict[str, Any]
    policy: dict[str, Any]
    dependencies: dict[str, Any]
    artifact_template: dict[str, Any] | None
    package_hash: str

    def resolve(self, relative_path: str, *, must_exist: bool = True) -> Path:
        path = _inside(self.root, self.root / _safe_relative_path(relative_path))
        if must_exist and not path.exists():
            raise SkillRuntimeError(f"Skill 资源不存在：{relative_path}")
        return path

    def resources(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.root).as_posix()
            group = relative.split("/", 1)[0] if "/" in relative else "root"
            rows.append(
                {
                    "path": relative,
                    "group": group,
                    "bytes": path.stat().st_size,
                    "editable": False,
                }
            )
        return rows

    def runtime_prompt(self, run_id: str) -> str:
        asset_hint = ""
        if self.artifact_template:
            asset_hint = (
                "\n模板清单已由运行时验证："
                + json.dumps(self.artifact_template, ensure_ascii=False)
            )
        return (
            f"你正在通过通用 Skill Runtime 执行 ${self.name}。\n"
            f"skill_id={self.skill_id}; run_id={run_id}; package_hash={self.package_hash[:12]}。\n"
            "这不是提示词模拟：完整 Skill 包已只读挂载，必须通过 skill_package_* 工具按需读取 references、assets 和清单；"
            "若包内提供 scripts/，可用 skill_run_script 在隔离工作区执行，不要把脚本内容改写成临时提示词。"
            "所有输出写入本次运行工作区。开始时先调用 skill_plan_tasks 建立可验证任务图，执行中持续更新任务状态和检查点。"
            "不要声称资源不存在，除非 skill_package_inspect 或 skill_read_resource 返回不存在。"
            "不要只给操作说明；在具备工具时必须继续调用工具完成产物。"
            "若交付物是 PPTX，必须通过 presentation_validate；运行环境支持桌面 Office 时再调用 "
            "presentation_powerpoint_validate 做增强验收。"
            "最终仅在 skill_validate_run 通过后才能声称任务完成。"
            + asset_hint
            + "\n\n# Skill instructions\n\n"
            + self.instructions.strip()
        )


class SkillRegistry:
    """Discover complete Skill packages below one or more roots."""

    def __init__(self, roots: list[Path]) -> None:
        self.roots = [Path(root).resolve() for root in roots]

    def discover(self) -> dict[str, SkillPackage]:
        packages: dict[str, SkillPackage] = {}
        for root in self.roots:
            if not root.is_dir():
                continue
            for skill_file in root.glob("*/SKILL.md"):
                package = self._load(skill_file.parent)
                packages[package.skill_id] = package
                packages.setdefault(package.name, package)
        return packages

    def get(self, skill_id: str) -> SkillPackage:
        packages = self.discover()
        package = packages.get(str(skill_id).strip())
        if package is None:
            available = sorted({item.skill_id for item in packages.values()})
            raise SkillRuntimeError(
                f"未找到 Skill {skill_id!r}；可用 Skill：{', '.join(available)}"
            )
        return package

    @staticmethod
    def _load(root: Path) -> SkillPackage:
        skill_file = root / "SKILL.md"
        frontmatter, body = _frontmatter(skill_file)
        name = str(frontmatter.get("name") or root.name).strip()
        description = str(frontmatter.get("description") or "").strip()
        if not name or not description:
            raise SkillRuntimeError(f"Skill 名称或描述缺失：{skill_file}")

        agent_config: dict[str, Any] = {}
        agent_file = root / "agents" / "openai.yaml"
        if agent_file.is_file():
            loaded = yaml.safe_load(agent_file.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                agent_config = loaded

        artifact_template = None
        manifest_file = root / "artifact-template.json"
        if manifest_file.is_file():
            artifact_template = json.loads(manifest_file.read_text(encoding="utf-8"))
            if not isinstance(artifact_template, dict):
                raise SkillRuntimeError(f"artifact-template.json 必须是对象：{manifest_file}")
            for key in ("reference", "preview"):
                value = artifact_template.get(key)
                if value:
                    candidate = _inside(root, root / _safe_relative_path(str(value)))
                    if not candidate.is_file():
                        raise SkillRuntimeError(f"模板清单引用的资源不存在：{value}")

        digest = hashlib.sha256()
        # Python import caches are execution side effects, not Skill versions.
        # Including them would make an unchanged run unable to resume after its
        # own first import. Keep every source/asset/config in the version hash.
        for path in sorted(item for item in root.rglob("*") if item.is_file()
                           and "__pycache__" not in item.relative_to(root).parts
                           and item.suffix not in {".pyc", ".pyo"}):
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(str(path.stat().st_size).encode("ascii"))
            if path.stat().st_size <= 1024 * 1024:
                digest.update(path.read_bytes())

        return SkillPackage(
            skill_id=root.name,
            name=name,
            description=description,
            root=root.resolve(),
            skill_markdown=skill_file.read_text(encoding="utf-8"),
            instructions=body,
            interface=dict(agent_config.get("interface") or {}),
            policy=dict(agent_config.get("policy") or {}),
            dependencies=dict(agent_config.get("dependencies") or {}),
            artifact_template=artifact_template,
            package_hash=digest.hexdigest(),
        )


class SkillRunContext:
    """Persistent state and isolated workspace for one Skill execution."""

    def __init__(self, package: SkillPackage, runtime_root: Path, run_id: str | None = None) -> None:
        self.package = package
        self.run_id = run_id or (
            "skill-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
        )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.run_id):
            raise SkillRuntimeError(f"非法的 Skill run_id：{self.run_id!r}")
        self.root = Path(runtime_root).resolve() / self.run_id
        self.inputs_dir = self.root / "inputs"
        self.working_dir = self.root / "working"
        self.outputs_dir = self.root / "outputs"
        self.state_path = self.root / "run-state.json"
        self.checkpoints_path = self.root / "checkpoints.jsonl"
        for path in (self.inputs_dir, self.working_dir, self.outputs_dir):
            path.mkdir(parents=True, exist_ok=True)
        if not self.state_path.is_file():
            self.save_state(
                {
                    "schema_version": 1,
                    "run_id": self.run_id,
                    "skill_id": package.skill_id,
                    "skill_name": package.name,
                    "package_hash": package.package_hash,
                    "status": "created",
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                    "plan": [],
                    "artifacts": [],
                    "artifact_validations": [],
                    "validation": {"status": "pending", "checks": []},
                }
            )

    def load_state(self) -> dict[str, Any]:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def save_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = _now_iso()
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.state_path)

    def set_plan(self, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        if not tasks:
            raise SkillRuntimeError("任务图不能为空。")
        normalized = []
        seen: set[str] = set()
        for index, item in enumerate(tasks, start=1):
            task_id = str(item.get("id") or f"task-{index}").strip()
            if task_id in seen:
                raise SkillRuntimeError(f"任务 ID 重复：{task_id}")
            seen.add(task_id)
            normalized.append(
                {
                    "id": task_id,
                    "title": str(item.get("title") or task_id).strip(),
                    "success_criteria": str(item.get("success_criteria") or "").strip(),
                    "depends_on": [str(value) for value in item.get("depends_on") or []],
                    "status": "pending",
                    "summary": "",
                    "evidence": [],
                    "attempts": 0,
                }
            )
        state = self.load_state()
        state["plan"] = normalized
        state["status"] = "running"
        self.save_state(state)
        self.checkpoint("任务图已建立", {"task_count": len(normalized)})
        return state

    def update_task(
        self,
        task_id: str,
        status: str,
        summary: str = "",
        evidence: list[str] | None = None,
    ) -> dict[str, Any]:
        allowed = {"pending", "running", "completed", "failed", "blocked"}
        if status not in allowed:
            raise SkillRuntimeError(f"不支持的任务状态：{status}")
        state = self.load_state()
        task = next((item for item in state.get("plan", []) if item.get("id") == task_id), None)
        if task is None:
            raise SkillRuntimeError(f"任务图中不存在节点：{task_id}")
        task["status"] = status
        task["summary"] = str(summary or "")[:1000]
        task["evidence"] = [str(item) for item in (evidence or [])][:20]
        task["attempts"] = int(task.get("attempts", 0)) + (1 if status == "running" else 0)
        self.save_state(state)
        self.checkpoint(
            f"任务 {task_id} 更新为 {status}",
            {"summary": task["summary"], "evidence": task["evidence"]},
        )
        return task

    def checkpoint(self, message: str, data: dict[str, Any] | None = None) -> None:
        payload = {
            "at": _now_iso(),
            "message": str(message)[:1000],
            "data": data or {},
        }
        with self.checkpoints_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def workspace_path(self, relative_path: str, *, must_exist: bool = False) -> Path:
        path = _inside(self.root, self.root / _safe_relative_path(relative_path))
        if must_exist and not path.exists():
            raise SkillRuntimeError(f"运行工作区资源不存在：{relative_path}")
        return path

    def copy_asset(self, source_relative_path: str, output_name: str) -> Path:
        source = self.package.resolve(source_relative_path)
        target = _inside(self.outputs_dir, self.outputs_dir / _safe_relative_path(output_name))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        self.register_artifact(target, "working_copy")
        self.checkpoint(
            "已从 Skill 包复制资产",
            {"source": source_relative_path, "output": target.relative_to(self.root).as_posix()},
        )
        return target

    def register_artifact(self, path: Path, kind: str) -> None:
        path = _inside(self.root, path)
        if not path.is_file():
            raise SkillRuntimeError(f"交付物不存在：{path}")
        state = self.load_state()
        relative = path.relative_to(self.root).as_posix()
        row = {"path": relative, "kind": kind, "bytes": path.stat().st_size}
        previous = next(
            (item for item in state.get("artifacts", []) if item.get("path") == relative),
            None,
        )
        state["artifacts"] = [
            item for item in state.get("artifacts", []) if item.get("path") != relative
        ] + [row]
        # A validator commonly re-registers the same untouched artifact.  Keep
        # prior independent gates in that case; otherwise a later structural
        # check would erase an already-passed content check.  Any content or
        # kind change still invalidates the prior evidence as required.
        unchanged = bool(
            previous
            and previous.get("kind") == row["kind"]
            and previous.get("bytes") == row["bytes"]
        )
        if not unchanged:
            state["artifact_validations"] = [
                item for item in state.get("artifact_validations", []) if item.get("path") != relative
            ]
        self.save_state(state)

    def record_artifact_validation(
        self,
        path: Path,
        validator: str,
        passed: bool,
        detail: Any,
    ) -> None:
        path = _inside(self.root, path)
        relative = path.relative_to(self.root).as_posix()
        state = self.load_state()
        row = {
            "path": relative,
            "validator": str(validator),
            "passed": bool(passed),
            "detail": detail,
            "checked_at": _now_iso(),
        }
        state["artifact_validations"] = [
            item
            for item in state.get("artifact_validations", [])
            if not (item.get("path") == relative and item.get("validator") == validator)
        ] + [row]
        self.save_state(state)

    def validate(self, required_artifacts: list[str] | None = None) -> dict[str, Any]:
        state = self.load_state()
        checks: list[dict[str, Any]] = []
        plan = state.get("plan") or []
        checks.append(
            {
                "id": "plan_exists",
                "passed": bool(plan),
                "detail": f"任务节点 {len(plan)} 个",
            }
        )
        if (self.package.artifact_template or {}).get("kind") == "presentation":
            presentations = [
                item for item in state.get("artifacts", [])
                if item.get("kind") == "presentation" and str(item.get("path", "")).lower().endswith(".pptx")
            ]
            checks.append(
                {
                    "id": "presentation_deliverable",
                    "passed": bool(presentations),
                    "detail": (
                        f"PPTX 交付物 {len(presentations)} 个"
                        if presentations
                        else "尚未登记经过编辑与检查的 PPTX 交付物"
                    ),
                }
            )
            validations = state.get("artifact_validations", [])
            validator_labels = {
                "pptx_structure": "PPTX 结构验收",
                "powerpoint_render": "Microsoft PowerPoint 打开与逐页渲染验收",
            }
            required_validators = self.package.policy.get(
                "required_artifact_validators", ["pptx_structure"]
            )
            for validator in required_validators:
                label = validator_labels.get(str(validator), str(validator))
                matching = [
                    item
                    for item in validations
                    if item.get("validator") == validator
                    and item.get("passed")
                    and any(item.get("path") == deck.get("path") for deck in presentations)
                ]
                checks.append(
                    {
                        "id": validator,
                        "passed": bool(matching),
                        "detail": f"{label}已通过" if matching else f"{label}尚未通过",
                    }
                )
        if (self.package.artifact_template or {}).get("kind") == "document":
            required_kinds = self.package.policy.get("required_artifact_kinds", ["document"])
            for kind in required_kinds:
                artifacts = [item for item in state.get("artifacts", []) if item.get("kind") == kind]
                checks.append({"id": f"document:{kind}", "passed": bool(artifacts),
                               "detail": f"{kind} 已登记" if artifacts else f"缺少 {kind} 交付物"})
                for validator in self.package.policy.get("required_artifact_validators", []):
                    matching = [item for item in state.get("artifact_validations", [])
                                if item.get("validator") == validator and item.get("passed")
                                and any(item.get("path") == artifact.get("path") for artifact in artifacts)]
                    checks.append({"id": f"{kind}:{validator}", "passed": bool(matching),
                                   "detail": "独立验收通过" if matching else "尚未通过独立验收"})
        unfinished = [item.get("id") for item in plan if item.get("status") != "completed"]
        checks.append(
            {
                "id": "plan_completed",
                "passed": bool(plan) and not unfinished,
                "detail": "全部完成" if not unfinished else f"未完成：{unfinished}",
            }
        )
        for relative in required_artifacts or []:
            try:
                path = self.workspace_path(relative, must_exist=True)
                passed = path.is_file() and path.stat().st_size > 0
                detail = f"{relative}; bytes={path.stat().st_size if path.exists() else 0}"
            except Exception as exc:
                passed = False
                detail = f"{relative}; {exc}"
            checks.append({"id": f"artifact:{relative}", "passed": passed, "detail": detail})
        passed = all(item["passed"] for item in checks)
        state["validation"] = {
            "status": "passed" if passed else "failed",
            "checked_at": _now_iso(),
            "checks": checks,
        }
        state["status"] = "completed" if passed else "needs_repair"
        self.save_state(state)
        self.checkpoint("运行验收完成", state["validation"])
        return state["validation"]
