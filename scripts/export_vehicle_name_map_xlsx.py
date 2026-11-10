"""把车系名称映射库导出为业务核对用的 Excel（三张表 + README）。

输入：
    competitor_insight/config/vehicle_name_map.json（scripts/build_vehicle_name_map.py 产物）
输出：
    outputs/competitor-insights/BCI-006/20261110-vehicle-name-map/车系名称映射表_20261110.xlsx
    outputs/competitor-insights/BCI-006/20261110-vehicle-name-map/README.md

三张表：
    1 待业务确认（274 种）：业务填写「业务确认标准名」「备注」两列；
    2 已自动归一（758 种）：按标准名分组着色；认为归错的在「业务确认标准名」里改；
    3 定量车型待补（purchase_model 的 14 种）：业务补标准名。

副作用：只写 outputs 下的两个文件，不改映射库、不改业务代码。
重复执行会覆盖同名文件；文件名中的日期取自运行当天。
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "competitor_insight" / "config" / "vehicle_name_map.json"
OUT_DIR = ROOT / "outputs" / "competitor-insights" / "BCI-006" / f"{date.today():%Y%m%d}-vehicle-name-map"

HEAD_FILL = PatternFill("solid", fgColor="1F3B63")
HEAD_FONT = Font(bold=True, color="FFFFFF", size=10.5)
INPUT_FILL = PatternFill("solid", fgColor="FFF7E0")
GROUP_FILLS = (PatternFill("solid", fgColor="FFFFFF"), PatternFill("solid", fgColor="EEF3FA"))
THIN = Side(style="thin", color="D6DEEA")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BODY_FONT = Font(size=10)
WRAP = Alignment(vertical="center", wrap_text=True)
CENTER = Alignment(horizontal="center", vertical="center")


def norm(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", text)


def candidates_for(raw: str, standards: list[str], limit: int = 3) -> list[tuple[str, float]]:
    key = norm(raw)
    scored = []
    for standard in standards:
        target = norm(standard)
        if not target or not key:
            continue
        ratio = difflib.SequenceMatcher(None, key, target).ratio()
        if ratio >= 0.5:
            scored.append((standard, round(ratio, 3)))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored[:limit]


def suggest_standard(raw: str, candidate: str | None, score: float) -> str:
    """给出「建议标准名」：只在证据够硬时填，宁可空着也不误导业务。

    两条例外：相似度 ≥0.84；或候选写法完整包含原始写法（同一款车补了品牌/能源后缀），
    反向包含（原始写法更细，如「别克GL8高定」→「别克GL8」）不填，避免把细分款并成基础款。
    """
    if not candidate:
        return ""
    if score >= 0.84:
        return candidate
    key, target = norm(raw), norm(candidate)
    if len(key) >= 4 and key in target:
        return candidate
    return ""


def write_sheet(ws, headers, rows, widths, input_columns=(), group_column=None):
    ws.append(headers)
    for column, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=column)
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = CENTER
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(column)].width = widths[column - 1]
    ws.row_dimensions[1].height = 26

    group_index = 0
    previous = None
    for row in rows:
        ws.append(row)
        index = ws.max_row
        if group_column is not None:
            value = row[group_column]
            if value != previous:
                group_index += 1
                previous = value
            fill = GROUP_FILLS[group_index % 2]
        else:
            fill = None
        for column in range(1, len(headers) + 1):
            cell = ws.cell(row=index, column=column)
            cell.font = BODY_FONT
            cell.border = BORDER
            cell.alignment = WRAP
            if fill is not None:
                cell.fill = fill
            if column in input_columns:
                cell.fill = INPUT_FILL
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(ws.max_row, 1)}"


def main() -> None:
    payload = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    mappings = payload["mappings"]
    pending = payload["pending"]
    standards = sorted({item["standard"] for item in mappings})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()

    # ---------------- Sheet 1 待业务确认 ----------------
    sheet1 = workbook.active
    sheet1.title = "待业务确认"
    pending_rows = []
    for item in pending:
        sources = item.get("sources") or []
        total = sum(int(entry.get("count") or 0) for entry in sources)
        source_text = "；".join(f"{entry['source']}（{entry['count']}）" for entry in sources)
        primary = sources[0]["source"] if sources else ""
        candidate = item.get("candidate")
        score = item.get("score") or 0
        suggestion = suggest_standard(item["raw"], candidate, score)
        extra = [name for name, _ in candidates_for(item["raw"], standards)]
        pool = []
        if candidate:
            pool.append(f"{candidate}（相似度 {score}）")
        for name in extra:
            if candidate and name == candidate:
                continue
            pool.append(name)
        pending_rows.append(
            [
                item["raw"],
                source_text,
                total,
                suggestion,
                "；".join(pool[:4]) or "无相近车系",
                item.get("reason", ""),
                "",
                "",
                primary,
            ]
        )
    pending_rows.sort(key=lambda row: (row[8], -row[2], row[0]))
    headers1 = [
        "原始写法",
        "出现来源（数据源，括号内为条数）",
        "出现次数/条数",
        "建议标准名（若有）",
        "候选标准名（多个用分号分隔）",
        "系统判断不了的原因",
        "业务确认标准名（留空待填）",
        "备注（留空待填）",
        "来源分组（排序用）",
    ]
    write_sheet(
        sheet1,
        headers1,
        pending_rows,
        [26, 62, 12, 24, 42, 40, 24, 30, 26],
        input_columns=(7, 8),
    )
    sheet1.column_dimensions["I"].hidden = True

    # ---------------- Sheet 2 已自动归一 ----------------
    sheet2 = workbook.create_sheet("已自动归一")
    merged: dict[str, dict] = {}
    for item in mappings:
        record = merged.setdefault(
            item["raw"],
            {
                "standard": item["standard"],
                "method": item["method"],
                "sources": defaultdict(int),
            },
        )
        record["sources"][item["source"]] += int(item.get("count") or 0)
    rows2 = []
    for raw, record in merged.items():
        rows2.append(
            [
                raw,
                record["standard"],
                record["method"],
                "；".join(f"{source}（{count}）" for source, count in sorted(record["sources"].items())),
                sum(record["sources"].values()),
                "",
            ]
        )
    rows2.sort(key=lambda row: (row[1], row[0]))
    headers2 = [
        "原始写法",
        "标准名（汽车之家车系名）",
        "匹配方式",
        "来源（括号内为条数）",
        "出现次数/条数",
        "业务确认标准名（留空；认为归错了就填）",
    ]
    write_sheet(sheet2, headers2, rows2, [26, 26, 14, 66, 12, 30], input_columns=(6,), group_column=1)

    # ---------------- Sheet 3 定量车型待补 ----------------
    sheet3 = workbook.create_sheet("定量车型待补")
    rows3 = []
    for item in pending:
        sources = item.get("sources") or []
        purchase = next((entry for entry in sources if entry["source"] == "quant_sample.purchase_model"), None)
        if not purchase:
            continue
        others = [entry for entry in sources if entry["source"] != "quant_sample.purchase_model"]
        candidate = item.get("candidate")
        score = item.get("score") or 0
        rows3.append(
            [
                item["raw"],
                int(purchase.get("count") or 0),
                "是：" + "；".join(f"{entry['source']}（{entry['count']}）" for entry in others) if others else "否",
                f"{candidate}（相似度 {score}）" if candidate else "无",
                "",
            ]
        )
    rows3.sort(key=lambda row: (-row[1], row[0]))
    headers3 = ["车型名（purchase_model 原写法）", "定量样本人数", "是否已在其他源出现", "可用写法（若有）", "业务补标准名（留空待填）"]
    write_sheet(sheet3, headers3, rows3, [26, 14, 58, 30, 28], input_columns=(5,))

    target = OUT_DIR / f"车系名称映射表_{date.today():%Y%m%d}.xlsx"
    workbook.save(target)

    readme = f"""# 车系名称映射表（业务核对用）

- 文件：`{target.name}`
- 生成：{date.today():%Y-%m-%d}，来源 `competitor_insight/config/vehicle_name_map.json`
  （生成器 `scripts/export_vehicle_name_map_xlsx.py`，底层映射由 `scripts/build_vehicle_name_map.py` 产生）
- 标准名口径：**汽车之家车系名**（`public.autohome_series.series_name`）。

## 三张表怎么填

| Sheet | 行数 | 含义 | 需要你做什么 |
|---|---|---|---|
| 1 待业务确认 | {len(pending_rows)} | 系统无法可靠判断的写法（未归一会让页面把同一款车拆成多行） | 在「业务确认标准名」填汽车之家车系名；确实不同款就在「备注」写"不同款" |
| 2 已自动归一 | {len(rows2)} | 系统已归一的结果，按标准名分底色组 | 只有**认为归错了**才在「业务确认标准名」填正确名；同意则留空 |
| 3 定量车型待补 | {len(rows3)} | `purchase_model` 里在汽车之家查不到车系的写法 | 补标准名；若汽车之家确实没有，请写一个业务约定名并在备注说明 |

排序：Sheet 1 按数据源分组、组内条数从高到低；Sheet 3 按人数从高到低。表头已冻结并加筛选。

## 填写约定

1. 只填浅黄色两列，**不要改动其他列、不要改表头、不要插删行**。
2. 留空 = 同意系统结果或暂时无法判断。
3. 一个原始写法只填一个标准名；同一款车的多种写法请填同一个标准名。
4. 不确定但需要保留的写法，在备注写"待补录"，不要强行合并。

## 填完怎么回收

把改好的 xlsx 放回本目录（同名覆盖或加 `_已确认` 后缀均可），或直接发回给我。我按
「业务确认标准名」更新 `competitor_insight/config/analysis_models.json` 的
`competitor_aliases` 与映射库，再重跑 `scripts/build_vehicle_name_map.py` 复核，
并把仍有分歧的项回给你。
"""
    (OUT_DIR / "README.md").write_text(readme.strip() + "\n", encoding="utf-8")
    print(target)
    print(OUT_DIR / "README.md")
    print("sheet1", len(pending_rows), "sheet2", len(rows2), "sheet3", len(rows3))


if __name__ == "__main__":
    main()
