"""BCI-004 · 档案导出（xlsx / md）。

- 纯内存生成，返回 `bytes`，不落 `outputs/`、不写临时文件；
- `xlsx` 支持 1–63 人合并（一人一列），`md` 只允许单人；
- 无来源维度保留整行，内容写「本期无来源：<原因>」，不写空字符串；
- 满意度评分按 `value_json.score` 判定 `explicit` / `missing`，缺失时保留原因文案。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from io import BytesIO
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from competitor_insight.server.archive_store import ArchiveFieldRecord, ArchiveRecord

SATISFACTION_DIMENSION_ID = "satisfaction_score"
NO_SOURCE_PREFIX = "本期无来源："

XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
MD_CONTENT_TYPE = "text/markdown; charset=utf-8"

_HEADER_FILL = PatternFill("solid", fgColor="1F3864")
_SUBHEADER_FILL = PatternFill("solid", fgColor="D9E2F3")
_NOSOURCE_FILL = PatternFill("solid", fgColor="FFF2CC")
_WHITE_BOLD = Font(color="FFFFFF", bold=True)
_WRAP_TOP = Alignment(wrap_text=True, vertical="top")


class ExportError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------- helpers


def has_value(field: ArchiveFieldRecord | None) -> bool:
    if field is None:
        return False
    if field.value_text not in (None, ""):
        return True
    return field.value_json not in (None, "", [], {})


def is_template_no_source(field: ArchiveFieldRecord) -> bool:
    return field.fill_mode == "none" and (field.source_ref or {}).get(
        "no_source_scope"
    ) == "template"


def display_value(field: ArchiveFieldRecord | None) -> str:
    if field is None:
        return ""
    if field.fill_mode == "none" or not has_value(field):
        reason = (field.no_data_reason or "访谈中未涉及该维度").strip()
        if is_template_no_source(field):
            return f"{NO_SOURCE_PREFIX}{reason}"
        return reason
    if isinstance(field.value_json, dict) and field.value_json.get("score") is not None:
        return field.value_text or f"{field.value_json['score']} 分"
    if isinstance(field.value_json, list):
        return "；".join(str(item) for item in field.value_json)
    return field.value_text or ""


def score_source(field: ArchiveFieldRecord | None) -> str | None:
    if field is None or field.dimension_id != SATISFACTION_DIMENSION_ID:
        return None
    explicit = (
        field.fill_mode == "derived"
        and isinstance(field.value_json, dict)
        and field.value_json.get("score") is not None
        and has_value(field)
    )
    return "explicit" if explicit else "missing"


def completeness(template: dict[str, Any], archive: ArchiveRecord) -> float:
    required = {
        dim["id"] for dim in template.get("dimensions", []) if dim.get("required", True)
    }
    if not required:
        return 0.0
    fields = {field.dimension_id: field for field in archive.fields}
    filled = sum(
        1
        for dim_id in required
        if has_value(fields.get(dim_id)) or (fields.get(dim_id) and fields[dim_id].no_data_reason)
    )
    return round(filled / len(required) * 100, 2)


def _group_names(template: dict[str, Any]) -> dict[str, str]:
    return {group.get("id"): group.get("name", group.get("id")) for group in template.get("groups", [])}


def _ordered_fields(
    template: dict[str, Any], archive: ArchiveRecord
) -> list[tuple[dict[str, Any], ArchiveFieldRecord | None]]:
    by_id = {field.dimension_id: field for field in archive.fields}
    ordered = [(dim, by_id.get(dim.get("id"))) for dim in template.get("dimensions", [])]
    known = {dim.get("id") for dim in template.get("dimensions", [])}
    ordered.extend(
        ({"id": field.dimension_id, "name": field.dimension_id, "group": field.group_id}, field)
        for field in archive.fields
        if field.dimension_id not in known
    )
    return ordered


def _respondent_label(respondent: dict[str, Any]) -> str:
    return str(
        respondent.get("respondent_code")
        or respondent.get("interview_id")
        or ""
    )


def _safe_filename_part(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", (value or "").strip()) or "未命名"


def xlsx_filename(template: dict[str, Any], count: int, day: date | None = None) -> str:
    name = _safe_filename_part(str(template.get("name") or template.get("template_id") or "洞察档案"))
    stamp = (day or date.today()).strftime("%Y%m%d")
    return f"用户洞察档案_{name}_{count}人_{stamp}.xlsx"


def md_filename(respondent: dict[str, Any]) -> str:
    label = _safe_filename_part(_respondent_label(respondent))
    city = _safe_filename_part(str(respondent.get("city") or "未知城市"))
    return f"用户洞察档案_{label}_{city}.md"


# ----------------------------------------------------------------------- xlsx


def build_xlsx(
    template: dict[str, Any],
    archives: Iterable[ArchiveRecord],
    respondents: dict[str, dict[str, Any]],
    *,
    generated_at: str | None = None,
    day: date | None = None,
) -> tuple[bytes, str]:
    archive_list = list(archives)
    if not archive_list:
        raise ExportError("empty_selection", "至少选择一位受访者再导出")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "洞察档案"
    groups = _group_names(template)

    total_columns = 2 + len(archive_list)
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_columns)
    title = sheet.cell(row=1, column=1)
    title.value = (
        f"用户洞察档案 · {template.get('name') or template.get('template_id')} "
        f"{template.get('version') or ''} · {len(archive_list)} 人"
    )
    title.font = Font(color="FFFFFF", bold=True, size=13)
    title.fill = _HEADER_FILL
    title.alignment = Alignment(horizontal="left", vertical="center")
    sheet.row_dimensions[1].height = 24

    headers = ["模块", "子项"] + [
        _respondent_label(respondents.get(archive.interview_id, {"interview_id": archive.interview_id}))
        for archive in archive_list
    ]
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row=2, column=column, value=header)
        cell.font = _WHITE_BOLD
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    fields_by_archive = [
        {field.dimension_id: field for field in archive.fields} for archive in archive_list
    ]
    row_index = 3
    for dim in template.get("dimensions", []):
        dim_id = dim.get("id")
        group_cell = sheet.cell(row=row_index, column=1, value=groups.get(dim.get("group"), dim.get("group")))
        group_cell.font = _WHITE_BOLD
        group_cell.fill = _HEADER_FILL
        group_cell.alignment = _WRAP_TOP

        name_cell = sheet.cell(row=row_index, column=2, value=dim.get("name", dim_id))
        name_cell.fill = _SUBHEADER_FILL
        name_cell.alignment = _WRAP_TOP

        for offset, field_map in enumerate(fields_by_archive):
            field = field_map.get(dim_id)
            cell = sheet.cell(row=row_index, column=3 + offset, value=display_value(field))
            cell.alignment = _WRAP_TOP
            if field is not None and is_template_no_source(field):
                cell.fill = _NOSOURCE_FILL
        row_index += 1

    sheet.column_dimensions["A"].width = 18
    sheet.column_dimensions["B"].width = 26
    for offset in range(len(archive_list)):
        sheet.column_dimensions[get_column_letter(3 + offset)].width = 45
    sheet.freeze_panes = "C3"

    _write_scope_sheet(workbook, template, archive_list, respondents, generated_at)
    _write_evidence_sheet(workbook, template, archive_list, respondents)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), xlsx_filename(template, len(archive_list), day)


def _write_scope_sheet(
    workbook: Workbook,
    template: dict[str, Any],
    archives: list[ArchiveRecord],
    respondents: dict[str, dict[str, Any]],
    generated_at: str | None,
) -> None:
    sheet = workbook.create_sheet("口径与证据")
    stamps = [archive.generated_at for archive in archives if archive.generated_at]
    rows = [
        ("模板 ID", template.get("template_id")),
        ("模板名称", template.get("name")),
        ("模板版本", template.get("version")),
        ("导出人数", len(archives)),
        ("生成时间", generated_at or (max(stamps) if stamps else "")),
        ("模型", ", ".join(sorted({a.model for a in archives if a.model}))),
        ("Prompt 版本", ", ".join(sorted({a.prompt_version for a in archives if a.prompt_version}))),
    ]
    for row, (label, value) in enumerate(rows, start=1):
        key = sheet.cell(row=row, column=1, value=label)
        key.font = Font(bold=True)
        sheet.cell(row=row, column=2, value=value if value is not None else "")

    start = len(rows) + 2
    headers = ["受访者", "编号", "城市", "车型", "状态", "覆盖率", "完整率", "无数据维度"]
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row=start, column=column, value=header)
        cell.font = _WHITE_BOLD
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    names = {dim.get("id"): dim.get("name", dim.get("id")) for dim in template.get("dimensions", [])}
    for offset, archive in enumerate(archives):
        respondent = respondents.get(archive.interview_id, {"interview_id": archive.interview_id})
        no_data = [
            names.get(field.dimension_id, field.dimension_id)
            for field in archive.fields
            if field.fill_mode == "none"
        ]
        values = [
            _respondent_label(respondent),
            archive.interview_id,
            respondent.get("city") or "",
            respondent.get("vehicle_model") or "",
            archive.status,
            archive.coverage_required,
            completeness(template, archive),
            "、".join(no_data),
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=start + 1 + offset, column=column, value=value)
            cell.alignment = _WRAP_TOP

    for column, width in enumerate((14, 12, 12, 14, 10, 10, 10, 60), start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width


def _write_evidence_sheet(
    workbook: Workbook,
    template: dict[str, Any],
    archives: list[ArchiveRecord],
    respondents: dict[str, dict[str, Any]],
) -> None:
    sheet = workbook.create_sheet("证据")
    headers = ["受访者", "维度", "证据 ID", "类型", "题号", "说话人", "原话"]
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=column, value=header)
        cell.font = _WHITE_BOLD
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    names = {dim.get("id"): dim.get("name", dim.get("id")) for dim in template.get("dimensions", [])}
    row = 2
    for archive in archives:
        label = _respondent_label(respondents.get(archive.interview_id, {"interview_id": archive.interview_id}))
        for field in archive.fields:
            for ref in field.evidence_refs or []:
                values = [
                    label,
                    names.get(field.dimension_id, field.dimension_id),
                    ref.get("id"),
                    ref.get("kind"),
                    ref.get("question_id"),
                    ref.get("speaker"),
                    ref.get("quote"),
                ]
                for column, value in enumerate(values, start=1):
                    cell = sheet.cell(row=row, column=column, value=value)
                    cell.alignment = _WRAP_TOP
                row += 1

    for column, width in enumerate((12, 18, 24, 14, 8, 10, 60), start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width


# ------------------------------------------------------------------------- md


def build_md(
    template: dict[str, Any],
    archive: ArchiveRecord,
    respondent: dict[str, Any],
) -> tuple[bytes, str]:
    groups = _group_names(template)
    label = _respondent_label(respondent) or archive.interview_id
    place = " · ".join(
        str(part) for part in (respondent.get("city"), respondent.get("vehicle_model")) if part
    )
    header = f"# 用户洞察档案 · {label}" + (f"（{place}）" if place else "")

    lines = [
        header,
        "",
        f"- 模板：{template.get('name') or template.get('template_id')} {template.get('version') or ''}".rstrip(),
        f"- 状态：{archive.status}",
        f"- 覆盖率：{archive.coverage_required}%",
        f"- 完整率：{completeness(template, archive)}%",
        f"- 生成时间：{archive.generated_at or ''}",
        f"- 模型：{archive.model or ''}",
        "",
    ]

    current_group = None
    evidence_lines: list[str] = []
    names = {dim.get("id"): dim.get("name", dim.get("id")) for dim in template.get("dimensions", [])}

    for dim, field in _ordered_fields(template, archive):
        group_id = dim.get("group")
        if group_id != current_group:
            current_group = group_id
            lines.extend([f"## {groups.get(group_id, group_id)}", ""])
        lines.append(f"- **{dim.get('name') or dim.get('id')}**：{display_value(field)}")
        if field is not None:
            for ref in field.evidence_refs or []:
                quote = (ref.get("quote") or "").strip()
                lost = "（来源已失效）" if ref.get("source_missing") else ""
                evidence_lines.append(
                    f"- {names.get(field.dimension_id, field.dimension_id)} / "
                    f"Q{ref.get('question_id') or '?'} / {ref.get('speaker') or '未知'}："
                    f"「{quote}」{lost}"
                )

    if evidence_lines:
        lines.extend(["", "## 证据索引", ""])
        lines.extend(evidence_lines)

    return ("\n".join(lines) + "\n").encode("utf-8"), md_filename(respondent)


def default_generated_at() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
