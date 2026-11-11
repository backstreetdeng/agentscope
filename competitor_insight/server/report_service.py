"""BCI-007 · 报告输出（HTML v1）。

骨架（用户 2026-11-11 确认）：
- 报告是「组竞品」报告，只覆盖竞品侧，不含本品对标；
- 契约以 `config/report_outline.json` 为唯一来源：每页每块先声明 type/source/required，服务端逐块落内容并校验；
- 所有数字来自即时分析取数或档案聚合，正文不写字面数字，样式与措辞不隐藏分母；
- 报告不调用大模型，P11 小结由数据确定性拼装，重跑结果稳定；
- 版本按 `data_fingerprint` 幂等：同指纹直接复用最新有效版本，不产重复版本。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from competitor_insight.server import db
from competitor_insight.server.analysis_service import AnalysisError, AnalysisService
from competitor_insight.server.channel_normalizer import UNCATEGORIZED
from competitor_insight.server.report_archive_aggregate import ArchiveAggregator, ArchiveUnavailable
from competitor_insight.server.report_render_html import RENDERER_VERSION, render_report_html

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTLINE_PATH = PROJECT_ROOT / "competitor_insight/config/report_outline.json"
CONFIG_PATH = PROJECT_ROOT / "competitor_insight/config/analysis_models.json"

BLOCK_TYPES = {"table", "bars", "kv", "quotes", "bullets"}
BLOCK_STATUSES = {"ok", "partial", "insufficient", "missing", "empty"}

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
        if not blocks:
            raise ReportError("outline_invalid", f"{page_id} 没有任何内容块", 500)
        for block in blocks:
            block_id = str(block.get("id") or "")
            if not block_id or block_id in block_ids:
                raise ReportError("outline_invalid", f"内容块 id 为空或重复：{block_id}", 500)
            block_ids.add(block_id)
            if block.get("type") not in BLOCK_TYPES:
                raise ReportError("outline_invalid", f"{block_id} 类型不受支持：{block.get('type')}", 500)
            if block.get("source") not in SOURCE_REGISTRY:
                raise ReportError("outline_invalid", f"{block_id} 来源未登记：{block.get('source')}", 500)
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

    def ensure_report(self, title: str, model_keys: list[str], scope: dict[str, Any], created_by: str) -> str:
        rows = self._run(
            """
            select report_id from bci.report
            where model_keys = %s::jsonb
            order by created_at desc limit 1
            """,
            (json.dumps(model_keys, ensure_ascii=False),),
        )
        if rows:
            return str(rows[0][0])
        report_id = str(uuid.uuid4())
        self._run(
            """
            insert into bci.report (report_id, title, model_keys, sample_scope, created_by)
            values (%s, %s, %s::jsonb, %s::jsonb, %s)
            """,
            (
                report_id,
                title,
                json.dumps(model_keys, ensure_ascii=False),
                json.dumps(scope, ensure_ascii=False),
                created_by,
            ),
            fetch=False,
        )
        return report_id

    def find_by_fingerprint(self, fingerprint: str, model_keys: list[str]) -> dict[str, Any] | None:
        rows = self._run(
            """
            select v.report_version_id, v.report_id, v.version_no, v.generated_at, r.title
            from bci.report_version v
            join bci.report r using (report_id)
            where r.model_keys = %s::jsonb and v.data_fingerprint = %s and v.status = 'valid'
            order by v.generated_at desc limit 1
            """,
            (json.dumps(model_keys, ensure_ascii=False), fingerprint),
        )
        if not rows:
            return None
        return {
            "report_version_id": str(rows[0][0]),
            "report_id": str(rows[0][1]),
            "version_no": int(rows[0][2]),
            "generated_at": rows[0][3].isoformat() if hasattr(rows[0][3], "isoformat") else str(rows[0][3]),
            "title": rows[0][4],
        }

    def save_version(
        self,
        report_id: str,
        content: dict[str, Any],
        html: str,
        fingerprint: str,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        version_id = str(uuid.uuid4())
        rows = self._run(
            """
            insert into bci.report_version
                (report_version_id, report_id, version_no, content, html, data_fingerprint, source_snapshot)
            select %s, %s, coalesce(max(version_no), 0) + 1, %s::jsonb, %s, %s, %s::jsonb
            from bci.report_version where report_id = %s
            returning version_no, generated_at
            """,
            (
                version_id,
                report_id,
                json.dumps(content, ensure_ascii=False),
                html,
                fingerprint,
                json.dumps(snapshot, ensure_ascii=False),
                report_id,
            ),
        )
        return {
            "report_version_id": version_id,
            "report_id": report_id,
            "version_no": int(rows[0][0]),
            "generated_at": rows[0][1].isoformat() if hasattr(rows[0][1], "isoformat") else str(rows[0][1]),
        }

    def list_reports(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._run(
            """
            select v.report_version_id, v.report_id, r.title, r.model_keys, v.version_no,
                   v.generated_at, v.status, v.stale_reason, v.data_fingerprint
            from bci.report_version v
            join bci.report r using (report_id)
            order by v.generated_at desc
            limit %s
            """,
            (int(limit),),
        )
        return [
            {
                "report_version_id": str(row[0]),
                "report_id": str(row[1]),
                "title": row[2],
                "model_keys": row[3],
                "version_no": int(row[4]),
                "generated_at": row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5]),
                "status": row[6],
                "stale_reason": row[7] or "",
                "data_fingerprint": row[8],
            }
            for row in rows
        ]

    def get_version(self, report_version_id: str) -> dict[str, Any] | None:
        rows = self._run(
            """
            select v.report_version_id, v.report_id, r.title, r.model_keys, v.version_no, v.content,
                   v.html, v.data_fingerprint, v.source_snapshot, v.generated_at, v.status, v.stale_reason
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
            "version_no": int(row[4]),
            "content": row[5],
            "html": row[6],
            "data_fingerprint": row[7],
            "source_snapshot": row[8],
            "generated_at": row[9].isoformat() if hasattr(row[9], "isoformat") else str(row[9]),
            "status": row[10],
            "stale_reason": row[11] or "",
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
    ) -> None:
        self.analysis = analysis or AnalysisService()
        self.archive = archive or ArchiveAggregator(connect=lambda: db.connect(db.load_env()))
        self.store = store or PostgresReportStore()
        self._outline_path = Path(outline_path or OUTLINE_PATH)
        self._outline: dict[str, Any] | None = None

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

    def generate(self, model_keys: Iterable[str], created_by: str = "web") -> dict[str, Any]:
        keys = self._normalize_keys(model_keys)
        # 先用轻量快照判定是否已有同版本，命中直接复用，不为重复点击重跑完整取数。
        fingerprint = self.fingerprint(self.snapshot(keys))
        existing = self.store.find_by_fingerprint(fingerprint, keys)
        if existing:
            return {
                "created": False,
                "reused": True,
                "report_id": existing["report_id"],
                "report_version_id": existing["report_version_id"],
                "version_no": existing["version_no"],
                "generated_at": existing["generated_at"],
                "title": existing["title"],
                "summary": None,
            }

        content, snapshot = self.build(keys)
        fingerprint = self.fingerprint(snapshot)
        existing = self.store.find_by_fingerprint(fingerprint, keys)
        if existing:
            return {
                "created": False,
                "reused": True,
                "report_id": existing["report_id"],
                "report_version_id": existing["report_version_id"],
                "version_no": existing["version_no"],
                "generated_at": existing["generated_at"],
                "title": existing["title"],
                "summary": None,
            }

        html = render_report_html(content)
        report_id = self.store.ensure_report(content["title"], keys, content["scope"], created_by)
        saved = self.store.save_version(report_id, content, html, fingerprint, snapshot)
        return {
            "created": True,
            "reused": False,
            "report_id": saved["report_id"],
            "report_version_id": saved["report_version_id"],
            "version_no": saved["version_no"],
            "generated_at": saved["generated_at"],
            "title": content["title"],
            "summary": self._response_summary(content),
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

    def _normalize_keys(self, model_keys: Iterable[str]) -> list[str]:
        config = self.analysis.config()
        order = [model["key"] for model in config["models"]]
        wanted = [str(key).strip() for key in (model_keys or []) if str(key or "").strip()]
        if not wanted:
            wanted = [config.get("default_model") or order[0]]
        unknown = [key for key in wanted if key not in order]
        if unknown:
            raise ReportError("model_not_found", f"车型不在配置清单中：{'、'.join(unknown)}", 404)
        return [key for key in order if key in wanted]

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
        for page in outline["pages"]:
            pages.append(self._render_page(page, context, gaps))
        appendices = [self._render_page(page, context, gaps) for page in outline.get("appendices") or []]

        content = {
            "outline_version": outline["version"],
            "title": f"{len(model_keys)} 款车型竞品用户洞察报告",
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

    def _render_page(self, page: dict[str, Any], context: dict[str, Any], gaps: list[dict[str, str]]) -> dict[str, Any]:
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
        return {
            "page": page["page"],
            "title": page["title"],
            "subtitle": page.get("subtitle", ""),
            "blocks": blocks,
            "availability": _availability(block["availability"] for block in blocks),
        }

    def _render_block(self, block: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        builder = getattr(self, f"_build_{block['id'].replace('.', '_').lower()}", None)
        if builder is None:
            raise ReportError("outline_invalid", f"内容块 {block['id']} 没有实现", 500)
        data = builder(context)
        data.update({"id": block["id"], "type": block["type"], "title": block["title"], "source": block["source"]})
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
        rows = [[name] + [str(per_model[key].get(name, 0)) for key in context["keys"]] for name in rows_keys]
        archived = sum(context["archives"][key]["coverage"]["archived"] for key in context["keys"])
        status = "ok" if rows else "missing"
        return {
            "kind": "matrix",
            "columns": ["项目"] + columns,
            "rows": rows,
            "status": status,
            "note": f"{note} 合计可读档案 {archived} 人，均为深访人数，不是定量比例。",
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


__all__ = [
    "BciReportService",
    "PostgresReportStore",
    "ReportError",
    "SOURCE_REGISTRY",
    "load_outline",
    "validate_outline",
]
