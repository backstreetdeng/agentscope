"""Persistent, independently validated passenger-market baseline runs."""
from __future__ import annotations
import csv
import hashlib
import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4
from skill_runtime.core import SkillRegistry, SkillRunContext
from utils.passenger_forecast import parse_history, build_forecast, validate_forecast
from utils.passenger_forecast_exports import export_forecast, validate_exports


def _now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PassengerForecastJobs:
    MAX_UPLOAD_BYTES = 10 * 1024 * 1024

    def __init__(self, project_dir, skill_dir, on_complete=None):
        self.project_dir, self.skill_dir = Path(project_dir), Path(skill_dir)
        self.data_dir = self.project_dir / "data/passenger-forecast"
        self.run_dir = self.project_dir / "runtime/passenger-forecast"
        self.on_complete, self.lock, self.active = on_complete, Lock(), set()

    def _history_path(self, history_id):
        if not re.fullmatch(r"history-[a-f0-9]{24}", str(history_id)):
            raise ValueError("历史数据标识无效。")
        return self.data_dir / history_id

    def _run_path(self, run_id):
        if not re.fullmatch(r"forecast-\d{8}-\d{6}-[a-f0-9]{8}", str(run_id)):
            raise ValueError("预测运行标识无效。")
        root = self.run_dir / run_id
        if not (root / "run-state.json").is_file():
            raise ValueError("未找到该预测任务。")
        return root

    def upload(self, filename, content, unit):
        filename = str(filename).replace("\\", "/").split("/")[-1].strip()
        suffix = Path(filename).suffix.lower()
        if not filename or len(filename) > 180 or suffix not in {".xlsx", ".csv"}:
            raise ValueError("请选择 .xlsx 或 .csv 历史销量文件。")
        if not content or len(content) > self.MAX_UPLOAD_BYTES:
            raise ValueError("文件为空或超过10 MB。")
        if unit not in {"vehicle", "wan"}:
            raise ValueError("请选择原文件单位：辆或万辆。")
        history = parse_history(content, filename, unit=unit)
        digest = hashlib.sha256(content).hexdigest()
        history_id = "history-" + hashlib.sha256((digest + unit).encode()).hexdigest()[:24]
        folder = self._history_path(history_id)
        metadata = dict(history_id=history_id, filename=filename, unit=unit, sha256=digest,
                        uploaded_at=_now(), summary=history["summary"], warnings=history.get("warnings", []), available=True)
        with self.lock:
            folder.mkdir(parents=True, exist_ok=True)
            original = folder / ("source" + suffix)
            if not original.exists():
                original.write_bytes(content)
            history.update(filename=filename, source_sha256=digest)
            _write(folder / "normalized.json", history)
            _write(folder / "metadata.json", metadata)
            _write(self.data_dir / "current.json", {"history_id": history_id})
        return metadata

    def history(self, history_id="", include_records=False):
        if not history_id:
            if not (self.data_dir / "current.json").is_file():
                return {"available": False}
            history_id = _read(self.data_dir / "current.json")["history_id"]
        folder = self._history_path(history_id)
        if not (folder / "metadata.json").is_file():
            raise ValueError("未找到历史输入，请重新上传。")
        data = _read(folder / "metadata.json")
        if include_records:
            data["records"] = _read(folder / "normalized.json")["records"]
            data["records_unit"] = "万辆"
        return data

    def start(self, payload):
        if payload.get("task", "monthly") not in {"monthly", "rolling"}:
            raise ValueError("此执行器用于月度基准和滚动预测。")
        metadata = self.history(str(payload.get("history_id", "")))
        if not metadata.get("available"):
            raise ValueError("请先接入历史销量文件。")
        as_of = str(payload.get("as_of_date", ""))
        datetime.strptime(as_of, "%Y-%m-%d")
        if as_of > _now()[:10]:
            raise ValueError("信息截止日期不能晚于当前上海日期。")
        year, annual = payload.get("target_year"), payload.get("annual_targets")
        if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2100:
            raise ValueError("目标年份无效。")
        if not isinstance(annual, dict) or str(year) not in {str(k) for k in annual}:
            raise ValueError("目标年度采用值必须由用户提供。")
        if payload.get("allow_draft") is not True:
            raise ValueError("请明确确认本次运行属于基准预测试算。")
        package = SkillRegistry([self.skill_dir.parent]).get(self.skill_dir.name)
        for required in ("SKILL.md", "references/input-contract.md", "references/monthly-input.md", "references/annual-monthly.md", "references/nev-penetration.md", "references/output-formats.md"):
            package.resolve(required)
        run_id = "forecast-" + datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
        ctx = SkillRunContext(package, self.run_dir, run_id)
        snapshot = ctx.working_dir / "skill-package" / package.skill_id
        shutil.copytree(package.root, snapshot, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        pinned = SkillRegistry([snapshot.parent]).get(package.skill_id)
        if pinned.package_hash != package.package_hash:
            raise ValueError("Skill包在任务建立期间发生变化，请重试。")
        source = self._history_path(metadata["history_id"])
        suffix = Path(metadata["filename"]).suffix.lower()
        shutil.copy2(source / ("source" + suffix), ctx.inputs_dir / ("history" + suffix))
        shutil.copy2(source / "normalized.json", ctx.inputs_dir / "history.json")
        request = dict(history_id=metadata["history_id"], target_year=year, annual_targets=annual,
                       as_of_date=as_of, allow_draft=True, task=payload.get("task", "monthly"),
                       question=str(payload.get("question", ""))[:12000], filename=metadata["filename"])
        _write(ctx.inputs_dir / "request.json", request)
        _write(ctx.working_dir / "package-manifest.json", {"hash": pinned.package_hash, "resources": pinned.resources()})
        files = ("utils/passenger_forecast.py", "utils/passenger_forecast_jobs.py", "utils/passenger_forecast_exports.py", "scripts/export_passenger_forecast.mjs")
        _write(ctx.working_dir / "implementation.json", {f: _digest(self.project_dir / f) for f in files})
        titles = [("input", "读取Excel与口径检查"), ("forecast", "计算年度约束与渗透率"), ("validate", "独立校验月度与年度闭合"), ("export", "生成Excel与可编辑图表"), ("delivery", "保存结果与执行记录")]
        ctx.set_plan([dict(id=k, title=t, success_criteria=t + "且持久化独立证据", depends_on=[] if i == 0 else [titles[i-1][0]]) for i, (k, t) in enumerate(titles)])
        _write(self.run_dir / "latest.json", {"run_id": run_id})
        self._launch(run_id)
        return self.get(run_id)

    def _launch(self, run_id):
        with self.lock:
            if run_id in self.active:
                return
            self.active.add(run_id)
        Thread(target=self._execute, args=(run_id,), daemon=True, name=run_id).start()

    def resume(self, run_id):
        root = self._run_path(run_id)
        if _read(root / "run-state.json").get("status") == "completed":
            return self.get(run_id)
        versions = _read(root / "working/implementation.json")
        if any(_digest(self.project_dir / f) != h for f, h in versions.items()):
            raise ValueError("执行程序版本已更新，请重新运行；旧任务与证据保留。")
        self._launch(run_id)
        return self.get(run_id)

    def _execute(self, run_id):
        ctx, stage = None, "input"
        try:
            root = self._run_path(run_id)
            snapshot = root / "working/skill-package" / self.skill_dir.name
            package = SkillRegistry([snapshot.parent]).get(self.skill_dir.name)
            ctx = SkillRunContext(package, self.run_dir, run_id)
            state = ctx.load_state()
            if package.package_hash != state["package_hash"]:
                raise ValueError("锁定Skill包版本不一致。")
            state.update(status="running", error="")
            ctx.save_state(state)
            request, history = _read(ctx.inputs_dir / "request.json"), _read(ctx.inputs_dir / "history.json")
            ctx.update_task(stage, "running", "读取业务输入和来源")
            original = ctx.inputs_dir / ('history' + Path(request['filename']).suffix.lower())
            reparsed = parse_history(original.read_bytes(), request['filename'], unit=history['input_unit'])
            if reparsed['sha256'] != history['sha256'] or reparsed['records'] != history['records']:
                raise ValueError('规范化月度数据与原Excel/CSV不一致，请重新上传。')
            ctx.update_task(stage, "completed", f"读取{len(history['records'])}个月；已发布月份作为实际输入", ["inputs/history.json", "working/package-manifest.json"])
            stage = "forecast"
            ctx.update_task(stage, "running", "按技能规则计算季节性与新能源趋势")
            result = build_forecast(history, request["target_year"], request["annual_targets"], request["as_of_date"], allow_draft=True)
            result.update(run_id=run_id, source_filename=request["filename"], package_hash=package.package_hash)
            _write(ctx.working_dir / "result.json", result)
            ctx.update_task(stage, "completed", f"{result['year']}年{len(result['rows'])}个月，年度人工采用值保持", ["working/result.json"])
            stage = "validate"
            ctx.update_task(stage, "running", "独立核对闭合、边界和输入保持")
            validation = validate_forecast(result, history, request["annual_targets"])
            _write(ctx.working_dir / "calculation-validation.json", validation)
            if validation.get("status") != "passed":
                raise ValueError("预测数值验收失败：" + json.dumps(validation, ensure_ascii=False))
            ctx.update_task(stage, "completed", "数值验收通过", ["working/calculation-validation.json"])
            stage = "export"
            ctx.update_task(stage, "running", "生成同源Excel与PowerPoint原生图表")
            for attempt in range(2):
                artifacts = export_forecast(result, history, ctx.outputs_dir)
                export_check = validate_exports(artifacts, result)
                _write(ctx.working_dir / "export-validation.json", export_check)
                if export_check.get("status") == "passed":
                    break
                ctx.checkpoint("导出验收失败，有限重试", {"attempt": attempt + 1, "validation": export_check})
            if export_check.get("status") != "passed":
                raise ValueError("下载文件验收失败：" + json.dumps(export_check, ensure_ascii=False))
            for a in artifacts:
                ctx.register_artifact(Path(a["path"]), a["kind"])
                ctx.record_artifact_validation(Path(a["path"]), "forecast_native_charts", True, export_check)
            ctx.update_task(stage, "completed", "文件数据与原生图表通过核验", ["working/export-validation.json"])
            stage = "delivery"
            ctx.update_task(stage, "running", "保存结果和下载指纹")
            csv_path = ctx.outputs_dir / "forecast.csv"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["年份", "月份", "数据性质", "乘用车总量_万辆", "新能源渗透率_%", "新能源销量_万辆", "非新能源销量_万辆"])
                for r in result["rows"]:
                    writer.writerow([result["year"], r["month"], "已发布实际" if r["status"] == "provided" else "规则预测（试算）", r["total"], r["penetration"], r["nev"], r["traditional"]])
            artifacts.append(dict(path=str(csv_path), kind="csv", label="下载CSV"))
            delivery = []
            for a in artifacts:
                path = Path(a["path"]).resolve()
                path.relative_to(ctx.outputs_dir.resolve())
                kind = path.suffix.lower()[1:]
                delivery.append(dict(path=path.relative_to(root).as_posix(), kind=kind, label=a["label"], sha256=_digest(path), url=f"/api/forecast/download?run_id={run_id}&artifact={kind}"))
            _write(ctx.working_dir / "delivery.json", delivery)
            evidence = ['inputs/history.json', 'inputs/request.json', original.relative_to(root).as_posix(),
                        'working/result.json', 'working/calculation-validation.json', 'working/export-validation.json', 'working/delivery.json']
            _write(ctx.working_dir / 'evidence.json', {name: _digest(root / name) for name in evidence})
            state = ctx.load_state()
            state['evidence_manifest_sha256'] = _digest(ctx.working_dir / 'evidence.json')
            ctx.save_state(state)
            ctx.update_task(stage, "completed", "基准试算已保存；业务口径待确认", ["working/delivery.json"])
            ctx.validate([a["path"] for a in delivery] + ["working/result.json", "working/calculation-validation.json", "working/export-validation.json"])
            if self.on_complete:
                try:
                    project_id = self.on_complete(self.get(run_id), request)
                    state = ctx.load_state()
                    state["project_id"] = project_id
                    ctx.save_state(state)
                except Exception as exc:
                    ctx.checkpoint("项目列表保存异常；结果仍可恢复", {"error": str(exc)})
        except Exception as exc:
            if ctx:
                ctx.update_task(stage, "failed", str(exc)[:950])
                state = ctx.load_state()
            else:
                state = _read(self._run_path(run_id) / "run-state.json")
            state.update(status="failed", error=str(exc)[:3000], validation={"status": "failed", "checks": [{"id": stage, "passed": False, "detail": str(exc)[:1000]}]})
            _write(self._run_path(run_id) / "run-state.json", state)
        finally:
            with self.lock:
                self.active.discard(run_id)

    def get(self, run_id=""):
        if not run_id:
            if not (self.run_dir / "latest.json").is_file():
                return {"available": False}
            run_id = _read(self.run_dir / "latest.json")["run_id"]
        root = self._run_path(run_id)
        state = _read(root / "run-state.json")
        status = state["status"]
        if status == "running" and run_id not in self.active:
            status, state["error"] = "failed", "服务重启中断了任务，可恢复；输入与检查点已保留。"
        steps = state.get("plan", [])
        current = next((s for s in steps if s["status"] in {"running", "failed"}), None)
        response = dict(available=True, run_id=run_id, status=status, stage=current["title"] if current else "基准试算已完成" if status == "completed" else "准备执行",
                        steps=steps, error=state.get("error", ""), validation=state.get("validation", {}), created_at=state.get("created_at"), updated_at=state.get("updated_at"),
                        project_id=state.get("project_id", ""), execution_mode="skill_rule_baseline", package_hash=state["package_hash"], artifacts=[])
        if status == "completed" and state.get("validation", {}).get("status") == "passed":
            manifest = root / 'working/evidence.json'
            if not manifest.is_file() or _digest(manifest) != state.get('evidence_manifest_sha256'):
                raise ValueError('预测验收证据已变更，禁止展示与下载，请重新执行。')
            for relative, digest in _read(manifest).items():
                evidence = (root / relative).resolve()
                evidence.relative_to(root.resolve())
                if not evidence.is_file() or _digest(evidence) != digest:
                    raise ValueError('预测输入或结果已变更，与已验收文件不一致，请重新执行。')
            response["result"] = _read(root / "working/result.json")
            response["artifacts"] = [{k: a[k] for k in ("kind", "label", "url")} for a in _read(root / "working/delivery.json")]
        return response

    def download(self, run_id, kind):
        root, job = self._run_path(run_id), self.get(run_id)
        if job["status"] != "completed" or job["validation"].get("status") != "passed":
            raise ValueError("预测尚未通过验收，不能下载。")
        artifact = next((a for a in _read(root / "working/delivery.json") if a["kind"] == kind), None)
        if not artifact:
            raise ValueError("未找到该下载文件。")
        path = (root / artifact["path"]).resolve()
        path.relative_to((root / "outputs").resolve())
        if _digest(path) != artifact["sha256"]:
            raise ValueError("下载文件已变更，请重新执行验收。")
        return path
