"""Durable macro-report jobs; execution is supplied by the application.

No model text can mark a job complete. Publication requires the persisted
runtime and business gates. A cancelled/blocked job retains its original id.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re
from threading import Event, Lock, Thread
from typing import Any, Callable
from uuid import uuid4


class MacroJobCancelled(RuntimeError):
    pass


class MacroJobBlocked(RuntimeError):
    def __init__(self, message: str, *, issues: list[Any] | None = None,
                 result: dict[str, Any] | None = None, status: str = "needs_repair") -> None:
        super().__init__(message)
        self.issues = issues or []
        self.result = result
        self.status = status


class MacroReportJobManager:
    TERMINAL_STATUSES = {"completed", "partial_completed", "draft_ready", "retained_ready", "failed", "cancelled", "input_required", "needs_repair", "waiting_input"}

    def __init__(self, root: Path, executor: Callable[..., dict[str, Any]],
                 archive: Callable[..., dict[str, Any]] | None = None) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.executor = executor
        self.archive = archive
        self._lock = Lock()
        self._worker_lock = Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._threads: dict[str, Thread] = {}
        self._cancel_events: dict[str, Event] = {}
        for path in self.root.glob("macro-*.json"):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
                run_id = state.get("run_id", "")
                if re.fullmatch(r"macro-\d{8}-\d{6}-[a-f0-9]{8}", run_id):
                    self._jobs[run_id] = state
            except (OSError, ValueError, TypeError):
                continue

    def _write(self, state: dict[str, Any]) -> None:
        path = self.root / f"{state['run_id']}.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def update(self, run_id: str, phase: str, message: str, progress: int,
               *, status: str = "running", **values: Any) -> dict[str, Any]:
        with self._lock:
            state = self._jobs[run_id]
            events = state.setdefault("events", [])
            now = self._now()
            events.append({"seq": events[-1]["seq"] + 1 if events else 1,
                           "at": now, "phase": phase, "status": status,
                           "message": message, "progress": progress})
            state.update(phase=phase, message=message, progress=progress, status=status,
                         updated_at=now, heartbeat_at=now, **values)
            self._write(state)
            return deepcopy(state)

    def checkpoint(self, run_id: str, phase: str, data: dict[str, Any], *, completed: bool = True) -> None:
        with self._lock:
            state = self._jobs[run_id]
            state.setdefault("checkpoints", {})[phase] = deepcopy(data)
            phases = state.setdefault("completed_phases", [])
            if completed and phase not in phases:
                phases.append(phase)
            state["updated_at"] = self._now()
            self._write(state)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._jobs.get(run_id)
            # A task can be created by another local service instance. The
            # persisted task is the same durable record across page reopen.
            path=self.root / f"{run_id}.json"
            if re.fullmatch(r"macro-\d{8}-\d{6}-[a-f0-9]{8}",run_id) and path.is_file():
                try:
                    saved=json.loads(path.read_text(encoding="utf-8"))
                    if not state or saved.get("updated_at","") > state.get("updated_at",""):
                        if saved.get("run_id")==run_id:self._jobs[run_id]=state=saved
                except (OSError,ValueError):pass
            return deepcopy(state) if state else None

    def check_cancelled(self, run_id: str) -> None:
        with self._lock:
            cancel = self._cancel_events.setdefault(run_id, Event())
        if cancel.is_set():
            raise MacroJobCancelled("宏观月报任务已取消，已完成的来源和更新检查点保留。")

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        report_month = str(payload.get("report_month", "")).strip()
        if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", report_month):
            raise ValueError("宏观月报需要有效报告月份（YYYY-MM）。")
        cutoff_date = str(payload.get("cutoff_date") or datetime.now().date().isoformat())
        try:
            parsed_cutoff = datetime.strptime(cutoff_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("信息截止日必须为 YYYY-MM-DD。") from exc
        if parsed_cutoff > datetime.now().date():
            raise ValueError("信息截止日不能晚于执行日。")
        mode = str(payload.get("mode") or ("forecast" if payload.get("delivery_mode") in {"formal","public_draft"} else "historical_update")).replace("historical-update", "historical_update")
        if mode not in {"forecast", "historical_update"} or payload.get("slides"):
            raise ValueError("当前宏观月报仅支持完整预测版或完整历史更新版；单页范围尚未接入。")
        delivery_mode = str(payload.get("delivery_mode") or ("historical_retained" if mode == "historical_update" else "formal"))
        if delivery_mode not in {"formal", "public_draft", "historical_retained"}:
            raise ValueError("不支持的宏观月报交付模式。")
        if delivery_mode == "public_draft" and payload.get("public_draft_confirmed") is not True:
            raise ValueError("公开数据草稿必须由用户显式选择并确认缺口标注；不会自动降级。")
        if mode == "historical_update" and delivery_mode == "public_draft":
            raise ValueError("历史更新与公开数据草稿是独立流程，请选择正式历史更新或旧版公开草稿。")
        if mode == "historical_update" and not payload.get("delivery_mode"):
            payload={**payload,"history_retention_confirmed":True}
        if delivery_mode == "historical_retained" and (mode != "historical_update" or payload.get("history_retention_confirmed") is not True):
            raise ValueError("历史延续版需要显式确认保留带日期的历史图表。")
        run_id = f"macro-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
        safe_payload = {"question": str(payload.get("question", "")).strip(),
                        "analysis_type": "macro_monthly_report",
                        "model_provider": str(payload.get("model_provider") or "minimax"),
                        "report_month": report_month, "cutoff_date": cutoff_date, "mode": mode,
                        "delivery_mode": delivery_mode,
                        "history_retention_confirmed": delivery_mode == "historical_retained" and payload.get("history_retention_confirmed") is True,
                        "public_draft_confirmed": delivery_mode == "public_draft" and payload.get("public_draft_confirmed") is True,
                        "capabilities": [str(x) for x in payload.get("capabilities", [])],
                        "mcp_plugins": [str(x) for x in payload.get("mcp_plugins", [])]}
        now = self._now()
        state = {"version": 1, "run_id": run_id, "kind": "macro_monthly_report",
                 "status": "queued", "phase": "queued", "progress": 0,
                 "created_at": now, "updated_at": now, "heartbeat_at": now,
                 "payload": safe_payload, "events": [], "completed_phases": [],
                 "checkpoints": {}, "error": None, "result": None, "recoverable": True}
        with self._lock:
            self._jobs[run_id] = state
            self._cancel_events[run_id] = Event()
        self.update(run_id, "queued", "宏观月报已入队，等待后台按逐页数据契约执行。", 1, status="queued")
        self._spawn(run_id)
        return self.get(run_id) or {}

    def _spawn(self, run_id: str) -> None:
        with self._lock:
            existing = self._threads.get(run_id)
            if existing and existing.is_alive():
                return
            thread = Thread(target=self._run, args=(run_id,), name=f"macro-job-{run_id[-8:]}", daemon=True)
            self._threads[run_id] = thread
            thread.start()

    def cancel(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._jobs.get(run_id)
            if not state or state.get("status") in self.TERMINAL_STATUSES:
                return deepcopy(state) if state else None
            self._cancel_events.setdefault(run_id, Event()).set()
            progress = int(state.get("progress", 0))
        return self.update(run_id, "cancel", "取消请求已记录，将在当前有界步骤结束后安全停止。", progress)

    def resume(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._jobs.get(run_id)
            if not state or state.get("status") in {"completed", "draft_ready", "retained_ready"}:
                return deepcopy(state) if state else None
            existing = self._threads.get(run_id)
            if existing and existing.is_alive():
                return deepcopy(state)
            self._cancel_events[run_id] = Event()
            if state.get("status") == "partial_completed":
                state["payload"]["resume_missing_pages"] = True
                self._write(state)
            progress = int(state.get("progress", 1))
        self.update(run_id, "resume", "从原运行检查点继续，不重复创建任务或重采已验收来源。", progress,
                    status="queued", error=None, recoverable=True)
        self._spawn(run_id)
        return self.get(run_id)

    def recover_pending(self) -> None:
        with self._lock:
            pending = [key for key, value in self._jobs.items() if value.get("status") in {"running", "queued"}]
        for run_id in pending:
            self.resume(run_id)

    def _heartbeat(self, run_id: str, done: Event) -> None:
        while not done.wait(15):
            # Read and append under the same lock: a heartbeat must not race
            # finalization and turn a completed job back into running.
            with self._lock:
                job = self._jobs[run_id]
                if job.get("status") in self.TERMINAL_STATUSES:
                    return
                events = job.setdefault("events", [])
                now = self._now()
                events.append({"seq": events[-1]["seq"] + 1 if events else 1,
                               "at": now, "phase": job.get("phase", "running"),
                               "status": job.get("status", "running"),
                               "message": f"{job.get('phase', 'running')}步骤仍在执行；已完成检查点保留。",
                               "progress": int(job.get("progress", 0))})
                job["heartbeat_at"] = now
                self._write(job)

    @staticmethod
    def verified(result: dict[str, Any]) -> bool:
        runtime = result.get("skill_run") or {}
        state = runtime.get("state") or {}
        validations = {item.get("validator") for item in state.get("artifact_validations", []) if item.get("passed")}
        return (result.get("business_status") == "passed"
                and result.get("formal_delivery_allowed") is True
                and state.get("formal_delivery_allowed") is True
                and state.get("business_status") == "passed"
                and (state.get("validation") or {}).get("status") == "passed"
                and {"macro_business", "pptx_structure", "powerpoint_render", "macro_layout"}.issubset(validations)
                and bool(runtime.get("delivery_url")))

    @staticmethod
    def verified_draft(result: dict[str, Any], payload: dict[str, Any]) -> bool:
        """A separate opt-in deliverable, never a formal gate substitute."""
        from utils.macro_report_delivery import verified_draft_state
        runtime = result.get("skill_run") or {}
        state = runtime.get("state") or {}
        run_id = str(result.get("run_id") or runtime.get("run_id") or "")
        return bool(payload.get("delivery_mode") == "public_draft"
                    and payload.get("public_draft_confirmed") is True
                    and result.get("delivery_mode") == "public_draft"
                    and result.get("draft_delivery_allowed") is True
                    and result.get("formal_delivery_allowed") is False
                    and result.get("business_status") == "draft_passed"
                    and runtime.get("delivery_mode") == "public_draft"
                    and runtime.get("delivery_url") == f"/api/macro-report/draft/{run_id}"
                    and result.get("draft_delivery_url") == runtime.get("delivery_url")
                    and verified_draft_state(state, run_id))

    @staticmethod
    def verified_retained(result: dict[str, Any], payload: dict[str, Any]) -> bool:
        """A separate opt-in deliverable, never a formal gate substitute."""
        from utils.macro_report_delivery import verified_retained_state
        runtime = result.get("skill_run") or {}
        state = runtime.get("state") or {}
        run_id = str(result.get("run_id") or runtime.get("run_id") or "")
        return bool(payload.get("delivery_mode") == "historical_retained"
                    and payload.get("history_retention_confirmed") is True
                    and result.get("delivery_mode") == "historical_retained"
                    and result.get("retained_delivery_allowed") is True
                    and result.get("formal_delivery_allowed") is False
                    and result.get("business_status") == "retained_passed"
                    and runtime.get("delivery_mode") == "historical_retained"
                    and runtime.get("delivery_url") == f"/api/macro-report/retained/{run_id}"
                    and result.get("retained_delivery_url") == runtime.get("delivery_url")
                    and verified_retained_state(state, run_id))

    def _archive(self, run_id: str, result: dict[str, Any]) -> dict[str, Any]:
        if self.archive:
            archived = self.archive(run_id, deepcopy((self.get(run_id) or {}).get("payload", {})), result)
            if archived:
                result["project"] = archived
                self.checkpoint(run_id, "archive", {"project_id": archived.get("id")})
        return result

    def _run(self, run_id: str) -> None:
        with self._worker_lock:
            done = Event()
            heartbeat = Thread(target=self._heartbeat, args=(run_id, done), daemon=True)
            try:
                self.check_cancelled(run_id)
                job = self.get(run_id) or {}
                self.update(run_id, "start", "后台宏观月报任务已启动。", int(job.get("progress", 1)))
                heartbeat.start()
                result = self.executor(self, run_id, deepcopy(job.get("payload", {})))
                self.check_cancelled(run_id)
                is_draft = job.get("payload", {}).get("delivery_mode") == "public_draft"
                is_retained = job.get("payload", {}).get("delivery_mode") == "historical_retained"
                valid = self.verified_retained(result, job.get("payload", {})) if is_retained else self.verified_draft(result, job.get("payload", {})) if is_draft else self.verified(result)
                if (is_draft or is_retained) and (result.get("run_id") != run_id or (result.get("skill_run") or {}).get("run_id") != run_id):
                    valid = False
                if not valid:
                    raise MacroJobBlocked("宏观月报未通过业务及运行时验收，文件保留，正式发布阻断。", result=result)
                result["run_id"] = run_id
                result = self._archive(run_id, result)
                finish_status = result.get("report_completion", "retained_ready") if is_retained else "draft_ready" if is_draft else "completed"
                self.update(run_id, finish_status if is_retained else "draft_ready" if is_draft else "completed",
                            "历史延续版已通过事实、历史日期、结构与Office验收。" if is_retained else "公开数据草稿已通过真实性、结构及Office验收；缺口已标注，不是正式完整月报。" if is_draft else "权威来源、逐页内容、可编辑文件及 Office 验收均已通过。", 100,
                            status=finish_status, result=result, recoverable=finish_status == "partial_completed", error=None)
            except MacroJobCancelled as exc:
                job = self.get(run_id) or {}
                self.update(run_id, "cancelled", str(exc), int(job.get("progress", 0)),
                            status="cancelled", error={"type": type(exc).__name__, "message": str(exc)}, recoverable=True)
            except MacroJobBlocked as exc:
                job = self.get(run_id) or {}
                result = self._archive(run_id, exc.result) if exc.result else None
                self.update(run_id, job.get("phase", "business_gate"), str(exc), int(job.get("progress", 0)),
                            status=exc.status, result=result, recoverable=True,
                            error={"type": type(exc).__name__, "message": str(exc), "issues": exc.issues})
            except Exception as exc:
                job = self.get(run_id) or {}
                self.update(run_id, job.get("phase", "failed"), f"{type(exc).__name__}: {exc}",
                            int(job.get("progress", 0)), status="failed", recoverable=True,
                            error={"type": type(exc).__name__, "message": str(exc)})
            finally:
                done.set()
