"""BCI-007 · 报告输出接口层。

对外只暴露报告域操作；数据读取、聚合、渲染、版本存储都在 service 内完成。
生成是同步接口：5 车实测约 23 秒，页面以进度态等待，避免留下没有状态查询的半套异步任务。
"""

from __future__ import annotations

import re
from typing import Any

from competitor_insight.server.report_service import SOURCE_REGISTRY, BciReportService, ReportError


class ReportApi:
    def __init__(self, service: BciReportService | None = None) -> None:
        self.service = service or BciReportService()

    # ---------------------------------------------------------------- 读

    def options(self) -> dict[str, Any]:
        return self.service.options()

    def outline(self) -> dict[str, Any]:
        return {"outline": self.service.outline(), "sources": SOURCE_REGISTRY}

    def versions(self, limit: int = 20) -> dict[str, Any]:
        return {"items": self.service.store.list_reports(limit=limit)}

    def detail(self, report_version_id: str) -> dict[str, Any]:
        row = self._version(report_version_id)
        stale, stale_reason = self._stale_state(row)
        return {
            "report_version_id": row["report_version_id"],
            "report_id": row["report_id"],
            "title": row["title"],
            "model_keys": row["model_keys"],
            "version_no": row["version_no"],
            "generated_at": row["generated_at"],
            "status": row["status"],
            "stale": stale,
            "stale_reason": stale_reason,
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

    def export(self, report_version_id: str) -> dict[str, Any]:
        row = self._version(report_version_id)
        self._stale_state(row)
        return {
            "html": row["html"],
            "filename": self._filename(row),
        }

    # ---------------------------------------------------------------- 写

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_keys = payload.get("model_keys")
        if model_keys is None:
            model_keys = []
        if not isinstance(model_keys, list):
            raise ReportError("invalid_request", "model_keys 必须为数组", 400)
        created_by = str(payload.get("created_by") or "web")[:32]
        return self.service.generate(model_keys, created_by=created_by)

    # ---------------------------------------------------------------- 内部

    def _version(self, report_version_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", str(report_version_id or "")):
            raise ReportError("invalid_request", "report_version_id 不合法", 400)
        row = self.service.store.get_version(report_version_id)
        if not row:
            raise ReportError("report_not_found", "报告版本不存在", 404)
        return row

    def _stale_state(self, row: dict[str, Any]) -> tuple[bool, str]:
        try:
            snapshot = self.service.snapshot(list(row["model_keys"] or []))
        except Exception as exc:  # noqa: BLE001
            return False, f"无法校验数据版本：{exc.__class__.__name__}"
        current = self.service.fingerprint(snapshot)
        if current == row["data_fingerprint"]:
            return False, ""
        reason = "底层样本量、档案修订、配置或模板已变化，当前报告为旧快照"
        if row.get("status") != "stale":
            try:
                self.service.store.mark_stale(row["report_version_id"], reason)
            except Exception:  # noqa: BLE001
                pass
        return True, row.get("stale_reason") or reason

    @staticmethod
    def _filename(row: dict[str, Any]) -> str:
        date = str(row.get("generated_at") or "")[:10].replace("-", "")
        return f"竞品用户洞察报告_v{row.get('version_no')}_{date or 'export'}.html"


__all__ = ["ReportApi"]
