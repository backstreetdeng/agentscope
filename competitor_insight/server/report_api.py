"""BCI-007 · 报告输出接口层。

对外只暴露报告域操作；数据读取、聚合、渲染、版本存储都在 service 内完成。
口径：一个目标车型一份报告；改稿只接受受控指令并落成子版本 v1.0 → v1.1。
"""

from __future__ import annotations

import re
from typing import Any

from competitor_insight.server.report_service import SOURCE_REGISTRY, BciReportService, ReportError
from competitor_insight.server.report_render_html import render_report_page_html


class ReportApi:
    def __init__(self, service: BciReportService | None = None, *, attack_llm: Any = None) -> None:
        self.service = service or BciReportService(attack_llm=attack_llm)

    # ---------------------------------------------------------------- 读

    def options(self) -> dict[str, Any]:
        payload = self.service.options()
        payload["fingerprint_rule"] = self.service.fingerprint_rule()
        return payload

    def outline(self) -> dict[str, Any]:
        return {"outline": self.service.outline(), "sources": SOURCE_REGISTRY}

    def versions(self, model_key: str | None = None, limit: int = 50) -> dict[str, Any]:
        key = str(model_key or "").strip() or None
        items = self.service.store.list_versions(model_key=key, limit=limit)
        return {"items": self._evaluate(items)}

    def version_line(self, report_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", str(report_id or "")):
            raise ReportError("invalid_request", "report_id 不合法", 400)
        return {"items": self.service.store.version_line(report_id)}

    def detail(self, report_version_id: str) -> dict[str, Any]:
        row = self._version(report_version_id)
        stale, stale_reason = self._stale_state(row)
        upgrade = self.service.upgrade_state(row["content"])
        return {
            "report_version_id": row["report_version_id"],
            "report_id": row["report_id"],
            "title": row["title"],
            "model_key": row["model_key"],
            "model_keys": row["model_keys"],
            "legacy": row["legacy"],
            "version_no": row["version_no"],
            "version_label": row["version_label"],
            "parent_version_id": row["parent_version_id"],
            "revision_kind": row["revision_kind"],
            "patch": row["patch"],
            "generated_at": row["generated_at"],
            "status": row["status"],
            "stale": stale,
            "stale_reason": stale_reason,
            "upgrade": upgrade,
            "content": row["content"],
        }

    def preview(self, report_version_id: str) -> dict[str, Any]:
        row = self._version(report_version_id)
        stale, stale_reason = self._stale_state(row)
        return {
            "html": row["html"],
            "filename": self._filename(row),
            "stale": stale,
            "stale_reason": stale_reason,
        }

    def page(self, report_version_id: str, page_id: str) -> dict[str, Any]:
        """单页视图：只渲染这一页；整篇导出仍走 export。"""
        row = self._version(report_version_id)
        page = str(page_id or "").strip()
        if not re.fullmatch(r"(P\d{2}|APPENDIX)", page):
            raise ReportError("invalid_request", "page 参数不合法", 400)
        pages = list((row["content"] or {}).get("pages") or [])
        target = next((item for item in pages if str(item.get("page")) == page), None)
        if target is None:
            raise ReportError("page_not_found", f"报告里没有这一页：{page}", 404)
        return {
            "html": render_report_page_html(row["content"], page),
            "page": page,
            "title": target.get("title"),
            "ordinal": pages.index(target) + 1,
            "total": len(pages),
            "filename": self._filename(row),
        }

    def export(self, report_version_id: str) -> dict[str, Any]:
        row = self._version(report_version_id)
        self._stale_state(row)
        return {
            "html": row["html"],
            "filename": self._filename(row),
        }

    def compare(self, base_id: str, target_id: str) -> dict[str, Any]:
        base = self._valid_id(base_id)
        target = self._valid_id(target_id)
        self._version(base)
        self._version(target)
        return self.service.compare(base, target)

    def delete_version(self, report_version_id: str) -> dict[str, Any]:
        """软删除：库里保留记录，列表/下拉/详情不再返回。"""
        rid = self._valid_id(report_version_id)
        row = self.service.store.get_version(rid)
        if not row:
            raise ReportError("report_version_not_found", "报告版本不存在", 404)
        if row.get("deleted_at"):
            raise ReportError("report_version_deleted", "该版本已删除，不能重复删除", 409)
        if not self.service.store.soft_delete_version(rid):
            raise ReportError("report_version_deleted", "该版本已删除，不能重复删除", 409)
        return {
            "deleted": True,
            "report_version_id": rid,
            "report_id": row["report_id"],
            "version_label": row["version_label"],
            "deleted_at": row.get("generated_at"),
        }

    # ---------------------------------------------------------------- 写

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_key = payload.get("model_key")
        if model_key is None:
            model_keys = payload.get("model_keys")
            if isinstance(model_keys, list):
                if len(model_keys) > 1:
                    raise ReportError("multi_model_not_supported", "报告固定为一个目标车型一份，请只选择一个车型", 400)
                model_key = model_keys[0] if model_keys else None
            elif isinstance(model_keys, str):
                model_key = model_keys
        if model_key is None:
            raise ReportError("invalid_request", "请选择一个目标车型", 400)
        created_by = str(payload.get("created_by") or "web")[:32]
        return self.service.generate(str(model_key), created_by=created_by)

    def revise(self, payload: dict[str, Any]) -> dict[str, Any]:
        report_version_id = self._valid_id(payload.get("report_version_id"))
        created_by = str(payload.get("created_by") or "web")[:32]
        return self.service.revise(report_version_id, payload.get("operations"), created_by=created_by)

    # ---------------------------------------------------------------- 内部

    @staticmethod
    def _valid_id(report_version_id: Any) -> str:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", str(report_version_id or "")):
            raise ReportError("invalid_request", "report_version_id 不合法", 400)
        return str(report_version_id)

    def _version(self, report_version_id: str) -> dict[str, Any]:
        row = self.service.store.get_version(self._valid_id(report_version_id))
        if not row:
            raise ReportError("report_version_not_found", "报告版本不存在", 404)
        if row.get("deleted_at"):
            raise ReportError("report_version_deleted", "该版本已删除", 409)
        return row

    def _current_fp(self, model_key: str) -> str | None:
        try:
            return self.service.fingerprint(self.service.snapshot([model_key]))
        except Exception:  # noqa: BLE001
            return None

    def _evaluate(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按数据指纹即时校正每版状态；大纲/渲染器升级不参与判定。"""
        cache: dict[str, str | None] = {}
        for item in items:
            key = item.get("model_key") or ""
            if key not in cache:
                cache[key] = self._current_fp(key)
            current = cache[key]
            if current is None:
                continue
            if item.get("data_fingerprint") == current:
                if item.get("status") == "stale":
                    try:
                        self.service.store.mark_valid(item["report_version_id"])
                    except Exception:  # noqa: BLE001
                        pass
                item["status"] = "valid"
                item["stale_reason"] = ""
            else:
                reason = "底层数据已变化，当前报告为旧快照"
                if item.get("status") != "stale":
                    try:
                        self.service.store.mark_stale(item["report_version_id"], reason)
                    except Exception:  # noqa: BLE001
                        pass
                item["status"] = "stale"
                item["stale_reason"] = item.get("stale_reason") or reason
        return items

    def _stale_state(self, row: dict[str, Any]) -> tuple[bool, str]:
        snapshot = None
        try:
            snapshot = self.service.snapshot([row["model_key"]])
        except Exception as exc:  # noqa: BLE001
            return False, f"无法校验数据版本：{exc.__class__.__name__}"
        current = self.service.fingerprint(snapshot)
        if current == row["data_fingerprint"]:
            if row.get("status") == "stale":
                try:
                    self.service.store.mark_valid(row["report_version_id"])
                except Exception:  # noqa: BLE001
                    pass
            return False, ""
        reason = self.service.data_reason(row.get("source_snapshot"), snapshot)
        if row.get("status") != "stale":
            try:
                self.service.store.mark_stale(row["report_version_id"], reason)
            except Exception:  # noqa: BLE001
                pass
        return True, reason

    @staticmethod
    def _filename(row: dict[str, Any]) -> str:
        date = str(row.get("generated_at") or "")[:10].replace("-", "")
        label = str(row.get("version_label") or f"v{row.get('version_no')}").lstrip("v")
        return f"竞品用户洞察报告_v{label}_{date or 'export'}.html"


__all__ = ["ReportApi"]
