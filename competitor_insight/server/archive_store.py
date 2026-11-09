"""BCI-004 · 档案存储层。

两种实现共用同一接口：
- `PostgresArchiveStore`：写 `bci.archive*`（生产路径）；
- `FileArchiveStore`：写本地 JSON 目录（DDL 不可用或单测时的等价实现）。

共同语义：
- 同一（受访者, 模板, 版本）重跑时原地覆盖当前档案（revision 不变、字段重建），不留修订历史；
  重跑过程仍记录于 `bci.archive_run` / `archive_run_item`（用户 2026-11-09 拍板）；
- 一次保存 = 一个事务，字段写入失败则整份档案不落库；
- 查询返回三态 `QueryResult`：`success|partial|failed`，并带 应查/实查/命中 计数，
  空结果不会被伪装成成功，也不把「未覆盖」写成 0。
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from competitor_insight.server.db import transaction

ARCHIVE_STATUSES = ("ready", "partial", "failed", "stale")
FILL_MODES = ("metadata", "tag", "derived", "llm", "none")
REVIEW_STATUSES = ("auto", "ok", "suspect", "missing")
RUN_STATUSES = ("queued", "running", "completed", "partial", "failed", "cancelled")
RUN_ITEM_STATUSES = ("queued", "running", "done", "failed", "skipped")


class ArchiveStoreError(RuntimeError):
    """存储层校验或写入失败。"""


@dataclass(frozen=True)
class ArchiveFieldRecord:
    dimension_id: str
    group_id: str
    fill_mode: str
    value_text: str | None = None
    value_json: Any = None
    source_ref: dict[str, Any] = field(default_factory=dict)
    no_data_reason: str | None = None
    confidence: float | None = None
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    review_status: str = "auto"

    def validate(self) -> None:
        if not self.dimension_id:
            raise ArchiveStoreError("dimension_id 不能为空")
        if not self.group_id:
            raise ArchiveStoreError(f"{self.dimension_id} 缺少 group_id")
        if self.fill_mode not in FILL_MODES:
            raise ArchiveStoreError(f"{self.dimension_id} fill_mode 非法：{self.fill_mode}")
        if self.review_status not in REVIEW_STATUSES:
            raise ArchiveStoreError(f"{self.dimension_id} review_status 非法：{self.review_status}")
        if self.fill_mode == "none" and not (self.no_data_reason or "").strip():
            raise ArchiveStoreError(f"{self.dimension_id} 无来源维必须写 no_data_reason")
        if self.fill_mode != "none" and self.no_data_reason:
            raise ArchiveStoreError(f"{self.dimension_id} 非无来源维不应写 no_data_reason")


@dataclass(frozen=True)
class ArchiveDraft:
    interview_id: str
    template_id: str
    template_version: str
    template_snapshot: dict[str, Any]
    status: str
    coverage_required: float
    fields: tuple[ArchiveFieldRecord, ...]
    run_id: str | None = None
    model: str | None = None
    prompt_version: str | None = None

    def validate(self) -> None:
        if not self.interview_id:
            raise ArchiveStoreError("interview_id 不能为空")
        if self.status not in ARCHIVE_STATUSES:
            raise ArchiveStoreError(f"archive.status 非法：{self.status}")
        if not self.fields:
            raise ArchiveStoreError("档案必须至少包含一个维度")
        seen: set[str] = set()
        for item in self.fields:
            item.validate()
            if item.dimension_id in seen:
                raise ArchiveStoreError(f"维度重复：{item.dimension_id}")
            seen.add(item.dimension_id)


@dataclass(frozen=True)
class ArchiveRecord:
    archive_id: int | str
    interview_id: str
    template_id: str
    template_version: str
    template_snapshot: dict[str, Any]
    revision: int
    status: str
    coverage_required: float
    fields: tuple[ArchiveFieldRecord, ...]
    run_id: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    generated_at: str | None = None


@dataclass(frozen=True)
class ArchiveSummary:
    archive_id: int | str
    interview_id: str
    template_id: str
    template_version: str
    revision: int
    status: str
    coverage_required: float
    field_count: int
    generated_at: str | None = None


@dataclass(frozen=True)
class QueryResult:
    status: str
    expected: int | None
    checked: int
    hit: int
    items: tuple[Any, ...]
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "should_check": self.expected,
            "checked": self.checked,
            "hit": self.hit,
            "reasons": list(self.reasons),
        }


def build_query_result(
    items: list[Any],
    *,
    expected: int | None = None,
    checked: int | None = None,
    reasons: list[str] | None = None,
) -> QueryResult:
    """三态换算：有明确应查数时按命中判定；无应查数时只表示查询本身成功。"""
    hit = len(items)
    if expected is None:
        status = "success"
    elif hit == expected:
        status = "success"
    elif hit == 0:
        status = "failed"
    else:
        status = "partial"
    return QueryResult(
        status=status,
        expected=expected,
        checked=hit if checked is None else checked,
        hit=hit,
        items=tuple(items),
        reasons=tuple(reasons or ()),
    )


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    template_id: str
    template_version: str
    mode: str
    request_json: dict[str, Any]
    status: str
    total: int = 0
    done: int = 0
    failed: int = 0
    model: str | None = None
    prompt_version: str | None = None
    error_text: str | None = None
    created_by: str = "local"
    generated_at: str | None = None
    finished_at: str | None = None


class ArchiveStore(Protocol):
    def save_archive(self, draft: ArchiveDraft) -> ArchiveRecord: ...

    def get_archive(
        self,
        interview_id: str,
        template_id: str,
        template_version: str | None = None,
        revision: int | None = None,
    ) -> QueryResult: ...

    def list_archives(
        self,
        template_id: str,
        template_version: str | None = None,
        status: str | None = None,
        expected: int | None = None,
    ) -> QueryResult: ...

    def create_run(self, record: RunRecord) -> None: ...

    def update_run(self, run_id: str, **changes: Any) -> None: ...

    def update_run_item(self, run_id: str, interview_id: str, status: str, error_text: str | None = None) -> None: ...

    def get_run(self, run_id: str) -> QueryResult: ...


def _validate_run_status(status: str) -> None:
    if status not in RUN_STATUSES:
        raise ArchiveStoreError(f"run.status 非法：{status}")


class PostgresArchiveStore:
    """生产实现：写 bci.archive*，全部使用参数化 SQL。"""

    def __init__(self, connect_fn) -> None:
        self._connect = connect_fn

    def _new_conn(self):
        return self._connect()

    def save_archive(self, draft: ArchiveDraft) -> ArchiveRecord:
        draft.validate()
        conn = self._new_conn()
        try:
            with transaction(conn) as cur:
                # 同一受访者+模板+版本串行化，避免并发覆盖冲突
                cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (f"{draft.interview_id}|{draft.template_id}|{draft.template_version}",),
                )
                # 覆盖语义（用户 2026-11-09 拍板）：同键只保留一份当前档案，
                # 重跑原行更新、字段重建，不留修订历史；重跑过程仍记录于 archive_run。
                cur.execute(
                    """
                    SELECT archive_id, revision FROM bci.archive
                    WHERE interview_id = %s AND template_id = %s AND template_version = %s
                    ORDER BY revision DESC LIMIT 1
                    """,
                    (draft.interview_id, draft.template_id, draft.template_version),
                )
                existing = cur.fetchone()
                if existing:
                    archive_id = existing[0]
                    revision = int(existing[1])
                    cur.execute(
                        """
                        UPDATE bci.archive
                        SET template_snapshot = %s::jsonb, run_id = %s, status = %s,
                            coverage_required = %s, model = %s, prompt_version = %s,
                            generated_at = now(), updated_at = now()
                        WHERE archive_id = %s
                        RETURNING generated_at
                        """,
                        (
                            json.dumps(draft.template_snapshot, ensure_ascii=False),
                            draft.run_id,
                            draft.status,
                            draft.coverage_required,
                            draft.model,
                            draft.prompt_version,
                            archive_id,
                        ),
                    )
                    generated_at = cur.fetchone()[0]
                    cur.execute("DELETE FROM bci.archive_field WHERE archive_id = %s", (archive_id,))
                else:
                    revision = 1
                    cur.execute(
                        """
                        INSERT INTO bci.archive
                            (interview_id, template_id, template_version, template_snapshot, run_id,
                             revision, status, coverage_required, model, prompt_version)
                        VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                        RETURNING archive_id, generated_at
                        """,
                        (
                            draft.interview_id,
                            draft.template_id,
                            draft.template_version,
                            json.dumps(draft.template_snapshot, ensure_ascii=False),
                            draft.run_id,
                            revision,
                            draft.status,
                            draft.coverage_required,
                            draft.model,
                            draft.prompt_version,
                        ),
                    )
                    archive_id, generated_at = cur.fetchone()

                for item in draft.fields:
                    cur.execute(
                        """
                        INSERT INTO bci.archive_field
                            (archive_id, dimension_id, group_id, fill_mode, value_text, value_json,
                             source_ref, no_data_reason, confidence, evidence_refs, review_status)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb, %s)
                        """,
                        (
                            archive_id,
                            item.dimension_id,
                            item.group_id,
                            item.fill_mode,
                            item.value_text,
                            json.dumps(item.value_json, ensure_ascii=False) if item.value_json is not None else None,
                            json.dumps(item.source_ref, ensure_ascii=False),
                            item.no_data_reason,
                            item.confidence,
                            json.dumps(item.evidence_refs, ensure_ascii=False),
                            item.review_status,
                        ),
                    )
        finally:
            conn.close()

        return ArchiveRecord(
            archive_id=archive_id,
            interview_id=draft.interview_id,
            template_id=draft.template_id,
            template_version=draft.template_version,
            template_snapshot=draft.template_snapshot,
            revision=revision,
            status=draft.status,
            coverage_required=draft.coverage_required,
            fields=draft.fields,
            run_id=draft.run_id,
            model=draft.model,
            prompt_version=draft.prompt_version,
            generated_at=generated_at.isoformat() if generated_at else None,
        )

    def get_archive(
        self,
        interview_id: str,
        template_id: str,
        template_version: str | None = None,
        revision: int | None = None,
    ) -> QueryResult:
        conn = self._new_conn()
        try:
            with conn.cursor() as cur:
                sql = [
                    "SELECT archive_id, interview_id, template_id, template_version, template_snapshot,",
                    "revision, status, coverage_required, run_id, model, prompt_version, generated_at",
                    "FROM bci.archive WHERE interview_id = %s AND template_id = %s",
                ]
                params: list[Any] = [interview_id, template_id]
                if template_version is not None:
                    sql.append("AND template_version = %s")
                    params.append(template_version)
                if revision is not None:
                    sql.append("AND revision = %s")
                    params.append(revision)
                else:
                    sql.append("AND status <> 'stale'")
                sql.append("ORDER BY revision DESC LIMIT 1")
                cur.execute(" ".join(sql), tuple(params))
                row = cur.fetchone()
                if row is None:
                    return build_query_result([], expected=1, checked=1, reasons=["未找到匹配档案"])
                record = self._row_to_record(cur, row)
        finally:
            conn.close()
        return build_query_result([record], expected=1, checked=1)

    def _row_to_record(self, cur, row) -> ArchiveRecord:
        archive_id = row[0]
        cur.execute(
            """
            SELECT dimension_id, group_id, fill_mode, value_text, value_json, source_ref,
                   no_data_reason, confidence, evidence_refs, review_status
            FROM bci.archive_field WHERE archive_id = %s ORDER BY group_id, dimension_id
            """,
            (archive_id,),
        )
        fields = tuple(
            ArchiveFieldRecord(
                dimension_id=f[0],
                group_id=f[1],
                fill_mode=f[2],
                value_text=f[3],
                value_json=f[4],
                source_ref=f[5] or {},
                no_data_reason=f[6],
                confidence=float(f[7]) if f[7] is not None else None,
                evidence_refs=f[8] or [],
                review_status=f[9],
            )
            for f in cur.fetchall()
        )
        return ArchiveRecord(
            archive_id=archive_id,
            interview_id=row[1],
            template_id=row[2],
            template_version=row[3],
            template_snapshot=row[4] or {},
            revision=row[5],
            status=row[6],
            coverage_required=float(row[7]),
            fields=fields,
            run_id=row[8],
            model=row[9],
            prompt_version=row[10],
            generated_at=row[11].isoformat() if row[11] else None,
        )

    def list_archives(
        self,
        template_id: str,
        template_version: str | None = None,
        status: str | None = None,
        expected: int | None = None,
    ) -> QueryResult:
        conn = self._new_conn()
        try:
            with conn.cursor() as cur:
                sql = [
                    "SELECT a.archive_id, a.interview_id, a.template_id, a.template_version, a.revision,",
                    "a.status, a.coverage_required, count(f.dimension_id), a.generated_at",
                    "FROM bci.archive a LEFT JOIN bci.archive_field f ON f.archive_id = a.archive_id",
                    "WHERE a.template_id = %s",
                ]
                params: list[Any] = [template_id]
                if template_version is not None:
                    sql.append("AND a.template_version = %s")
                    params.append(template_version)
                if status is not None:
                    sql.append("AND a.status = %s")
                    params.append(status)
                else:
                    sql.append("AND a.status <> 'stale'")
                sql.append("GROUP BY a.archive_id ORDER BY a.interview_id, a.revision DESC")
                cur.execute(" ".join(sql), tuple(params))
                items = [
                    ArchiveSummary(
                        archive_id=r[0],
                        interview_id=r[1],
                        template_id=r[2],
                        template_version=r[3],
                        revision=r[4],
                        status=r[5],
                        coverage_required=float(r[6]),
                        field_count=int(r[7]),
                        generated_at=r[8].isoformat() if r[8] else None,
                    )
                    for r in cur.fetchall()
                ]
        finally:
            conn.close()
        return build_query_result(items, expected=expected)

    def create_run(self, record: RunRecord) -> None:
        _validate_run_status(record.status)
        conn = self._new_conn()
        try:
            with transaction(conn) as cur:
                cur.execute(
                    """
                    INSERT INTO bci.archive_run
                        (run_id, template_id, template_version, mode, request_json, status,
                         total, done, failed, model, prompt_version, created_by)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.run_id,
                        record.template_id,
                        record.template_version,
                        record.mode,
                        json.dumps(record.request_json, ensure_ascii=False),
                        record.status,
                        record.total,
                        record.done,
                        record.failed,
                        record.model,
                        record.prompt_version,
                        record.created_by,
                    ),
                )
        finally:
            conn.close()

    def update_run(self, run_id: str, **changes: Any) -> None:
        allowed = {"status", "total", "done", "failed", "error_text", "model", "prompt_version", "finished_at"}
        unknown = set(changes) - allowed
        if unknown:
            raise ArchiveStoreError(f"update_run 不支持字段：{sorted(unknown)}")
        if "status" in changes:
            _validate_run_status(changes["status"])
        if not changes:
            return
        assignments = ", ".join(f"{key} = %s" for key in changes)
        conn = self._new_conn()
        try:
            with transaction(conn) as cur:
                cur.execute(f"UPDATE bci.archive_run SET {assignments} WHERE run_id = %s", (*changes.values(), run_id))
        finally:
            conn.close()

    def update_run_item(self, run_id: str, interview_id: str, status: str, error_text: str | None = None) -> None:
        if status not in RUN_ITEM_STATUSES:
            raise ArchiveStoreError(f"run_item.status 非法：{status}")
        conn = self._new_conn()
        try:
            with transaction(conn) as cur:
                cur.execute(
                    """
                    INSERT INTO bci.archive_run_item (run_id, interview_id, status, error_text)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (run_id, interview_id) DO UPDATE
                    SET status = EXCLUDED.status, error_text = EXCLUDED.error_text, updated_at = now()
                    """,
                    (run_id, interview_id, status, error_text),
                )
        finally:
            conn.close()

    def get_run(self, run_id: str) -> QueryResult:
        conn = self._new_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, template_id, template_version, mode, request_json, status,
                           total, done, failed, model, prompt_version, error_text, created_by,
                           created_at, finished_at
                    FROM bci.archive_run WHERE run_id = %s
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
                cur.execute(
                    "SELECT interview_id, status, error_text FROM bci.archive_run_item WHERE run_id = %s ORDER BY interview_id",
                    (run_id,),
                )
                items = [
                    {"interview_id": r[0], "status": r[1], "error_text": r[2]} for r in cur.fetchall()
                ]
                if row is None:
                    return build_query_result([], expected=1, checked=1, reasons=["任务不存在"])
                record = RunRecord(
                    run_id=row[0],
                    template_id=row[1],
                    template_version=row[2],
                    mode=row[3],
                    request_json=row[4] or {},
                    status=row[5],
                    total=row[6],
                    done=row[7],
                    failed=row[8],
                    model=row[9],
                    prompt_version=row[10],
                    error_text=row[11],
                    created_by=row[12],
                    generated_at=row[13].isoformat() if row[13] else None,
                    finished_at=row[14].isoformat() if row[14] else None,
                )
        finally:
            conn.close()
        return build_query_result([{"run": record, "items": items}], expected=1, checked=1)


class FileArchiveStore:
    """文件后端：目录结构与数据库语义一致，只用于开发与单测，不作为验收结论。"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _archive_dir(self, template_id: str, version: str, interview_id: str) -> Path:
        return self.root / template_id / version / interview_id

    def save_archive(self, draft: ArchiveDraft) -> ArchiveRecord:
        draft.validate()
        directory = self._archive_dir(draft.template_id, draft.template_version, draft.interview_id)
        directory.mkdir(parents=True, exist_ok=True)
        # 覆盖语义（用户 2026-11-09 拍板）：同键只保留一份当前档案，重跑原地覆盖不留修订。
        existing = sorted(int(p.stem.split("-r")[-1]) for p in directory.glob("*-r*.json"))
        revision = existing[-1] if existing else 1
        payload = {
            "archive_id": f"{draft.template_id}:{draft.template_version}:{draft.interview_id}:{revision}",
            "interview_id": draft.interview_id,
            "template_id": draft.template_id,
            "template_version": draft.template_version,
            "template_snapshot": draft.template_snapshot,
            "run_id": draft.run_id,
            "revision": revision,
            "status": draft.status,
            "coverage_required": draft.coverage_required,
            "model": draft.model,
            "prompt_version": draft.prompt_version,
            "fields": [
                {
                    "dimension_id": f.dimension_id,
                    "group_id": f.group_id,
                    "fill_mode": f.fill_mode,
                    "value_text": f.value_text,
                    "value_json": f.value_json,
                    "source_ref": f.source_ref,
                    "no_data_reason": f.no_data_reason,
                    "confidence": f.confidence,
                    "evidence_refs": f.evidence_refs,
                    "review_status": f.review_status,
                }
                for f in draft.fields
            ],
        }
        target = directory / f"archive-r{revision}.json"
        for previous in directory.glob("*-r*.json"):
            if previous != target:
                previous.unlink()
        tmp = directory / f".tmp-{uuid.uuid4().hex}.json"
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
        return self._load_file(target)

    def _load_file(self, path: Path) -> ArchiveRecord:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ArchiveRecord(
            archive_id=data["archive_id"],
            interview_id=data["interview_id"],
            template_id=data["template_id"],
            template_version=data["template_version"],
            template_snapshot=data.get("template_snapshot", {}),
            revision=int(data["revision"]),
            status=data["status"],
            coverage_required=float(data["coverage_required"]),
            fields=tuple(ArchiveFieldRecord(**f) for f in data["fields"]),
            run_id=data.get("run_id"),
            model=data.get("model"),
            prompt_version=data.get("prompt_version"),
        )

    def get_archive(
        self,
        interview_id: str,
        template_id: str,
        template_version: str | None = None,
        revision: int | None = None,
    ) -> QueryResult:
        base = self.root / template_id
        if template_version is not None:
            candidates = [base / template_version / interview_id]
        else:
            candidates = sorted(base.glob(f"*/{interview_id}"))
        for directory in candidates:
            files = sorted(directory.glob("archive-r*.json"))
            if not files:
                continue
            if revision is not None:
                match = [p for p in files if int(p.stem.split("-r")[-1]) == revision]
                if not match:
                    continue
                return build_query_result([self._load_file(match[0])], expected=1, checked=1)
            return build_query_result([self._load_file(files[-1])], expected=1, checked=1)
        return build_query_result([], expected=1, checked=1, reasons=["未找到匹配档案"])

    def list_archives(
        self,
        template_id: str,
        template_version: str | None = None,
        status: str | None = None,
        expected: int | None = None,
    ) -> QueryResult:
        base = self.root / template_id
        items: list[ArchiveSummary] = []
        for path in sorted(base.glob("*/*/archive-r*.json")):
            parts = path.parts
            if template_version is not None and parts[-3] != template_version:
                continue
            record = self._load_file(path)
            if status is None and record.status == "stale":
                continue
            if status is not None and record.status != status:
                continue
            items.append(
                ArchiveSummary(
                    archive_id=record.archive_id,
                    interview_id=record.interview_id,
                    template_id=record.template_id,
                    template_version=record.template_version,
                    revision=record.revision,
                    status=record.status,
                    coverage_required=record.coverage_required,
                    field_count=len(record.fields),
                )
            )
        return build_query_result(items, expected=expected)

    def create_run(self, record: RunRecord) -> None:
        _validate_run_status(record.status)
        directory = self.root / "_runs"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{record.run_id}.json").write_text(
            json.dumps(record.__dict__, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def update_run(self, run_id: str, **changes: Any) -> None:
        path = self.root / "_runs" / f"{run_id}.json"
        if not path.exists():
            raise ArchiveStoreError(f"任务不存在：{run_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(changes)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def update_run_item(self, run_id: str, interview_id: str, status: str, error_text: str | None = None) -> None:
        if status not in RUN_ITEM_STATUSES:
            raise ArchiveStoreError(f"run_item.status 非法：{status}")
        path = self.root / "_runs" / f"{run_id}.items.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        data[interview_id] = {"status": status, "error_text": error_text}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_run(self, run_id: str) -> QueryResult:
        path = self.root / "_runs" / f"{run_id}.json"
        if not path.exists():
            return build_query_result([], expected=1, checked=1, reasons=["任务不存在"])
        run = json.loads(path.read_text(encoding="utf-8"))
        item_path = self.root / "_runs" / f"{run_id}.items.json"
        items = json.loads(item_path.read_text(encoding="utf-8")) if item_path.exists() else {}
        return build_query_result(
            [{"run": run, "items": [{"interview_id": k, **v} for k, v in sorted(items.items())]}],
            expected=1,
            checked=1,
        )
