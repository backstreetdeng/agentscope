"""BCI-007 · 报告输出（HTML v1）。

骨架（用户 2026-11-11 确认）：
- 报告是「组竞品」报告，只覆盖竞品侧，不含本品对标；
- 契约以 `config/report_outline.json` 为唯一来源：每页每块先声明 type/source/required，服务端逐块落内容并校验；
- 所有数字来自即时分析取数或档案聚合，正文不写字面数字，样式与措辞不隐藏分母；
- 报告固定一车一份，版本按 `data_fingerprint` 幂等：同指纹直接复用最新有效版本；
- 页面标题结论与导语由模型按本车数据撰写，数字必须来自报告自身，失败或越界降级为只写主题。
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from competitor_insight.server import db
from competitor_insight.server.analysis_service import AnalysisError, AnalysisService
from competitor_insight.server.channel_normalizer import UNCATEGORIZED
from competitor_insight.server.report_archive_aggregate import ArchiveAggregator, ArchiveUnavailable
from competitor_insight.server.report_render_html import RENDERER_VERSION, render_report_html
from competitor_insight.server.llm_client import LlmUnavailable, build_deepseek_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTLINE_PATH = PROJECT_ROOT / "competitor_insight/config/report_outline.json"
CONFIG_PATH = PROJECT_ROOT / "competitor_insight/config/analysis_models.json"

BLOCK_TYPES = {"table", "bars", "kv", "quotes", "bullets"}
BLOCK_STATUSES = {"ok", "partial", "insufficient", "missing", "empty"}

# 确定性改稿只开放这三种指令，不放开模型自由改写道。
REVISION_OPS = {"set_title", "limit_items", "append_refs"}
MAX_LIMIT_ITEMS = 20
NUMERIC_KEYS = {"count", "n", "ratio", "mean"}

SOURCE_REGISTRY: dict[str, str] = {
    "analysis.profile": "定量问卷 · 用户画像分布",
    "analysis.attention": "定量问卷 · Q3_13 购车关注 16 维多选",
    "analysis.winloss": "定量问卷 · Q3_23 / Q3_22×Q3_24 + 深访 Q29",
    "analysis.satisfaction": "定量问卷 · Q5_1 / Q5_2 / Q5_5 + 外部口碑",
    "archive.lifestyle": "洞察档案 · 性格兴趣 / 消费观",
    "archive.motivation": "洞察档案 · 购车动机",
    "archive.brand_role": "洞察档案 · 品牌/产品/服务排序",
    "archive.satisfaction_points": "洞察档案 · 满意点 / 不满点",
    "archive.info_channels": "洞察档案 · 信息获取渠道",
    "archive.content_format": "洞察档案 · 内容形式偏好",
    "archive.conversion": "洞察档案 · 转化机会 / 风险",
    "derived.summary": "本报告内已有数字推导",
    "derived.boundary": "取数元信息与缺口",
}

# 页脚只出现业务口径的数据源名称，按源族聚合；n 一律实时计算。
SOURCE_FAMILIES: dict[str, tuple[str, ...]] = {
    "analysis.profile": ("quant",),
    "analysis.attention": ("quant",),
    "analysis.winloss": ("quant",),
    "analysis.satisfaction": ("quant", "reputation"),
    "archive.lifestyle": ("interview",),
    "archive.motivation": ("interview",),
    "archive.brand_role": ("interview",),
    "archive.satisfaction_points": ("interview",),
    "archive.info_channels": ("interview",),
    "archive.content_format": ("interview",),
    "archive.conversion": ("interview",),
    "derived.summary": (),
    "derived.boundary": (),
}

SOURCE_ORDER = ("interview", "quant", "reputation", "zhiche")
SOURCE_NAMES = {
    "interview": "用户深访解析数据",
    "quant": "用户定量问卷数据",
    "reputation": "外部口碑数据",
    "zhiche": "中汽数据换购数据",
}

# 标题结论与导语由模型按本车数据撰写，但数字必须来自报告自身，品牌不得串车。
NARRATIVE_SYSTEM_PROMPT = (
    "你是竞品用户洞察报告的编辑。只依据用户消息中该页的数据写标题结论和导语，"
    "不得引入数据中没有的事实、品牌或数字；数据不足以支撑结论时 conclusion 输出空字符串。"
    "标题结论不超过 30 字，导语不超过 60 字，均不带句号；"
    "结论要写成判断，不要罗列档案条目，也不要把“其他/未归类”当成主要发现。"
    '输出严格 JSON：{"pages":[{"page":"P01","conclusion":"","lead":""}]}。'
)
NARRATIVE_MAX_CONCLUSION = 30
NARRATIVE_MAX_LEAD = 60


class ReportError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


# ---------------------------------------------------------------------- 契约


def load_outline(path: Path | None = None) -> dict[str, Any]:
    target = Path(path or OUTLINE_PATH)
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError("outline_unavailable", f"报告大纲不可读：{exc.__class__.__name__}", 500) from exc


def validate_outline(outline: dict[str, Any]) -> None:
    """大纲是报告的唯一契约：块 id 唯一、类型受控、来源必须在登记表内。"""
    if not str(outline.get("version") or "").startswith("report-outline/"):
        raise ReportError("outline_invalid", "大纲缺少合法的 version（需以 report-outline/ 开头）", 500)
    pages = list(outline.get("pages") or []) + list(outline.get("appendices") or [])
    if not pages:
        raise ReportError("outline_invalid", "大纲没有任何页面", 500)
    page_ids: set[str] = set()
    block_ids: set[str] = set()
    for page in pages:
        page_id = str(page.get("page") or "")
        if not page_id or page_id in page_ids:
            raise ReportError("outline_invalid", f"页面编号为空或重复：{page_id}", 500)
        page_ids.add(page_id)
        blocks = page.get("blocks") or []
        if page.get("data_status") == "unavailable":
            if blocks:
                raise ReportError("outline_invalid", f"{page_id} 不可用页不应再有内容块", 500)
            if not str(page.get("empty_note") or "").strip():
                raise ReportError("outline_invalid", f"{page_id} 需声明 empty_note", 500)
        elif not blocks:
            raise ReportError("outline_invalid", f"{page_id} 没有任何内容块", 500)
        for declared in page.get("sources") or []:
            if declared.get("id") not in SOURCE_NAMES:
                raise ReportError("outline_invalid", f"{page_id} 数据源族未登记：{declared.get('id')}", 500)
            if not str(declared.get("name") or "").strip():
                raise ReportError("outline_invalid", f"{page_id} 数据源需声明展示名", 500)
            if not isinstance(declared.get("required"), bool):
                raise ReportError("outline_invalid", f"{page_id} 数据源需显式声明 required", 500)
        for block in blocks:
            block_id = str(block.get("id") or "")
            if not block_id or block_id in block_ids:
                raise ReportError("outline_invalid", f"内容块 id 为空或重复：{block_id}", 500)
            block_ids.add(block_id)
            if block.get("type") not in BLOCK_TYPES:
                raise ReportError("outline_invalid", f"{block_id} 类型不受支持：{block.get('type')}", 500)
            if block.get("data_status") == "unavailable":
                if not str(block.get("missing_reason") or "").strip():
                    raise ReportError("outline_invalid", f"{block_id} 不可用块需声明 missing_reason", 500)
            if block.get("source") not in SOURCE_REGISTRY:
                raise ReportError("outline_invalid", f"{block_id} 来源未登记：{block.get('source')}", 500)
            for family in block.get("footer_sources") or []:
                if family not in SOURCE_NAMES:
                    raise ReportError("outline_invalid", f"{block_id} 页脚数据源未登记：{family}", 500)
            if not isinstance(block.get("required"), bool):
                raise ReportError("outline_invalid", f"{block_id} 必须显式声明 required", 500)


# ---------------------------------------------------------------------- 小工具


def _ratio_text(item: dict[str, Any]) -> str:
    count = item.get("count")
    n = item.get("n")
    if count is None or n is None:
        return "—"
    if item.get("ratio") is None:
        return f"{count}/{n}（{item.get('ratio_hidden_reason') or '样本不足，不展示比例'}）"
    return f"{count}/{n}（{item['ratio']}%）"


def _ratio_plain(item: dict[str, Any]) -> str:
    """小结用：避免「（25/41（61.0%））」这类嵌套括号。"""
    count = item.get("count")
    n = item.get("n")
    if count is None or n is None:
        return "—"
    if item.get("ratio") is None:
        return f"{count}/{n}，样本不足不展示比例"
    return f"{count}/{n}，{item['ratio']}%"


def _pct(value: Any) -> str:
    return "—" if value is None else f"{value}%"


def _mean_text(value: Any) -> str:
    return "—" if value is None else f"{value}"


def _availability(statuses: Iterable[str]) -> str:
    seen = [status for status in statuses if status]
    if not seen:
        return "missing"
    if all(status == "ok" for status in seen):
        return "ok"
    if all(status in {"missing", "empty"} for status in seen):
        return "missing"
    return "partial"


def _archive_quote_entries(values: dict[str, Any], dimension: str, *, limit: int = 4) -> list[dict[str, Any]]:
    entries = values.get(dimension) or []
    items: list[dict[str, Any]] = []
    for entry in entries:
        text = entry.get("text") or "；".join(entry.get("items") or [])
        if not text:
            continue
        items.append(
            {
                "code": entry.get("respondent_code") or entry.get("interview_id"),
                "text": text[:220],
                "suspect": bool(entry.get("suspect")),
            }
        )
    return items[:limit]


def _dimension_filled(archives: dict[str, Any], dimension: str) -> tuple[int, int]:
    stats = (archives.get("dimensions") or {}).get(dimension) or {}
    return int(stats.get("filled") or 0), int(stats.get("total") or 0)


def collect_numbers(node: Any) -> list[float]:
    """递归收集块内 count/n/ratio/mean，作为报告侧数字证据索引。

    改稿后用它做白名单校验：新版本的数字必须是旧版本数字的子多重集，
    只允许随条目删除而减少，不允许新增或改写。
    """
    found: list[float] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "numeric_index":
                    continue
                if key in NUMERIC_KEYS and isinstance(item, (int, float)) and not isinstance(item, bool):
                    found.append(round(float(item), 4))
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(node)
    return sorted(found)


def numeric_index(content: dict[str, Any]) -> dict[str, list[float]]:
    """按 block.id 建索引；标题、备注、引用不参与，只认结构化数据字段。"""
    index: dict[str, list[float]] = {}
    for page in list(content.get("pages") or []) + list(content.get("appendices") or []):
        for block in page.get("blocks") or []:
            data = {key: value for key, value in block.items() if key not in {"title", "note", "refs"}}
            index[str(block["id"])] = collect_numbers(data)
    return index


def collect_text_numbers(node: Any) -> list[float]:
    """收集内容里所有字面数字，覆盖改标题等结构化字段之外的位置。"""
    found: list[float] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"data_fingerprint", "refs", "numeric_index"}:
                    continue
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            found.extend(round(float(token), 4) for token in re.findall(r"\d+(?:\.\d+)?", value))

    walk(node)
    return sorted(found)


def _major_label(version_label: Any, version_no: Any) -> str:
    match = re.fullmatch(r"v(\d+)\.(\d+)", str(version_label or ""))
    if match:
        return f"v{match.group(1)}.0"
    return f"v{int(version_no or 1)}.0"


def bump_label(version_label: Any) -> str:
    match = re.fullmatch(r"v(\d+)\.(\d+)", str(version_label or ""))
    if not match:
        return "v1.1"
    return f"v{match.group(1)}.{int(match.group(2)) + 1}"


def _next_major(version_label: Any) -> str:
    match = re.fullmatch(r"v(\d+)\.(\d+)", str(version_label or ""))
    if not match:
        return "v2.0"
    return f"v{int(match.group(1)) + 1}.0"


def _block_rows(block: dict[str, Any]) -> dict[str, str]:
    """把块摊平成「行键 → 行内容」，用于结构化并排与变化行定位。"""
    rows: dict[str, str] = {}
    if block.get("kind") == "matrix":
        for row in block.get("rows") or []:
            rows[str(row[0])] = " | ".join(str(cell) for cell in row[1:])
        return rows
    block_type = block.get("type")
    for model in block.get("models") or []:
        label = str(model.get("label") or model.get("key") or "")
        if block_type == "table":
            for row in model.get("rows") or []:
                rows[f"{label}|{row[0]}"] = " | ".join(str(cell) for cell in row[1:])
        elif block_type == "bars":
            for item in model.get("items") or []:
                rows[f"{label}|{item.get('label')}"] = f"{item.get('value')}（{item.get('text')}）"
        elif block_type == "kv":
            for item in model.get("items") or []:
                rows[f"{label}|{item.get('label')}"] = f"{item.get('value')}（{item.get('sub')}）"
        elif block_type == "quotes":
            for item in model.get("items") or []:
                rows[f"{label}|{item.get('code')}"] = str(item.get("text"))
    for item in block.get("items") or []:
        rows[f"要点|{item.get('model')}"] = str(item.get("text"))
    return rows


# ---------------------------------------------------------------------- 存储


class PostgresReportStore:
    def __init__(self, connect=None) -> None:
        self.connect = connect or (lambda: db.connect(db.load_env()))

    def _run(self, sql: str, params: tuple, *, fetch: bool = True):
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                result = cur.fetchall() if fetch else None
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ensure_report(self, title: str, model_key: str, scope: dict[str, Any], created_by: str) -> str:
        rows = self._run(
            """
            select report_id from bci.report
            where model_key = %s and legacy = false
            order by created_at desc limit 1
            """,
            (model_key,),
        )
        if rows:
            return str(rows[0][0])
        report_id = str(uuid.uuid4())
        self._run(
            """
            insert into bci.report (report_id, title, model_keys, model_key, sample_scope, created_by)
            values (%s, %s, %s::jsonb, %s, %s::jsonb, %s)
            """,
            (
                report_id,
                title,
                json.dumps([model_key], ensure_ascii=False),
                model_key,
                json.dumps(scope, ensure_ascii=False),
                created_by,
            ),
            fetch=False,
        )
        return report_id

    def find_by_fingerprint(self, fingerprint: str, model_key: str) -> dict[str, Any] | None:
        rows = self._run(
            """
            select v.report_version_id, v.report_id, v.version_no, v.version_label, v.generated_at, r.title
            from bci.report_version v
            join bci.report r using (report_id)
            where r.model_key = %s and r.legacy = false and v.data_fingerprint = %s
              and v.status = 'valid' and v.revision_kind = 'generate'
            order by v.generated_at desc limit 1
            """,
            (model_key, fingerprint),
        )
        if not rows:
            return None
        return {
            "report_version_id": str(rows[0][0]),
            "report_id": str(rows[0][1]),
            "version_no": int(rows[0][2]),
            "version_label": rows[0][3] or _major_label(None, rows[0][2]),
            "generated_at": rows[0][4].isoformat() if hasattr(rows[0][4], "isoformat") else str(rows[0][4]),
            "title": rows[0][5],
        }

    def save_version(
        self,
        report_id: str,
        content: dict[str, Any],
        html: str,
        fingerprint: str,
        snapshot: dict[str, Any],
        *,
        revision_kind: str = "generate",
        parent_version_id: str | None = None,
        patch: dict[str, Any] | None = None,
        version_label: str | None = None,
    ) -> dict[str, Any]:
        """同一事务内锁报告行再取号，避免并发升版撞唯一键。"""
        version_id = str(uuid.uuid4())
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("select report_id from bci.report where report_id = %s for update", (report_id,))
                if not cur.fetchone():
                    raise ReportError("report_not_found", "报告不存在", 404)
                cur.execute(
                    "select coalesce(max(version_no), 0), max(version_label) from bci.report_version where report_id = %s",
                    (report_id,),
                )
                version_no, latest_label = cur.fetchone()
                version_no = int(version_no or 0) + 1
                label = version_label or (
                    "v1.0" if latest_label is None else (bump_label(latest_label) if revision_kind == "revise" else _next_major(latest_label))
                )
                cur.execute(
                    """
                    insert into bci.report_version
                        (report_version_id, report_id, version_no, version_label, parent_version_id,
                         revision_kind, patch, content, html, data_fingerprint, source_snapshot)
                    values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb)
                    returning generated_at
                    """,
                    (
                        version_id,
                        report_id,
                        version_no,
                        label,
                        parent_version_id,
                        revision_kind,
                        json.dumps(patch or {}, ensure_ascii=False),
                        json.dumps(content, ensure_ascii=False),
                        html,
                        fingerprint,
                        json.dumps(snapshot, ensure_ascii=False),
                    ),
                )
                generated_at = cur.fetchone()[0]
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return {
            "report_version_id": version_id,
            "report_id": report_id,
            "version_no": version_no,
            "version_label": label,
            "revision_kind": revision_kind,
            "generated_at": generated_at.isoformat() if hasattr(generated_at, "isoformat") else str(generated_at),
        }

    def list_versions(self, model_key: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._run(
            """
            select v.report_version_id, v.report_id, r.title, r.model_keys, r.model_key, r.legacy,
                   v.version_no, v.version_label, v.parent_version_id, v.revision_kind,
                   v.generated_at, v.status, v.stale_reason, v.data_fingerprint
            from bci.report_version v
            join bci.report r using (report_id)
            where (%s::text is null or r.model_key = %s::text) and r.legacy = false
            order by v.generated_at desc
            limit %s
            """,
            (model_key, model_key, int(limit)),
        )
        return [
            {
                "report_version_id": str(row[0]),
                "report_id": str(row[1]),
                "title": row[2],
                "model_keys": row[3],
                "model_key": row[4],
                "legacy": bool(row[5]),
                "version_no": int(row[6]),
                "version_label": row[7] or _major_label(None, row[6]),
                "parent_version_id": str(row[8]) if row[8] else None,
                "revision_kind": row[9],
                "generated_at": row[10].isoformat() if hasattr(row[10], "isoformat") else str(row[10]),
                "status": row[11],
                "stale_reason": row[12] or "",
                "data_fingerprint": row[13],
            }
            for row in rows
        ]

    def version_line(self, report_id: str) -> list[dict[str, Any]]:
        rows = self._run(
            """
            select report_version_id, version_no, version_label, parent_version_id, revision_kind,
                   generated_at, status, stale_reason
            from bci.report_version where report_id = %s order by version_no
            """,
            (report_id,),
        )
        return [
            {
                "report_version_id": str(row[0]),
                "version_no": int(row[1]),
                "version_label": row[2] or _major_label(None, row[1]),
                "parent_version_id": str(row[3]) if row[3] else None,
                "revision_kind": row[4],
                "generated_at": row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5]),
                "status": row[6],
                "stale_reason": row[7] or "",
            }
            for row in rows
        ]

    def get_version(self, report_version_id: str) -> dict[str, Any] | None:
        rows = self._run(
            """
            select v.report_version_id, v.report_id, r.title, r.model_keys, r.model_key, r.legacy,
                   v.version_no, v.version_label, v.parent_version_id, v.revision_kind, v.patch,
                   v.content, v.html, v.data_fingerprint, v.source_snapshot, v.generated_at,
                   v.status, v.stale_reason
            from bci.report_version v
            join bci.report r using (report_id)
            where v.report_version_id = %s
            """,
            (report_version_id,),
        )
        if not rows:
            return None
        row = rows[0]
        return {
            "report_version_id": str(row[0]),
            "report_id": str(row[1]),
            "title": row[2],
            "model_keys": row[3],
            "model_key": row[4],
            "legacy": bool(row[5]),
            "version_no": int(row[6]),
            "version_label": row[7] or _major_label(None, row[6]),
            "parent_version_id": str(row[8]) if row[8] else None,
            "revision_kind": row[9],
            "patch": row[10] or {},
            "content": row[11],
            "html": row[12],
            "data_fingerprint": row[13],
            "source_snapshot": row[14],
            "generated_at": row[15].isoformat() if hasattr(row[15], "isoformat") else str(row[15]),
            "status": row[16],
            "stale_reason": row[17] or "",
        }

    def mark_stale(self, report_version_id: str, reason: str) -> None:
        self._run(
            "update bci.report_version set status = 'stale', stale_reason = %s where report_version_id = %s",
            (reason, report_version_id),
            fetch=False,
        )


# ---------------------------------------------------------------------- 服务


class BciReportService:
    def __init__(
        self,
        analysis: AnalysisService | None = None,
        archive: ArchiveAggregator | None = None,
        store: PostgresReportStore | None = None,
        outline_path: Path | None = None,
        narrative: bool | None = None,
    ) -> None:
        self.analysis = analysis or AnalysisService()
        self.archive = archive or ArchiveAggregator(connect=lambda: db.connect(db.load_env()))
        self.store = store or PostgresReportStore()
        self._outline_path = Path(outline_path or OUTLINE_PATH)
        self._outline: dict[str, Any] | None = None
        self.narrative = (
            narrative
            if narrative is not None
            else os.environ.get("BCI_REPORT_NARRATIVE", "1") != "0"
        )

    # ---------------------------------------------------------------- 元信息

    def outline(self) -> dict[str, Any]:
        if self._outline is None:
            outline = load_outline(self._outline_path)
            validate_outline(outline)
            self._outline = outline
        return self._outline

    def options(self) -> dict[str, Any]:
        models = self.analysis.models()
        archive_meta = self._archive_meta()
        for model in models["models"]:
            model["archive"] = self._archive_coverage(model["key"])
        return {
            "models": models["models"],
            "default_model": models["default_model"],
            "version": models["version"],
            "archive": archive_meta,
            "outline": self._outline_brief(),
            "renderer": RENDERER_VERSION,
        }

    def _outline_brief(self) -> dict[str, Any]:
        outline = self.outline()
        return {
            "version": outline["version"],
            "pages": [
                {"page": page["page"], "title": page["title"], "blocks": [block["id"] for block in page["blocks"]]}
                for page in list(outline["pages"]) + list(outline.get("appendices") or [])
            ],
            "excluded_pages": outline.get("excluded_pages") or [],
            "scope_note": outline.get("scope_note", ""),
        }

    def _archive_meta(self) -> dict[str, Any]:
        try:
            return {
                "template_id": self.archive.template_id,
                "template_version": self.archive.template_version(),
            }
        except ArchiveUnavailable as exc:
            raise ReportError("archive_unavailable", str(exc), 503) from exc

    def _archive_coverage(self, model_key: str) -> dict[str, int]:
        model = self._model(model_key)
        names = model.get("interview_models") or [model["label"]]
        try:
            archived = len(self.archive.interviews(names))
            total = self.archive.interview_total(names)
        except ArchiveUnavailable:
            archived, total = 0, 0
        return {"archived": archived, "interview_total": total}

    def _model(self, key: str) -> dict[str, Any]:
        config = self.analysis.config()
        for model in config["models"]:
            if model["key"] == key or model["label"] == key:
                return model
        raise ReportError("model_not_found", f"车型不在配置清单中：{key}", 404)

    # ---------------------------------------------------------------- 快照 / 指纹

    def snapshot(self, model_keys: list[str]) -> dict[str, Any]:
        """指纹输入：只取元信息，不跑完整分析，详情页也能在 1–2 秒内判定 stale。"""
        config = self.analysis.config()
        models = {item["key"]: item for item in self.analysis.models()["models"]}
        per_model = []
        for key in model_keys:
            model = self._model(key)
            names = model.get("interview_models") or [model["label"]]
            try:
                archives = self.archive.interviews(names)
            except ArchiveUnavailable:
                archives = []
            per_model.append(
                {
                    "key": key,
                    "sources": models.get(key, {}).get("sources", {}),
                    "archives": [
                        {
                            "interview_id": item["interview_id"],
                            "revision": item["revision"],
                            "template_version": item["template_version"],
                            "updated_at": item["updated_at"],
                        }
                        for item in archives
                    ],
                }
            )
        return {
            "analysis_config": {"version": config.get("version"), "updated": config.get("updated")},
            "outline": self.outline()["version"],
            "archive_template": self._archive_meta(),
            "renderer": RENDERER_VERSION,
            "models": per_model,
        }

    @staticmethod
    def fingerprint(snapshot: dict[str, Any]) -> str:
        payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # ---------------------------------------------------------------- 生成

    def generate(self, model_keys: Iterable[str] | str, created_by: str = "web") -> dict[str, Any]:
        model_key = self._normalize_key(model_keys)
        # 先用轻量快照判定是否已有同版本，命中直接复用，不为重复点击重跑完整取数。
        fingerprint = self.fingerprint(self.snapshot([model_key]))
        existing = self.store.find_by_fingerprint(fingerprint, model_key)
        if existing:
            return self._reuse_payload(existing)

        content, snapshot = self.build([model_key])
        fingerprint = self.fingerprint(snapshot)
        existing = self.store.find_by_fingerprint(fingerprint, model_key)
        if existing:
            return self._reuse_payload(existing)

        html = render_report_html(content)
        report_id = self.store.ensure_report(content["title"], model_key, content["scope"], created_by)
        saved = self.store.save_version(report_id, content, html, fingerprint, snapshot)
        return {
            "created": True,
            "reused": False,
            "report_id": saved["report_id"],
            "report_version_id": saved["report_version_id"],
            "version_no": saved["version_no"],
            "version_label": saved["version_label"],
            "generated_at": saved["generated_at"],
            "title": content["title"],
            "summary": self._response_summary(content),
        }

    @staticmethod
    def _reuse_payload(existing: dict[str, Any]) -> dict[str, Any]:
        return {
            "created": False,
            "reused": True,
            "report_id": existing["report_id"],
            "report_version_id": existing["report_version_id"],
            "version_no": existing["version_no"],
            "version_label": existing.get("version_label") or _major_label(None, existing["version_no"]),
            "generated_at": existing["generated_at"],
            "title": existing["title"],
            "summary": None,
        }

    # ---------------------------------------------------------------- 确定性改稿

    def revise(self, report_version_id: str, operations: Any, created_by: str = "web") -> dict[str, Any]:
        """只执行 set_title / limit_items / append_refs，落成子版本，不覆盖父版本。"""
        parent = self.store.get_version(report_version_id)
        if not parent:
            raise ReportError("report_not_found", "报告版本不存在", 404)
        if parent.get("legacy"):
            raise ReportError("legacy_readonly", "历史多车型报告已转只读，不能改稿", 409)
        if not isinstance(operations, list) or not operations:
            raise ReportError("invalid_request", "改稿指令不能为空", 400)

        content = copy.deepcopy(parent["content"])
        applied = self._apply_operations(content, operations)
        self._check_numeric_invariant(parent["content"], content)
        content["numeric_index"] = numeric_index(content)
        content["data_fingerprint"] = parent["data_fingerprint"]

        label = bump_label(parent["version_label"])
        existing_labels = {item["version_label"] for item in self.store.version_line(parent["report_id"])}
        if label in existing_labels:
            raise ReportError("revision_conflict", f"{label} 已存在，请在该车型最新版本上继续改稿", 409)

        html = render_report_html(content)
        saved = self.store.save_version(
            parent["report_id"],
            content,
            html,
            parent["data_fingerprint"],
            parent["source_snapshot"],
            revision_kind="revise",
            parent_version_id=report_version_id,
            patch={"parent_version_id": report_version_id, "parent_version_label": parent["version_label"], "operations": applied},
            version_label=label,
        )
        return {
            "created": True,
            "report_id": saved["report_id"],
            "report_version_id": saved["report_version_id"],
            "parent_version_id": report_version_id,
            "version_no": saved["version_no"],
            "version_label": saved["version_label"],
            "generated_at": saved["generated_at"],
            "title": parent["title"],
            "applied": applied,
        }

    def _apply_operations(self, content: dict[str, Any], operations: list[Any]) -> list[dict[str, Any]]:
        page_map = {
            str(page["page"]): page for page in list(content.get("pages") or []) + list(content.get("appendices") or [])
        }
        block_map = {
            str(block["id"]): block
            for page in list(content.get("pages") or []) + list(content.get("appendices") or [])
            for block in page.get("blocks") or []
        }
        applied: list[dict[str, Any]] = []
        for spec in operations:
            if not isinstance(spec, dict):
                raise ReportError("invalid_request", "改稿指令必须是对象", 400)
            op = spec.get("op")
            if op not in REVISION_OPS:
                raise ReportError("invalid_request", f"不支持的改稿指令：{op}", 400)
            target = spec.get("target") or {}
            page_id = str(target.get("page") or "")
            block_id = str(target.get("block") or "")

            if op == "set_title":
                value = str(spec.get("value") or "").strip()
                if not value or len(value) > 60:
                    raise ReportError("invalid_request", "标题需为 1–60 字", 400)
                if block_id:
                    block = block_map.get(block_id)
                    if not block:
                        raise ReportError("target_not_found", f"内容块不存在：{block_id}", 404)
                    block["title"] = value
                    applied.append({"op": op, "target": {"block": block_id}, "value": value})
                elif page_id:
                    page = page_map.get(page_id)
                    if not page:
                        raise ReportError("target_not_found", f"页面不存在：{page_id}", 404)
                    page["title"] = value
                    applied.append({"op": op, "target": {"page": page_id}, "value": value})
                else:
                    raise ReportError("invalid_request", "set_title 需要 page 或 block 锚点", 400)
                continue

            block = block_map.get(block_id)
            if not block:
                raise ReportError("target_not_found", f"内容块不存在：{block_id}", 404)

            if op == "limit_items":
                if block.get("type") != "bullets":
                    raise ReportError("invalid_request", f"{block_id} 不是要点块，不能截断条目", 400)
                count = spec.get("count")
                if not isinstance(count, int) or isinstance(count, bool) or not (1 <= count <= MAX_LIMIT_ITEMS):
                    raise ReportError("invalid_request", f"条数需为 1–{MAX_LIMIT_ITEMS} 的整数", 400)
                block["items"] = list(block.get("items") or [])[:count]
                applied.append({"op": op, "target": {"block": block_id}, "count": count})
                continue

            refs = spec.get("refs")
            if not isinstance(refs, list) or not refs:
                raise ReportError("invalid_request", "append_refs 需要 refs 数组", 400)
            cleaned: list[str] = []
            for ref in refs:
                name = str(ref or "").strip()
                if name not in block_map:
                    raise ReportError("target_not_found", f"引用块不存在：{name}", 404)
                if name not in cleaned:
                    cleaned.append(name)
            current = list(block.get("refs") or [])
            for name in cleaned:
                if name not in current:
                    current.append(name)
            block["refs"] = current
            applied.append({"op": op, "target": {"block": block_id}, "refs": cleaned})
        return applied

    @staticmethod
    def _check_numeric_invariant(before: dict[str, Any], after: dict[str, Any]) -> None:
        old = numeric_index(before)
        for block_id, values in numeric_index(after).items():
            extra = Counter(values) - Counter(old.get(block_id, []))
            if extra:
                raise ReportError(
                    "numeric_violation",
                    f"{block_id} 出现原报告没有的数字：{sorted(extra.elements())}；确定性改稿只允许删除条目，不能新增或改写数字",
                    422,
                )
        extra_text = Counter(collect_text_numbers(after)) - Counter(collect_text_numbers(before))
        if extra_text:
            raise ReportError(
                "numeric_violation",
                f"改稿文本新增了原报告没有的数字：{sorted(extra_text.elements())}；确定性改稿不放开自由撰写",
                422,
            )

    # ---------------------------------------------------------------- 版本对比

    def compare(self, base_version_id: str, target_version_id: str) -> dict[str, Any]:
        base = self.store.get_version(base_version_id)
        target = self.store.get_version(target_version_id)
        if not base or not target:
            raise ReportError("report_not_found", "对比的版本不存在", 404)
        if base["report_id"] != target["report_id"]:
            raise ReportError("invalid_request", "只能对比同一车型报告下的版本", 400)

        base_pages = {
            str(page["page"]): page
            for page in list(base["content"].get("pages") or []) + list(base["content"].get("appendices") or [])
        }
        target_pages = {
            str(page["page"]): page
            for page in list(target["content"].get("pages") or []) + list(target["content"].get("appendices") or [])
        }
        order = [str(page["page"]) for page in target["content"].get("pages") or []]
        order += [str(page["page"]) for page in target["content"].get("appendices") or []]
        order += [page_id for page_id in base_pages if page_id not in order]

        pages: list[dict[str, Any]] = []
        changed_blocks = 0
        for page_id in order:
            old_page = base_pages.get(page_id) or {}
            new_page = target_pages.get(page_id) or {}
            old_blocks = {str(block["id"]): block for block in old_page.get("blocks") or []}
            new_blocks = {str(block["id"]): block for block in new_page.get("blocks") or []}
            block_ids = [str(block["id"]) for block in new_page.get("blocks") or []]
            block_ids += [block_id for block_id in old_blocks if block_id not in block_ids]
            blocks: list[dict[str, Any]] = []
            for block_id in block_ids:
                old_block = old_blocks.get(block_id) or {}
                new_block = new_blocks.get(block_id) or {}
                old_rows = _block_rows(old_block) if old_block else {}
                new_rows = _block_rows(new_block) if new_block else {}
                row_keys = list(new_rows) + [key for key in old_rows if key not in new_rows]
                row_changes = []
                for key in row_keys:
                    before = old_rows.get(key)
                    after = new_rows.get(key)
                    if before == after:
                        continue
                    change = "added" if before is None else ("removed" if after is None else "changed")
                    row_changes.append({"key": key, "change": change, "before": before, "after": after})
                title_changed = old_block.get("title") != new_block.get("title") or old_page.get("title") != new_page.get("title")
                refs_changed = (old_block.get("refs") or []) != (new_block.get("refs") or [])
                changed = bool(row_changes or title_changed or refs_changed or (not old_block) or (not new_block))
                if changed:
                    changed_blocks += 1
                blocks.append(
                    {
                        "id": block_id,
                        "title": new_block.get("title") or old_block.get("title"),
                        "changed": changed,
                        "row_changes": row_changes,
                    }
                )
            page_changed = old_page.get("title") != new_page.get("title") or any(block["changed"] for block in blocks)
            pages.append(
                {
                    "page": page_id,
                    "title": new_page.get("title") or old_page.get("title"),
                    "changed": page_changed,
                    "blocks": blocks,
                }
            )

        return {
            "base": {
                "report_version_id": base["report_version_id"],
                "version_label": base["version_label"],
                "title": base["title"],
                "generated_at": base["generated_at"],
            },
            "target": {
                "report_version_id": target["report_version_id"],
                "version_label": target["version_label"],
                "title": target["title"],
                "generated_at": target["generated_at"],
            },
            "changed_pages": sum(1 for page in pages if page["changed"]),
            "changed_blocks": changed_blocks,
            "pages": pages,
        }

    @staticmethod
    def _response_summary(content: dict[str, Any]) -> dict[str, Any]:
        blocks = [block for page in content["pages"] for block in page["blocks"]]
        return {
            "pages": len(content["pages"]),
            "blocks": len(blocks),
            "blocks_missing": sum(1 for block in blocks if block["availability"] == "missing"),
            "gaps": len(content["gaps"]),
            "data_fingerprint": content["data_fingerprint"][:12],
        }

    def _normalize_key(self, model_keys: Iterable[str] | str) -> str:
        config = self.analysis.config()
        order = [model["key"] for model in config["models"]]
        values = [model_keys] if isinstance(model_keys, str) else list(model_keys or [])
        wanted: list[str] = []
        for key in values:
            name = str(key or "").strip()
            if name and name not in wanted:
                wanted.append(name)
        if not wanted:
            wanted = [config.get("default_model") or order[0]]
        if len(wanted) > 1:
            raise ReportError("multi_model_not_supported", "报告固定为一个目标车型一份，请只选择一个车型", 400)
        key = wanted[0]
        if key not in order:
            raise ReportError("model_not_found", f"车型不在配置清单中：{key}", 404)
        return key

    # ---------------------------------------------------------------- 内容

    def build(self, model_keys: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
        outline = self.outline()
        config = self.analysis.config()
        models_meta = {item["key"]: item for item in self.analysis.models()["models"]}
        labels = [self._model(key)["label"] for key in model_keys]

        analysed: dict[str, dict[str, Any]] = {}
        archives: dict[str, dict[str, Any]] = {}
        for key in model_keys:
            model = self._model(key)
            names = model.get("interview_models") or [model["label"]]
            try:
                analysed[key] = self.analysis.analyze(key)
            except AnalysisError as exc:
                raise ReportError("analysis_failed", f"{model['label']} 取数失败：{exc}", 503) from exc
            try:
                archives[key] = self.archive.aggregate(names)
            except ArchiveUnavailable as exc:
                raise ReportError("archive_unavailable", f"{model['label']} 档案聚合失败：{exc}", 503) from exc

        context = {
            "outline": outline,
            "config": config,
            "keys": model_keys,
            "labels": labels,
            "models_meta": models_meta,
            "analysed": analysed,
            "archives": archives,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }

        pages: list[dict[str, Any]] = []
        gaps: list[dict[str, str]] = []
        counts = self._source_counts(context)
        for page in outline["pages"]:
            pages.append(self._render_page(page, context, gaps, counts))
        appendices = [self._render_page(page, context, gaps, counts) for page in outline.get("appendices") or []]
        for item in pages + appendices:
            if item.get("index"):
                item["title"] = f"{item['index']}-{item.get('theme') or item['title']}"

        content = {
            "outline_version": outline["version"],
            "title": f"{labels[0]} 竞品用户洞察报告" if len(labels) == 1 else f"{len(model_keys)} 款车型竞品用户洞察报告",
            "subtitle": "竞品侧用户洞察 · 定量 + 深访 + 口碑",
            "scope_note": outline.get("scope_note", ""),
            "generated_at": context["generated_at"],
            "models": [
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "sources": models_meta.get(key, {}).get("sources", {}),
                    "missing_sources": models_meta.get(key, {}).get("missing_sources", []),
                    "archive": archives[key]["coverage"],
                }
                for key in model_keys
            ],
            "scope": {
                "quant": "各车型全部定量样本，不切动力形式",
                "archive": "各车型已生成洞察档案，按当前最大 revision 去重",
            },
            "pages": pages,
            "appendices": appendices,
            "excluded_pages": outline.get("excluded_pages") or [],
            "gaps": gaps,
            "data_fingerprint": self.fingerprint(self._snapshot_from(context)),
            "sources": self._source_rows(context),
        }
        content["numeric_index"] = numeric_index(content)
        self._apply_page_narratives(pages + appendices, content, labels)
        self._validate_content(content, outline)
        return content, self._snapshot_from(context)

    def _snapshot_from(self, context: dict[str, Any]) -> dict[str, Any]:
        per_model = []
        for key in context["keys"]:
            per_model.append(
                {
                    "key": key,
                    "sources": context["models_meta"].get(key, {}).get("sources", {}),
                    "archives": [
                        {
                            "interview_id": item["interview_id"],
                            "revision": item["revision"],
                            "template_version": item["template_version"],
                            "updated_at": item["updated_at"],
                        }
                        for item in context["archives"][key]["interviews"]
                    ],
                }
            )
        return {
            "analysis_config": {
                "version": context["config"].get("version"),
                "updated": context["config"].get("updated"),
            },
            "outline": context["outline"]["version"],
            "archive_template": {
                "template_id": context["outline"]["archive_template_id"],
                "template_version": context["archives"][context["keys"][0]]["template_version"]
                if context["keys"]
                else "",
            },
            "renderer": RENDERER_VERSION,
            "models": per_model,
        }

    def _apply_page_narratives(
        self,
        pages: list[dict[str, Any]],
        content: dict[str, Any],
        labels: list[str],
    ) -> None:
        """标题结论与导语由模型按本车数据撰写，写不出或越界就降级为只写主题。"""
        if not self.narrative:
            return
        targets = [
            page
            for page in pages
            if page.get("data_status") != "unavailable"
            and page.get("blocks")
            and page.get("narrative", True)
        ]
        if not targets:
            return
        try:
            call = build_deepseek_client(system_prompt=NARRATIVE_SYSTEM_PROMPT)
            payload = {
                "report_model": labels[0] if labels else "",
                "pages": [
                    {
                        "page": page["page"],
                        "theme": page.get("theme") or page.get("title"),
                        "subtitle": page.get("subtitle") or "",
                        "data": [self._block_digest(block) for block in page.get("blocks") or []],
                    }
                    for page in targets
                ],
            }
            raw = call(json.dumps(payload, ensure_ascii=False))
            parsed = json.loads(raw)
        except (LlmUnavailable, json.JSONDecodeError):
            return
        items = {str(item.get("page")): item for item in parsed.get("pages") or [] if isinstance(item, dict)}
        allowed = set(collect_text_numbers(content))
        for page in targets:
            item = items.get(page["page"]) or {}
            conclusion = self._narrative_text(
                item.get("conclusion"), NARRATIVE_MAX_CONCLUSION, allowed, labels
            )
            lead = self._narrative_text(item.get("lead"), NARRATIVE_MAX_LEAD, allowed, labels)
            page["conclusion"] = conclusion
            base = f"{page['index']}-{page['theme']}" if page.get("index") else page["title"]
            page["title"] = f"{base}：{conclusion}" if conclusion else base
            if lead:
                page["lead"] = lead

    def _block_digest(self, block: dict[str, Any]) -> dict[str, Any]:
        picked = {
            key: block.get(key)
            for key in ("id", "title", "note", "columns", "rows", "items", "models", "unit", "availability")
            if block.get(key) not in (None, "", [])
        }
        for key in ("rows", "items"):
            if isinstance(picked.get(key), list):
                picked[key] = [
                    item
                    for item in picked[key]
                    if not (isinstance(item, list) and item and str(item[0]) in {"其他", "未归类"})
                ][:6]
        if isinstance(picked.get("models"), list):
            picked["models"] = [
                {
                    "label": model.get("label"),
                    "n": model.get("n"),
                    "rows": [
                        row
                        for row in model.get("rows") or []
                        if not (isinstance(row, list) and row and str(row[0]) in {"其他", "未归类"})
                    ][:6],
                    "items": (model.get("items") or [])[:6],
                }
                for model in picked["models"][:3]
            ]
        return picked

    def _narrative_text(
        self,
        value: Any,
        limit: int,
        allowed: set[float],
        labels: list[str],
    ) -> str:
        text = " ".join(str(value or "").split()).strip().rstrip("。.")
        if not text or len(text) > limit:
            return ""
        masked = text
        for model in self.analysis.models().get("models") or []:
            label = str(model.get("label") or "")
            if label:
                masked = masked.replace(label, " ")
        for token in re.findall(r"\d+(?:\.\d+)?", masked):
            if round(float(token), 4) not in allowed:
                return ""
        for model in self.analysis.models().get("models") or []:
            label = str(model.get("label") or "")
            if label and label not in labels and label in text:
                return ""
        return text

    def _render_page(
        self,
        page: dict[str, Any],
        context: dict[str, Any],
        gaps: list[dict[str, str]],
        counts: dict[str, Any],
    ) -> dict[str, Any]:
        if page.get("data_status") == "unavailable":
            return {
                "page": page["page"],
                "index": page.get("index"),
                "theme": page.get("theme", ""),
                "title": page["title"],
                "subtitle": page.get("subtitle", ""),
                "lead": page.get("lead", ""),
                "blocks": [],
                "data_status": "unavailable",
                "empty_note": page.get("empty_note") or "暂未提供数据",
                "missing_reason": page.get("missing_reason", ""),
                "sources": [
                    {
                        "key": item["id"],
                        "name": item.get("name") or SOURCE_NAMES[item["id"]],
                        "n": counts.get(item["id"]),
                        "required": bool(item.get("required")),
                    }
                    for item in page.get("sources") or []
                ],
                "footer_note": page.get("footer_note", ""),
                "availability": "missing",
            }
        blocks = []
        for block in page["blocks"]:
            rendered = self._render_block(block, context)
            if block["required"] and rendered["availability"] in {"missing", "empty"}:
                gaps.append(
                    {
                        "page": page["page"],
                        "block": block["id"],
                        "title": block["title"],
                        "reason": rendered.get("note") or "无数据",
                    }
                )
            blocks.append(rendered)
        families: list[str] = []
        for block in page["blocks"]:
            for family in block.get("footer_sources") or SOURCE_FAMILIES.get(block["source"], ()):
                if family not in families:
                    families.append(family)
        declared = {item["id"]: item for item in page.get("sources") or []}
        sources = [
            {
                "key": family,
                "name": (declared.get(family) or {}).get("name") or SOURCE_NAMES[family],
                "n": counts.get(family),
                "required": bool((declared.get(family) or {}).get("required", True)),
            }
            for family in SOURCE_ORDER
            if family in families
        ]
        return {
            "page": page["page"],
            "index": page.get("index"),
            "theme": page.get("theme", ""),
            "title": page["title"],
            "subtitle": page.get("subtitle", ""),
            "lead": page.get("lead", ""),
            "blocks": blocks,
            "sources": sources,
            "footer_note": page.get("footer_note", ""),
            "availability": _availability(block["availability"] for block in blocks),
            "narrative": page.get("narrative", True),
        }

    def _source_counts(self, context: dict[str, Any]) -> dict[str, Any]:
        """页脚 n 实时计算：档案人数、问卷作答数、去重口碑条数；中汽换购未接入。"""
        counts: dict[str, Any] = {"interview": 0, "quant": 0, "reputation": 0, "zhiche": None}
        for key in context["keys"]:
            counts["interview"] += int((context["archives"][key].get("coverage") or {}).get("archived") or 0)
            counts["quant"] += int(((context["models_meta"].get(key) or {}).get("sources") or {}).get("quant") or 0)
            metric = self._metric(context["analysed"][key], "satisfaction", "reputation")
            denominators = metric.get("denominators") or {}
            for direction in ("positive", "negative"):
                value = denominators.get(direction)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    counts["reputation"] += int(value)
        return counts

    def _render_block(self, block: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if block.get("data_status") == "unavailable":
            return {
                "id": block["id"],
                "type": block["type"],
                "title": block["title"],
                "source": block["source"],
                "refs": [],
                "availability": "missing",
                "data_status": "unavailable",
                "empty_note": block.get("empty_note") or "暂未提供数据",
                "note": block.get("missing_reason") or "",
            }
        builder = getattr(self, f"_build_{block['id'].replace('.', '_').lower()}", None)
        if builder is None:
            raise ReportError("outline_invalid", f"内容块 {block['id']} 没有实现", 500)
        data = builder(context)
        data.update({"id": block["id"], "type": block["type"], "title": block["title"], "source": block["source"]})
        data.setdefault("refs", [])
        if data.get("availability") not in BLOCK_STATUSES:
            raise ReportError("content_invalid", f"{block['id']} 的可用性取值非法", 500)
        return data

    # ---------------------------------------------------------------- P01

    def _build_p01_basic(self, context: dict[str, Any]) -> dict[str, Any]:
        models = []
        for key in context["keys"]:
            data = context["analysed"][key]
            n = ((data["tiles"].get("profile") or {}).get("metrics") or [{}])[0].get("n")
            rows = []
            for metric in (data["tiles"].get("profile") or {}).get("metrics") or []:
                if metric.get("kind") != "distribution" or metric.get("status") != "ok":
                    continue
                items = sorted(metric.get("items") or [], key=lambda item: (-item.get("count", 0), item.get("label", "")))[:3]
                if not items:
                    continue
                rows.append([metric.get("label", ""), "；".join(f"{item['label']} {_ratio_text(item)}" for item in items)])
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "n": n,
                    "columns": ["维度", "主要取值（人数 / 占比）"],
                    "rows": rows,
                    "status": "ok" if rows else "missing",
                    "note": "" if rows else "该车型定量画像分布为空",
                }
            )
        return {"kind": "per_model", "models": models, "availability": _availability(m["status"] for m in models)}

    def _build_p01_lifestyle(self, context: dict[str, Any]) -> dict[str, Any]:
        return self._archive_quote_block(context, "personality_interest_social", empty_note="该车型档案无生活状态字段")

    def _build_p01_motivation(self, context: dict[str, Any]) -> dict[str, Any]:
        return self._archive_quote_block(context, "purchase_motivation", empty_note="该车型档案无购车动机字段")

    def _build_p01_purchase(self, context: dict[str, Any]) -> dict[str, Any]:
        """购车特征：能取到的按口径落表，未采集的字段显式标缺，不用别的数据顶替。"""
        models = []
        for key in context["keys"]:
            attention = ((context["analysed"][key]["tiles"].get("attention") or {}).get("metrics") or [{}])[0]
            top = attention.get("top") or []
            archives = context["archives"][key]
            motivation = (archives["values"].get("purchase_motivation") or [])[:2]
            filled, total = _dimension_filled(archives, "purchase_motivation")
            rows = [
                [
                    "关注点 TOP3（定量）",
                    "；".join(f"{item['label']} {_ratio_text(item)}" for item in top[:3]) or "暂未提供数据",
                ],
                [
                    "购车动机（深访）",
                    "；".join((item.get("text") or "；".join(item.get("items") or []))[:80] for item in motivation)
                    or "暂未提供数据",
                ],
                ["用车场景", "暂未提供数据"],
                ["首购 / 增换购与预算", "暂未提供数据"],
            ]
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "n": attention.get("n"),
                    "columns": ["购车特征", "本车取值与口径"],
                    "rows": rows,
                    "status": "partial",
                    "note": (
                        f"关注点来自定量（n={attention.get('n')}）；动机来自深访 {filled}/{total} 份档案；"
                        "场景与预算字段档案未采集，不按其他数据推断。"
                    ),
                }
            )
        return {"kind": "per_model", "models": models, "availability": "partial"}

    # ---------------------------------------------------------------- P04

    def _build_p04_chart(self, context: dict[str, Any]) -> dict[str, Any]:
        models = []
        for key in context["keys"]:
            attention = ((context["analysed"][key]["tiles"].get("attention") or {}).get("metrics") or [{}])[0]
            items = [
                {"label": item["label"], "value": item.get("ratio"), "text": f"{item.get('count')}/{item.get('n')}"}
                for item in attention.get("top") or []
                if item.get("ratio") is not None
            ]
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "n": attention.get("n"),
                    "items": items,
                    "status": "ok" if items else (attention.get("status") or "missing"),
                    "note": attention.get("note", ""),
                }
            )
        return {
            "kind": "bars",
            "unit": "%",
            "max": 100,
            "models": models,
            "note": "多选题，勾选率之和大于 100%；分母为车型定量样本，作答不足 10 人不出比例。",
            "availability": _availability(model["status"] for model in models),
        }

    def _build_p04_top5(self, context: dict[str, Any]) -> dict[str, Any]:
        models = []
        for key in context["keys"]:
            attention = ((context["analysed"][key]["tiles"].get("attention") or {}).get("metrics") or [{}])[0]
            rows = [
                [item["label"], str(item.get("count")), str(item.get("n")), _pct(item.get("ratio"))]
                for item in attention.get("top") or []
            ]
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "n": attention.get("n"),
                    "columns": ["关注点", "勾选人数", "分母", "勾选率"],
                    "rows": rows,
                    "status": "ok" if rows else "missing",
                    "note": attention.get("note", ""),
                }
            )
        return {"kind": "per_model", "models": models, "availability": _availability(m["status"] for m in models)}

    def _build_p04_brand_role(self, context: dict[str, Any]) -> dict[str, Any]:
        return self._archive_quote_block(context, "brand_product_service_rank", empty_note="该车型档案无品牌/产品/服务排序")

    def _build_p04_share(self, context: dict[str, Any]) -> dict[str, Any]:
        """品牌 / 产品 / 服务第一排序人数；分母是已建档人数，不写成定量占比。"""
        models = []
        for key in context["keys"]:
            archives = context["archives"][key]
            entries = archives["values"].get("brand_product_service_rank") or []
            counter: Counter[str] = Counter()
            for entry in entries:
                items = [str(item).strip() for item in entry.get("items") or [] if str(item).strip()]
                if items:
                    counter[items[0]] += 1
            archived = int((archives.get("coverage") or {}).get("archived") or 0)
            rows = [
                [name, str(count), f"{count}/{archived}" if archived else "—"]
                for name, count in counter.most_common()
            ]
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "n": archived,
                    "columns": ["第一排序", "人数", "占已建档"],
                    "rows": rows,
                    "status": "ok" if rows else "missing",
                    "note": f"深访排序题，仅统计第一顺位；分母为已建档 {archived} 人，不与定量勾选率混用。",
                }
            )
        return {"kind": "per_model", "models": models, "availability": _availability(m["status"] for m in models)}

    # ---------------------------------------------------------------- P05

    def _build_p05_win(self, context: dict[str, Any]) -> dict[str, Any]:
        models = []
        for key in context["keys"]:
            metric = self._metric(context["analysed"][key], "winloss", "q3_23")
            rows = [
                [item["label"], str(item.get("count")), _ratio_text(item)]
                for item in sorted(metric.get("items") or [], key=lambda item: (-item.get("count", 0), item.get("label", "")))
                if item.get("count")
            ]
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "n": metric.get("n"),
                    "answered": metric.get("answered"),
                    "columns": ["选择原因", "勾选人数", "人数 / 分母（勾选率）"],
                    "rows": rows,
                    "status": metric.get("status") or ("ok" if rows else "missing"),
                    "note": metric.get("note", ""),
                }
            )
        return {"kind": "per_model", "models": models, "availability": _availability(m["status"] for m in models)}

    def _build_p05_competitors(self, context: dict[str, Any]) -> dict[str, Any]:
        models = []
        for key in context["keys"]:
            metric = self._metric(context["analysed"][key], "winloss", "loss_split")
            rows = []
            for item in metric.get("items") or []:
                reasons = "；".join(
                    f"{reason['label']} {reason.get('count')}/{reason.get('n')}"
                    + (f"（{reason['ratio']}%）" if reason.get("ratio") is not None else "")
                    for reason in (item.get("reasons") or [])[:3]
                )
                rows.append(
                    [
                        item.get("label", ""),
                        str(item.get("count")),
                        _pct(item.get("ratio")),
                        reasons or "—",
                    ]
                )
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "n": metric.get("n"),
                    "columns": ["最终购买车型", "人数", "占比（分母=对比过本品人数）", "主要原因（人数 / 该行人数）"],
                    "rows": rows,
                    "status": metric.get("status") or ("ok" if rows else "missing"),
                    "note": metric.get("note", ""),
                }
            )
        return {"kind": "per_model", "models": models, "availability": _availability(m["status"] for m in models)}

    def _build_p05_win_quotes(self, context: dict[str, Any]) -> dict[str, Any]:
        models = []
        for key in context["keys"]:
            metric = self._metric(context["analysed"][key], "winloss", "win_quotes")
            items = [
                {"code": item.get("respondent_code", ""), "text": item.get("quote", ""), "suspect": False}
                for item in (metric.get("items") or [])[:4]
            ]
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "people": metric.get("people", 0),
                    "items": items,
                    "status": metric.get("status") or ("ok" if items else "missing"),
                    "note": metric.get("note", ""),
                }
            )
        return {
            "kind": "quotes",
            "models": models,
            "note": "深访原话逐条列示，标注受访者编号；不做比例。",
            "availability": _availability(model["status"] for model in models),
        }

    # ---------------------------------------------------------------- P07

    def _build_p07_overall(self, context: dict[str, Any]) -> dict[str, Any]:
        models = []
        for key in context["keys"]:
            metric = self._metric(context["analysed"][key], "satisfaction", "overall")
            items = [
                {
                    "label": "整体使用满意度",
                    "value": _mean_text(metric.get("mean")),
                    "sub": f"作答 {metric.get('answered')}/{metric.get('n')}",
                }
            ]
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "n": metric.get("n"),
                    "items": items,
                    "status": metric.get("status") or "missing",
                    "note": metric.get("note", ""),
                }
            )
        return {"kind": "kv", "models": models, "availability": _availability(m["status"] for m in models)}

    def _build_p07_dimensions(self, context: dict[str, Any]) -> dict[str, Any]:
        models = []
        for key in context["keys"]:
            metric = self._metric(context["analysed"][key], "satisfaction", "dimensions")
            items = [
                {
                    "label": item["label"],
                    "value": item.get("mean"),
                    "text": f"{item.get('answered')}/{item.get('n')} 人作答",
                }
                for item in sorted(metric.get("top") or [], key=lambda item: -(item.get("mean") or 0))
            ]
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "n": metric.get("n"),
                    "items": items,
                    "status": metric.get("status") or ("ok" if items else "missing"),
                    "note": metric.get("note", ""),
                }
            )
        return {
            "kind": "bars",
            "unit": "分",
            "max": 10,
            "models": models,
            "note": "1–10 分均值，按均值降序；柱长为分值占 10 分的比例。",
            "availability": _availability(model["status"] for model in models),
        }

    def _build_p07_recommend(self, context: dict[str, Any]) -> dict[str, Any]:
        models = []
        for key in context["keys"]:
            metric = self._metric(context["analysed"][key], "satisfaction", "recommendation")
            items = [
                {"label": item["label"], "value": _pct(item.get("ratio")), "sub": f"{item.get('count')}/{item.get('n')}"}
                for item in metric.get("items") or []
            ]
            items.insert(0, {"label": "推荐意愿均值", "value": _mean_text(metric.get("mean")), "sub": f"作答 {metric.get('answered')}/{metric.get('n')}"})
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "n": metric.get("n"),
                    "items": items,
                    "status": metric.get("status") or "missing",
                    "note": metric.get("note", ""),
                }
            )
        return {"kind": "kv", "models": models, "availability": _availability(m["status"] for m in models)}

    def _build_p07_reputation(self, context: dict[str, Any]) -> dict[str, Any]:
        models = []
        for key in context["keys"]:
            metric = self._metric(context["analysed"][key], "satisfaction", "reputation")
            denominators = metric.get("denominators") or {}
            rows = []
            for direction, label in (("positive", "正向"), ("negative", "负向")):
                for item in (metric.get(direction) or [])[:5]:
                    rows.append(
                        [
                            label,
                            item.get("label", ""),
                            str(item.get("count")),
                            str(denominators.get(direction, "—")),
                            _pct(item.get("ratio")),
                        ]
                    )
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "n": denominators.get("positive"),
                    "columns": ["方向", "口碑点", "命中条数", "该方向分母", "占比"],
                    "rows": rows,
                    "status": "ok" if rows else "missing",
                    "note": metric.get("note") or "外部口碑（汽车之家 + 懂车帝）按 L3 标签统计，分母为该方向可统计口碑总条数。",
                }
            )
        return {"kind": "per_model", "models": models, "availability": _availability(m["status"] for m in models)}

    def _build_p07_points(self, context: dict[str, Any]) -> dict[str, Any]:
        models = []
        for key in context["keys"]:
            archives = context["archives"][key]
            items: list[dict[str, Any]] = []
            for dimension, prefix in (("satisfaction_points", "满意"), ("dissatisfaction_points", "不满")):
                for entry in _archive_quote_entries(archives["values"], dimension, limit=4):
                    items.append(
                        {
                            "code": entry["code"],
                            "text": f"{prefix}：{entry['text']}",
                            "suspect": entry["suspect"],
                        }
                    )
            filled = sum(1 for dimension in ("satisfaction_points", "dissatisfaction_points") if _dimension_filled(archives, dimension)[0])
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "people": archives["coverage"]["archived"],
                    "items": items[:6],
                    "status": "ok" if items else "missing",
                    "note": f"深访档案 {archives['coverage']['archived']} 人可读；{filled}/2 个维度有值。" if items else "该车型档案无满意点/不满点",
                }
            )
        return {
            "kind": "quotes",
            "models": models,
            "note": "深访逐人原话，不做比例；同一人可同时有满意点与不满点。",
            "availability": _availability(model["status"] for model in models),
        }

    # ---------------------------------------------------------------- P08

    def _build_p08_channels(self, context: dict[str, Any]) -> dict[str, Any]:
        return self._archive_matrix(
            context,
            dimension="info_channels",
            counter=lambda entries: ArchiveAggregator.channel_counts(entries),
            note="按渠道提及人数统计，一个人在同一渠道只计 1 人；未收进渠道表的原始写法归入「未归类」，不丢弃。",
        )

    def _build_p08_content(self, context: dict[str, Any]) -> dict[str, Any]:
        return self._archive_matrix(
            context,
            dimension="content_format_preference",
            counter=lambda entries: ArchiveAggregator.content_counts(entries),
            note="按内容形式提及人数统计，一个人可提及多种形式；分母为各车型已生成档案人数。",
        )

    def _archive_matrix(self, context, *, dimension: str, counter, note: str) -> dict[str, Any]:
        per_model: dict[str, dict[str, int]] = {}
        for key in context["keys"]:
            entries = context["archives"][key]["values"].get(dimension) or []
            per_model[key] = counter(entries)
        rows_keys: list[str] = []
        for counts in per_model.values():
            for name in counts:
                if name not in rows_keys:
                    rows_keys.append(name)
        rows_keys.sort(key=lambda name: (-sum(counts.get(name, 0) for counts in per_model.values()), name == UNCATEGORIZED, name))
        columns = [
            f"{self._model(key)['label']}"
            f"（n={context['archives'][key]['coverage']['archived']}）"
            for key in context["keys"]
        ]
        single = len(context["keys"]) == 1
        archived = int(context["archives"][context["keys"][0]]["coverage"]["archived"] or 0) if single else 0
        rows = []
        for name in rows_keys:
            row = [name] + [str(per_model[key].get(name, 0)) for key in context["keys"]]
            if single:
                count = per_model[context["keys"][0]].get(name, 0)
                row.append(f"{count}/{archived}" if archived else "—")
            rows.append(row)
        status = "ok" if rows else "missing"
        return {
            "kind": "matrix",
            "columns": ["项目"] + columns + (["占已建档"] if single else []),
            "rows": rows,
            "status": status,
            "note": f"{note} 合计可读档案 {archived or '多名'} 人，均为深访人数，不是定量比例。",
            "availability": status,
        }

    # ---------------------------------------------------------------- P10

    def _build_p10_risk(self, context: dict[str, Any]) -> dict[str, Any]:
        models = []
        for key in context["keys"]:
            archives = context["archives"][key]
            items: list[dict[str, Any]] = []
            for entry in archives["values"].get("conversion_opportunity_risk") or []:
                chunks = list(entry.get("items") or [])
                if not chunks and entry.get("text"):
                    chunks = [entry["text"]]
                for chunk in chunks[:2]:
                    items.append(
                        {
                            "code": entry.get("respondent_code", ""),
                            "text": chunk[:220],
                            "suspect": bool(entry.get("suspect")),
                        }
                    )
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "people": archives["coverage"]["archived"],
                    "items": items[:4],
                    "status": "ok" if items else "missing",
                    "note": f"档案 {archives['coverage']['archived']} 人可读，仅列原话与条件，不推断概率。" if items else "该车型档案无转化机会/风险",
                }
            )
        return {
            "kind": "quotes",
            "models": models,
            "note": "机会与风险均以「条件 + 动作」形式记录，来源为深访，非定量比例。",
            "availability": _availability(model["status"] for model in models),
        }

    # ---------------------------------------------------------------- P11

    def _build_p11_bullets(self, context: dict[str, Any]) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for key in context["keys"]:
            label = self._model(key)["label"]
            pieces: list[str] = []
            refs: list[str] = []
            attention = ((context["analysed"][key]["tiles"].get("attention") or {}).get("metrics") or [{}])[0]
            top_attention = (attention.get("top") or [None])[0]
            if top_attention:
                pieces.append(f"购车关注第一位是{top_attention['label']}（{_ratio_plain(top_attention)}）")
                refs.append("P04.TOP5")
            win = self._metric(context["analysed"][key], "winloss", "q3_23")
            top_win = (win.get("top") or [None])[0]
            if top_win:
                pieces.append(f"选择原因第一位是{top_win['label']}（{_ratio_plain(top_win)}）")
                refs.append("P05.WIN")
            loss = self._metric(context["analysed"][key], "winloss", "loss_split")
            top_loss = (loss.get("items") or [None])[0]
            if top_loss:
                pieces.append(
                    f"流失去向第一是{top_loss['label']}（{top_loss.get('count')}/{loss.get('n')}，{_pct(top_loss.get('ratio'))}）"
                )
                refs.append("P05.COMPETITORS")
            overall = self._metric(context["analysed"][key], "satisfaction", "overall")
            if overall.get("mean") is not None:
                pieces.append(f"整体满意度均值{overall['mean']}分（作答{overall.get('answered')}/{overall.get('n')}）")
                refs.append("P07.OVERALL")
            reputation = self._metric(context["analysed"][key], "satisfaction", "reputation")
            negative = (reputation.get("negative") or [None])[0]
            if negative:
                pieces.append(
                    f"外部口碑最集中的负向点是{negative['label']}（{negative.get('count')}/{reputation.get('denominators', {}).get('negative')}）"
                )
                refs.append("P07.REPUTATION")
            archive = context["archives"][key]["coverage"]
            pieces.append(f"深访档案{archive['archived']}/{archive['interview_total']}份可用")
            refs.append("A.BOUNDARY")
            items.append({"model": label, "text": f"{label}：" + "；".join(pieces) + "。", "refs": refs})
        items.append(
            {
                "model": "数据边界",
                "text": (
                    f"本期仅竞品侧，不含本品；定性模块为深访人数口径，不做比例；"
                    f"报告共记录 {len(context['keys'])} 款车型，数字均可回溯到对应页面与分母。"
                ),
                "refs": ["A.BOUNDARY", "A.GAPS"],
            }
        )
        return {"kind": "bullets", "items": items, "availability": "ok"}

    # ---------------------------------------------------------------- 附录

    def _build_a_boundary(self, context: dict[str, Any]) -> dict[str, Any]:
        columns = ["车型", "定量样本", "深访访谈数", "已生成档案", "缺失数据源"]
        rows = []
        for key in context["keys"]:
            sources = context["models_meta"].get(key, {})
            archive = context["archives"][key]["coverage"]
            rows.append(
                [
                    self._model(key)["label"],
                    str((sources.get("sources") or {}).get("quant", 0)),
                    str(archive["interview_total"]),
                    str(archive["archived"]),
                    "、".join(sources.get("missing_sources") or []) or "无",
                ]
            )
        return {"kind": "matrix", "columns": columns, "rows": rows, "status": "ok", "note": "定量样本为车型定量总样本；档案为当前有效 revision。", "availability": "ok"}

    def _build_a_gaps(self, context: dict[str, Any]) -> dict[str, Any]:
        rows = []
        for key in context["keys"]:
            archives = context["archives"][key]
            for dimension, name in (
                ("personality_interest_social", "生活状态与价值观"),
                ("purchase_motivation", "购车动机"),
                ("brand_product_service_rank", "品牌/产品/服务排序"),
                ("satisfaction_points", "满意点"),
                ("dissatisfaction_points", "不满点"),
                ("info_channels", "信息渠道"),
                ("content_format_preference", "内容形式偏好"),
                ("conversion_opportunity_risk", "转化机会/风险"),
            ):
                filled, total = _dimension_filled(archives, dimension)
                if filled < total:
                    rows.append([self._model(key)["label"], name, f"{filled}/{total}", "该车型部分档案无此维度取值"])
        attention = "库内无排序题，三类型第一排序无法计算"
        rows.append(["全部车型", "产品/品牌/服务第一排序", "—", attention])
        if not rows:
            rows.append(["全部车型", "无", "—", "—"])
        return {
            "kind": "matrix",
            "columns": ["车型", "维度", "有值 / 档案数", "说明"],
            "rows": rows,
            "status": "ok",
            "note": "缺口按档案逐维度统计，不补数、不插值。",
            "availability": "ok",
        }

    def _build_a_sources(self, context: dict[str, Any]) -> dict[str, Any]:
        rows = []
        for key in context["keys"]:
            analysis = context["analysed"][key]
            sources = analysis.get("sources") or {}
            rows.append(
                [
                    self._model(key)["label"],
                    "定量问卷",
                    str(sources.get("quant", 0)),
                    "quant_sample（车型全样本）",
                ]
            )
            rows.append(
                [
                    self._model(key)["label"],
                    "深访原话",
                    str(sources.get("interview", 0)),
                    "访谈库 Q29/Q27/Q28",
                ]
            )
            rows.append(
                [
                    self._model(key)["label"],
                    "外部口碑",
                    str(sources.get("reputation", 0)),
                    "汽车之家 + 懂车帝口碑",
                ]
            )
            rows.append(
                [
                    self._model(key)["label"],
                    "洞察档案",
                    str(context["archives"][key]["coverage"]["archived"]),
                    f"{context['archives'][key]['template_id']} {context['archives'][key]['template_version']}",
                ]
            )
        return {
            "kind": "matrix",
            "columns": ["车型", "数据源", "条数", "表 / 版本"],
            "rows": rows,
            "status": "ok",
            "note": "条数为取数时点计数，重跑会变化；变化会使版本指纹失效并标记 stale。",
            "availability": "ok",
        }

    # ---------------------------------------------------------------- 通用

    @staticmethod
    def _metric(analysis: dict[str, Any], tile: str, key: str) -> dict[str, Any]:
        for metric in ((analysis.get("tiles") or {}).get(tile) or {}).get("metrics") or []:
            if metric.get("key") == key:
                return metric
        return {}

    def _archive_quote_block(self, context: dict[str, Any], dimension: str, *, empty_note: str) -> dict[str, Any]:
        models = []
        for key in context["keys"]:
            archives = context["archives"][key]
            items = _archive_quote_entries(archives["values"], dimension)
            filled, total = _dimension_filled(archives, dimension)
            models.append(
                {
                    "key": key,
                    "label": self._model(key)["label"],
                    "people": filled,
                    "archived": total,
                    "items": items,
                    "status": "ok" if items else "missing",
                    "note": f"该车型 {filled}/{total} 份档案有此维度；深访人数口径，不做比例。" if items else empty_note,
                }
            )
        any_items = any(model["items"] for model in models)
        return {
            "kind": "quotes",
            "models": models,
            "note": "深访逐人原话；同一条可能由模型归纳，保留受访者编号便于追溯。" if any_items else empty_note,
            "availability": _availability(model["status"] for model in models),
        }

    def _source_rows(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for name, description in SOURCE_REGISTRY.items():
            rows.append({"name": name, "description": description})
        return rows

    # ---------------------------------------------------------------- 校验

    def _validate_content(self, content: dict[str, Any], outline: dict[str, Any]) -> None:
        declared = {
            block["id"]: block
            for page in list(outline["pages"]) + list(outline.get("appendices") or [])
            for block in page["blocks"]
        }
        seen: set[str] = set()
        for page in list(content["pages"]) + list(content["appendices"]):
            for block in page["blocks"]:
                block_id = block["id"]
                seen.add(block_id)
                if block["source"] != declared[block_id]["source"]:
                    raise ReportError("content_invalid", f"{block_id} 来源与大纲不一致", 500)
                if block["availability"] not in BLOCK_STATUSES:
                    raise ReportError("content_invalid", f"{block_id} 可用性非法", 500)
                if block.get("data_status") == "unavailable":
                    continue
                if block["type"] in {"table", "bars", "kv", "quotes"}:
                    if block.get("kind") == "matrix":
                        if not isinstance(block.get("rows"), list):
                            raise ReportError("content_invalid", f"{block_id} 缺少表格行", 500)
                        continue
                    models = block.get("models") or []
                    if not models:
                        raise ReportError("content_invalid", f"{block_id} 缺少车型数据", 500)
                    for model in models:
                        if model.get("n") is None and block["type"] != "quotes":
                            raise ReportError("content_invalid", f"{block_id} 的 {model.get('label')} 缺少分母 n", 500)
        missing = set(declared) - seen
        if missing:
            raise ReportError("content_invalid", f"大纲中的内容块未生成：{'、'.join(sorted(missing))}", 500)
        index = content.get("numeric_index") or {}
        if set(index) != seen:
            raise ReportError("content_invalid", "数字证据索引未覆盖全部内容块", 500)


__all__ = [
    "BciReportService",
    "PostgresReportStore",
    "ReportError",
    "SOURCE_REGISTRY",
    "REVISION_OPS",
    "bump_label",
    "collect_numbers",
    "load_outline",
    "numeric_index",
    "validate_outline",
]
