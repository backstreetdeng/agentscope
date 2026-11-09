"""BCI-004 · 洞察档案接口编排。

路由尚未挂到 `app.py`（D6 才改共用文件），本模块可直接被脚本或测试调用：

- `template()`                 模板分组与维度
- `respondents()`              受访者列表 + 每人档案状态
- `detail()`                   单人档案详情（含证据刷新）
- `generate()`                 创建单人 / 勾选 / 缺失 / 全量运行
- `run_status()`               运行状态轮询
- `quote()`                    「找原话」
- `export()`                   xlsx / md 二进制

失败统一抛 `ApiError`，由路由层转成
`{"ok": false, "error": {"code", "message", ...}}`；成功返回 `{"ok": true, "data": ...}`。
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime, timezone
from typing import Any, Iterable

from competitor_insight.server.archive_store import (
    ArchiveRecord,
    ArchiveSummary,
    QueryResult,
    RunRecord,
)
from competitor_insight.server.export_service import (
    MD_CONTENT_TYPE,
    XLSX_CONTENT_TYPE,
    build_md,
    build_xlsx,
    completeness,
    display_value,
    score_source,
)
from competitor_insight.server.quote_service import QuoteError, QuoteService, escape_like
from competitor_insight.server.source_map import SourceMapError
from competitor_insight.server.template_registry import (
    ARCHIVE_TEMPLATE_ID,
    TemplateBundle,
    TemplateRegistry,
    TemplateRegistryError,
)

MODES = ("single", "selected", "missing", "all")


class ApiError(RuntimeError):
    def __init__(
        self, code: str, message: str, status: int = 400, **extra: Any
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.extra = extra

    def to_payload(self) -> dict[str, Any]:
        return {"ok": False, "error": {"code": self.code, "message": str(self), **self.extra}}


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


class PostgresRespondentDirectory:
    """只读 `user_insight.interview`，只暴露编号 / 城市 / 车型 / 购车类型。"""

    FIELDS = (
        "interview_id",
        "coalesce(respondent_code, interview_id) AS respondent_code",
        "city",
        "vehicle_model",
        "purchase_type",
    )

    def __init__(self, connect_fn) -> None:
        self._connect = connect_fn

    @staticmethod
    def _where(keyword: str | None) -> tuple[str, tuple[Any, ...]]:
        if not keyword:
            return "", ()
        pattern = f"%{escape_like(keyword)}%"
        return (
            "WHERE (interview_id ILIKE %s ESCAPE '\\'"
            " OR coalesce(respondent_code, '') ILIKE %s ESCAPE '\\'"
            " OR coalesce(city, '') ILIKE %s ESCAPE '\\'"
            " OR coalesce(vehicle_model, '') ILIKE %s ESCAPE '\\')",
            (pattern, pattern, pattern, pattern),
        )

    def count(self, keyword: str | None = None) -> int:
        where, params = self._where(keyword)
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM user_insight.interview {where}", params)
                return int(cur.fetchone()[0])
        finally:
            conn.close()

    def list(self, keyword: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        where, params = self._where(keyword)
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {', '.join(self.FIELDS)} FROM user_insight.interview {where}"
                    " ORDER BY interview_id LIMIT %s OFFSET %s",
                    (*params, limit, offset),
                )
                return [
                    {
                        "interview_id": row[0],
                        "respondent_code": row[1],
                        "city": row[2],
                        "vehicle_model": row[3],
                        "purchase_type": row[4],
                    }
                    for row in cur.fetchall()
                ]
        finally:
            conn.close()

    def ids(self) -> list[str]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT interview_id FROM user_insight.interview ORDER BY interview_id")
                return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    def get_many(self, interview_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        ids = list(interview_ids)
        if not ids:
            return {}
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {', '.join(self.FIELDS)} FROM user_insight.interview"
                    " WHERE interview_id = ANY(%s)",
                    (ids,),
                )
                return {
                    row[0]: {
                        "interview_id": row[0],
                        "respondent_code": row[1],
                        "city": row[2],
                        "vehicle_model": row[3],
                        "purchase_type": row[4],
                    }
                    for row in cur.fetchall()
                }
        finally:
            conn.close()


class ArchiveService:
    def __init__(
        self,
        store,
        *,
        generator=None,
        registry: TemplateRegistry | None = None,
        directory=None,
        quotes: QuoteService | None = None,
        template_id: str = ARCHIVE_TEMPLATE_ID,
        background: bool = True,
        max_workers: int = 2,
    ) -> None:
        self.store = store
        self.registry = registry or TemplateRegistry()
        self.template_id = template_id
        self.background = background
        self.max_workers = max(1, int(max_workers))
        self._generator = generator
        self._directory = directory
        self._quotes = quotes
        self._lock = threading.Lock()
        self._active_run: str | None = None

    # ------------------------------------------------------------------ 模板

    def template(self, template_id: str | None = None) -> dict[str, Any]:
        bundle = self._ready_bundle(template_id)
        dimensions = [
            {
                key: dim[key]
                for key in (
                    "id",
                    "name",
                    "group",
                    "type",
                    "required",
                    "options",
                    "description",
                    "qualified",
                )
                if key in dim
            }
            for dim in bundle.definition.get("dimensions", [])
        ]
        return _ok(
            {
                "template_id": bundle.template_id,
                "label": bundle.label,
                "version": bundle.version,
                "status": bundle.status,
                "dimension_count": bundle.dimension_count,
                "source_map_ready": bundle.source_map is not None,
                "groups": [dict(group) for group in bundle.definition.get("groups", [])],
                "dimensions": dimensions,
            }
        )

    # ---------------------------------------------------------------- 受访者

    def respondents(
        self,
        template_id: str | None = None,
        keyword: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        bundle = self._ready_bundle(template_id)
        limit = min(max(int(limit), 1), 200)
        offset = max(int(offset), 0)

        directory = self._directory_obj()
        try:
            total = directory.count(keyword)
            rows = directory.list(keyword, limit, offset)
        except ApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ApiError("database_unavailable", "受访者查询失败，数据库不可用", 503) from exc

        summaries = self.store.list_archives(
            bundle.template_id, template_version=bundle.version
        )
        by_id: dict[str, ArchiveSummary] = {item.interview_id: item for item in summaries.items}

        items: list[dict[str, Any]] = []
        for row in rows:
            interview_id = row["interview_id"]
            summary = by_id.get(interview_id)
            archive = self._archive_summary(bundle, summary) if summary else None
            items.append({**row, "archive": archive})

        return _ok(
            {
                "template_id": bundle.template_id,
                "template_version": bundle.version,
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": items,
            }
        )

    def _archive_summary(
        self, bundle: TemplateBundle, summary: ArchiveSummary
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": summary.status,
            "version": summary.template_version,
            "coverage_required": summary.coverage_required,
            "field_count": summary.field_count,
            "generated_at": summary.generated_at,
        }
        detail = self.store.get_archive(
            summary.interview_id, bundle.template_id, summary.template_version
        )
        if detail.items:
            payload["completeness"] = completeness(bundle.definition, detail.items[0])
        return payload

    # ------------------------------------------------------------------ 详情

    def detail(
        self,
        interview_id: str,
        template_id: str | None = None,
        version: str | None = None,
        revision: int | None = None,
    ) -> dict[str, Any]:
        bundle = self._ready_bundle(template_id)
        if not interview_id:
            raise ApiError("invalid_interview", "interview_id 不能为空")

        result: QueryResult = self.store.get_archive(
            interview_id, bundle.template_id, version, revision
        )
        if not result.items:
            return _ok(
                {
                    "template": self._template_summary(bundle, None),
                    "archive": None,
                    "fields": [],
                }
            )

        record: ArchiveRecord = result.items[0]
        snapshot = (
            record.template_snapshot
            if record.template_snapshot.get("dimensions")
            else bundle.definition
        )
        fields = [self._field_payload(interview_id, field) for field in record.fields]
        fields = self._order_fields(snapshot, fields)

        return _ok(
            {
                "template": self._template_summary(bundle, record),
                "archive": {
                    "archive_id": record.archive_id,
                    "status": record.status,
                    "revision": record.revision,
                    "coverage_required": record.coverage_required,
                    "completeness": completeness(snapshot, record),
                    "generated_at": record.generated_at,
                    "model": record.model,
                    "prompt_version": record.prompt_version,
                    "run_id": record.run_id,
                },
                "fields": fields,
            }
        )

    def _field_payload(self, interview_id: str, field) -> dict[str, Any]:
        refs = field.evidence_refs or []
        if refs and self._quotes is not None:
            try:
                refs = self._quotes.refresh_refs(interview_id, refs)
            except Exception:  # noqa: BLE001
                # 刷新失败不丢档案：保留快照，前端仍可显示「来源已失效」以外的事实
                refs = field.evidence_refs or []
        return {
            "dimension_id": field.dimension_id,
            "group_id": field.group_id,
            "fill_mode": field.fill_mode,
            "value_text": field.value_text,
            "value_json": field.value_json,
            "display_value": display_value(field),
            "source_ref": field.source_ref,
            "no_data_reason": field.no_data_reason,
            "confidence": field.confidence,
            "review_status": field.review_status,
            "evidence_refs": refs,
            "score_source": score_source(field),
        }

    @staticmethod
    def _order_fields(
        template: dict[str, Any], fields: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        order = {dim.get("id"): index for index, dim in enumerate(template.get("dimensions", []))}
        return sorted(fields, key=lambda item: order.get(item["dimension_id"], len(order)))

    @staticmethod
    def _template_summary(
        bundle: TemplateBundle, record: ArchiveRecord | None
    ) -> dict[str, Any]:
        snapshot = record.template_snapshot if record else bundle.definition
        return {
            "template_id": record.template_id if record else bundle.template_id,
            "version": record.template_version if record else bundle.version,
            "name": snapshot.get("name") or bundle.label,
        }

    # ------------------------------------------------------------ 生成与轮询

    def generate(
        self,
        interview_ids: Iterable[str],
        template_id: str | None = None,
        mode: str = "selected",
        force: bool = False,
    ) -> dict[str, Any]:
        bundle = self._ready_bundle(template_id)
        if bundle.source_map is None:
            raise ApiError(
                "template_not_generatable",
                f"模板「{bundle.label}」缺少题项映射（source-map），暂不支持自动生成；"
                "请切换到「用户洞察档案」模板",
                400,
            )
        if mode not in MODES:
            raise ApiError("invalid_mode", f"mode 必须是 {MODES} 之一")

        requested = _dedupe(interview_ids)
        if mode in ("single", "selected") and not requested:
            raise ApiError("empty_selection", "未提供 interview_ids")

        if mode in ("missing", "all"):
            directory = self._directory_obj()
            try:
                all_ids = directory.ids()
            except Exception as exc:  # noqa: BLE001
                raise ApiError("database_unavailable", "读取受访者失败，数据库不可用", 503) from exc
            if mode == "all":
                requested = all_ids
            else:
                summaries = self._summaries(bundle)
                ready = {item.interview_id for item in summaries if item.status == "ready"}
                requested = [iid for iid in all_ids if iid not in ready]

        skipped: list[str] = []
        targets = requested
        if not force:
            ready = {item.interview_id for item in self._summaries(bundle) if item.status == "ready"}
            skipped = [iid for iid in requested if iid in ready]
            targets = [iid for iid in requested if iid not in ready]

        with self._lock:
            if self._active_run:
                raise ApiError(
                    "run_in_progress",
                    "已有归档任务在运行，请轮询该任务",
                    409,
                    run_id=self._active_run,
                )
            run_id = str(uuid.uuid4())
            self._active_run = run_id

        try:
            self.store.create_run(
                RunRecord(
                    run_id=run_id,
                    template_id=bundle.template_id,
                    template_version=bundle.version,
                    mode=mode,
                    request_json={
                        "interview_ids": list(requested),
                        "mode": mode,
                        "force": bool(force),
                    },
                    status="queued",
                    total=len(targets),
                    created_by="local",
                )
            )
            if not targets:
                self.store.update_run(
                    run_id, status="completed", finished_at=_now_iso()
                )
                with self._lock:
                    self._active_run = None
            elif self.background:
                threading.Thread(
                    target=self._execute_run,
                    args=(run_id, list(targets)),
                    name=f"bci-archive-{run_id[:8]}",
                    daemon=True,
                ).start()
            else:
                self._execute_run(run_id, list(targets))
        except Exception:
            with self._lock:
                self._active_run = None
            raise

        return _ok(
            {
                "run_id": run_id,
                "status": "queued" if targets else "completed",
                "mode": mode,
                "total": len(targets),
                "skipped": len(skipped),
            }
        )

    def _execute_run(self, run_id: str, targets: list[str]) -> None:
        done = failed = 0
        try:
            self.store.update_run(run_id, status="running")
            if self.max_workers > 1 and len(targets) > 1:
                with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                    futures = [pool.submit(self._generate_one, run_id, iid) for iid in targets]
                    for future in as_completed(futures):
                        if future.result():
                            done += 1
                        else:
                            failed += 1
            else:
                for interview_id in targets:
                    if self._generate_one(run_id, interview_id):
                        done += 1
                    else:
                        failed += 1
            status = "completed" if failed == 0 else ("partial" if done else "failed")
            self.store.update_run(
                run_id,
                status=status,
                done=done,
                failed=failed,
                finished_at=_now_iso(),
            )
        except Exception as exc:  # noqa: BLE001
            try:
                self.store.update_run(
                    run_id,
                    status="failed",
                    done=done,
                    failed=failed,
                    error_text=exc.__class__.__name__,
                    finished_at=_now_iso(),
                )
            except Exception:  # noqa: BLE001
                pass
        finally:
            with self._lock:
                self._active_run = None

    def _generate_one(self, run_id: str, interview_id: str) -> bool:
        try:
            self.store.update_run_item(run_id, interview_id, "running")
            draft = self._generator_obj().generate(interview_id)
            if draft.run_id != run_id:
                draft = replace(draft, run_id=run_id)
            self.store.save_archive(draft)
            self.store.update_run_item(run_id, interview_id, "done")
            return True
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", None) or exc.__class__.__name__
            try:
                self.store.update_run_item(run_id, interview_id, "failed", str(code))
            except Exception:  # noqa: BLE001
                pass
            return False

    def run_status(self, run_id: str) -> dict[str, Any]:
        if not run_id:
            raise ApiError("invalid_run", "run_id 不能为空")
        result = self.store.get_run(run_id)
        if not result.items:
            raise ApiError("run_not_found", f"运行不存在：{run_id}", 404)

        payload = result.items[0]
        run = payload["run"]
        run_data = asdict(run) if is_dataclass(run) else dict(run)
        total = int(run_data.get("total") or 0)
        done = int(run_data.get("done") or 0)
        failed = int(run_data.get("failed") or 0)
        run_data["progress"] = (
            round((done + failed) / total * 100, 2) if total else 0.0
        )
        run_data["items"] = payload["items"]
        return _ok(run_data)

    # ------------------------------------------------------------------ 原话

    def quote(
        self,
        interview_ids: str | list[str] | None,
        keyword: str,
        limit: int = 50,
        template_id: str | None = None,
    ) -> dict[str, Any]:
        bundle = self._ready_bundle(template_id)
        if isinstance(interview_ids, str):
            persons = [p.strip() for p in interview_ids.split(",") if p.strip()]
        else:
            persons = [str(p).strip() for p in (interview_ids or []) if str(p).strip()] or None
        archive_fields: list[dict[str, Any]] = []
        if persons and len(persons) == 1:
            detail = self.detail(persons[0], bundle.template_id)["data"]
            if detail["archive"]:
                archive_fields = [
                    {"dimension_id": field["dimension_id"], "value_text": field["value_text"]}
                    for field in detail["fields"]
                    if field["value_text"]
                ]
        try:
            data = self._quotes_obj().search(
                persons, keyword, limit=limit, archive_fields=archive_fields
            )
        except QuoteError as exc:
            raise ApiError(exc.code, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise ApiError("database_unavailable", "原话查询失败，数据库不可用", 503) from exc
        return _ok(data)

    # ------------------------------------------------------------------ 导出

    def export(
        self,
        interview_ids: Iterable[str],
        template_id: str | None = None,
        version: str | None = None,
        format: str = "xlsx",
    ) -> dict[str, Any]:
        fmt = (format or "").lower()
        if fmt not in ("xlsx", "md"):
            raise ApiError("unsupported_format", "format 只支持 xlsx 或 md")

        ids = _dedupe(interview_ids)
        if not ids:
            raise ApiError("empty_selection", "至少选择一位受访者再导出")
        if fmt == "md" and len(ids) != 1:
            raise ApiError("md_single_only", "MD 导出只支持单人", 400)

        bundle = self._ready_bundle(template_id)
        archives: list[ArchiveRecord] = []
        missing: list[str] = []
        for interview_id in ids:
            result = self.store.get_archive(interview_id, bundle.template_id, version)
            if not result.items:
                missing.append(interview_id)
            else:
                archives.append(result.items[0])
        if missing:
            raise ApiError(
                "archive_missing",
                f"以下受访者没有档案：{'、'.join(missing)}",
                409,
                interview_ids=missing,
            )

        respondents = self._respondent_meta(ids)
        if fmt == "xlsx":
            data, filename = build_xlsx(bundle.definition, archives, respondents)
            content_type = XLSX_CONTENT_TYPE
        else:
            respondent = respondents.get(ids[0], {"interview_id": ids[0]})
            data, filename = build_md(bundle.definition, archives[0], respondent)
            content_type = MD_CONTENT_TYPE

        return _ok(
            {
                "format": fmt,
                "content_type": content_type,
                "filename": filename,
                "bytes": len(data),
                "data": data,
            }
        )

    def _respondent_meta(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        default = {interview_id: {"interview_id": interview_id} for interview_id in ids}
        directory = self._directory
        if directory is None:
            return default
        try:
            return {**default, **directory.get_many(ids)}
        except Exception:  # noqa: BLE001
            return default

    # ------------------------------------------------------------------ 内部

    def _ready_bundle(self, template_id: str | None) -> TemplateBundle:
        try:
            return self.registry.load_ready(template_id or self.template_id)
        except (TemplateRegistryError, SourceMapError) as exc:
            status = 404 if "清单中没有" in str(exc) else 400
            raise ApiError("template_not_ready", str(exc), status) from exc

    def _summaries(self, bundle: TemplateBundle) -> list[ArchiveSummary]:
        result = self.store.list_archives(
            bundle.template_id, template_version=bundle.version
        )
        return list(result.items)

    def _directory_obj(self):
        if self._directory is None:
            from competitor_insight.server import db as db_module

            self._directory = PostgresRespondentDirectory(db_module.connect)
        return self._directory

    def _generator_obj(self):
        if self._generator is None:
            from competitor_insight.server import db as db_module
            from competitor_insight.server.archive_generator import (
                ArchiveGenerator,
                PostgresInterviewSource,
            )
            from competitor_insight.server.llm_client import build_deepseek_client

            client = build_deepseek_client()
            self._generator = ArchiveGenerator(
                PostgresInterviewSource(db_module.connect),
                registry=self.registry,
                llm=client,
                model=getattr(client, "model", None),
            )
        return self._generator

    def _quotes_obj(self):
        if self._quotes is None:
            from competitor_insight.server import db as db_module

            self._quotes = QuoteService(db_module.connect)
        return self._quotes


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
