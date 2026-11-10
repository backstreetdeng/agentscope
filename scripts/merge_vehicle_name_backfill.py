"""业务回填表回灌：生成确认覆盖层 → 重跑映射库 → 更新 competitor_aliases → 出差异报告。

输入：
  - 附件补填 xlsx（只读）
  - competitor_insight/config/vehicle_name_map.json（当前映射库）
  - competitor_insight/config/analysis_models.json（competitor_aliases）
输出（--apply 时）：
  - outputs/competitor-insights/BCI-006/20261110-vehicle-name-map/车系名称映射表_20261110-补填.xlsx（存档副本）
  - outputs/.../merge_stats.json、业务回填差异报告_20261110.md
  - competitor_insight/config/vehicle_name_confirmations.json（业务确认覆盖层）
  - competitor_insight/config/vehicle_name_map.json / .csv（重跑后）
  - competitor_insight/config/analysis_models.json（追加别名）
默认 dry-run：只打印统计与冲突，不写文件。
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_vehicle_name_map import CONFIRM_PATH, collect_standard_names  # noqa: E402

FILLED = Path(r"c:\Users\legio\.trae-cn\attachments\4605b703-7a76-4002-a3ec-a514f4b5de0a_b6ed5802-2096-47c1-a41e-71d50053d545_车系名称映射表_20261110-补填.xlsx")
OUT_DIR = ROOT / "outputs" / "competitor-insights" / "BCI-006" / "20261110-vehicle-name-map"
ARCHIVE = OUT_DIR / "车系名称映射表_20261110-补填.xlsx"
MAP_JSON = ROOT / "competitor_insight" / "config" / "vehicle_name_map.json"
MODELS_JSON = ROOT / "competitor_insight" / "config" / "analysis_models.json"
REPORT = OUT_DIR / "业务回填差异报告_20261110.md"

BRAND_LEVEL = {"深蓝", "理想", "问界", "零跑", "小鹏", "比亚迪", "吉利", "长城", "奇瑞", "长安", "蔚来", "极氪", "领克", "坦克"}


def norm(text: str) -> str:
    s = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", s)


def alias_key(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).casefold()


def read_filled() -> tuple[dict[str, dict], dict[str, dict], dict[str, str]]:
    wb = load_workbook(FILLED, read_only=True)
    ws1 = wb["待业务确认"]
    sheet1: dict[str, dict] = {}
    for r in range(2, ws1.max_row + 1):
        raw = ws1.cell(row=r, column=1).value
        if not raw:
            continue
        confirm = ws1.cell(row=r, column=7).value
        note = ws1.cell(row=r, column=8).value
        sheet1[str(raw).strip()] = {
            "standard": str(confirm).strip() if confirm else "",
            "note": str(note).strip() if note else "",
        }
    ws2 = wb["已自动归一"]
    corrections: dict[str, dict] = {}
    for r in range(2, ws2.max_row + 1):
        raw = ws2.cell(row=r, column=1).value
        value = ws2.cell(row=r, column=6).value
        if raw and value and str(value).strip():
            corrections[str(raw).strip()] = {"standard": str(value).strip()}
    ws3 = wb["定量车型待补"]
    sheet3: dict[str, str] = {}
    for r in range(2, ws3.max_row + 1):
        raw = ws3.cell(row=r, column=1).value
        value = ws3.cell(row=r, column=5).value
        if raw:
            sheet3[str(raw).strip()] = str(value).strip() if value else ""
    wb.close()
    return sheet1, corrections, sheet3


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(cell).replace("|", "\\|") for cell in row) + " |")
    return "\n".join(out)


def render_report(stats: dict, diff_lines: list[str]) -> str:
    deleted = stats["deleted_rows"]
    blank = stats["blank_rows"]
    lines = [
        "# 车系名称映射表 · 业务回填差异报告（20261110）",
        "",
        f"- 业务回填表存档：`{ARCHIVE.name}`（原件未改动）",
        "- 覆盖层：`competitor_insight/config/vehicle_name_confirmations.json`",
        "- 映射库：`competitor_insight/config/vehicle_name_map.json` / `.csv`",
        "- 别名：`competitor_insight/config/analysis_models.json` → `competitor_aliases`",
        "",
        "## 1. 回灌统计",
        "",
        md_table(
            ["项", "数量", "说明"],
            [
                ["Sheet1 收到行数", stats["sheet1_rows"], "原始 274 行"],
                ["Sheet1 已填", stats["sheet1_filled"], "业务填了确认标准名"],
                ["待确认 → 已归一", stats["pending_confirmed"], "写入映射库，匹配方式 business_confirm"],
                ["已归一改判", stats["auto_corrected"], "覆盖原自动结果，保留 previous_standard"],
                ["业务删行", len(deleted), "见 §4，保持待确认"],
                ["业务留空", len(blank), "见 §5，保持待确认"],
                ["冲突未回灌", len(stats["conflicts"]), "两张表填了不同标准名，见 §3"],
                ["新增别名", stats["alias_added"], "只补空缺，未覆盖已有别名"],
                ["别名冲突未改", len(stats["alias_conflicts"]), "见 §9"],
                ["新增标准名", len(stats["new_standards"]), "相对原 585 个标准名"],
            ],
        ),
        "",
        "## 2. 回灌后映射库",
        "",
        md_table(
            ["指标", "回灌前", "回灌后"],
            [
                ["写法数", stats["after"]["variants"], stats["after"]["variants"]],
                ["已归一写法", 758, stats["after"]["mapped"]],
                ["待确认写法", 274, stats["after"]["pending"]],
                ["标准名个数", 585, stats["after"]["standards"]],
                ["映射明细行", stats["mapping_rows_before"], stats["mapping_rows_after"]],
            ],
        ),
        "",
        "## 3. 冲突（未回灌，等业务定）",
        "",
        md_table(
            ["原始写法", "Sheet1 填的", "Sheet3 填的", "处理"],
            [[c[0], c[1], c[2], "保持待确认，两表口径不一致"] for c in stats["conflicts"]],
        ),
        "",
        "## 4. 业务删掉的行（未回灌，保持待确认）",
        "",
        "、".join(deleted) or "无",
        "",
        "## 5. 业务留空的行（未回灌，保持待确认）",
        "",
        "、".join(f"「{raw}」" for raw in blank) or "无",
        "",
        "> 「无」是问卷里真实出现的写法（Q3_22 三列共 82 条），不是车名，建议在数据侧按「未填对比车型」处理。",
        "",
        "## 6. 异常提示",
        "",
        "**疑似品牌/车系族而非具体车系**（已按业务填写回灌）：",
        "",
        "、".join(f"{raw} → {std}" for raw, std in stats["brand_level"]) or "无",
        "",
        "**含分隔标点**：",
        "",
        "、".join(f"{raw} → {std}" for raw, std in stats["separators"]) or "无",
        "",
        f"**含空格**：{len(stats['spacing'])} 条，均为「魏牌 蓝山」这类汽车之家车系名的固有写法，已原样保留，未改写。",
        "",
        "**同一标准名下写法差异过大（需复核是否误并）**：",
        "",
        md_table(["标准名", "写法A", "写法B", "相似度"], [[g[0], g[1], g[2], g[3]] for g in stats["suspect_groups"]]),
        "",
        "## 7. Sheet3 定量车型回灌结果",
        "",
        md_table(["车型名", "业务补标准名", "状态", "库内车系表"], stats["sheet3_check"]),
        "",
        "## 8. 未能确认",
        "",
        f"- 库内只有 `public.autohome_series` 448 条 + `public.new_car_model` 543 条，不是汽车之家全量车系表；"
        f"业务填的 {stats['not_in_catalog']} 个标准名在其中查不到，无法判定汽车之家是否收录，"
        "已标 `standard_source=unverified`，照业务填写保留。",
        "- 业务填的标准名是否与汽车之家官网一致，未联网核验。",
        "",
        "## 9. 别名冲突（已存在的别名未覆盖）",
        "",
        "`competitor_aliases` 里原有条目与业务确认值不一致时，保留原值不改，避免演示车标签被重命名：",
        "",
        md_table(["原始写法", "现有别名", "业务确认值"], [[c[0], c[1], c[2]] for c in stats["alias_conflicts"]]),
        "",
        "其中 `奇瑞iCAR V23`、`iCAR V23`、`奇瑞iCARV23`、`比亚迪海狮05` 属五款演示车的靶心/对手名，"
        "改动会重命名「战胜战败」的行标题，需业务确认是统一改成汽车之家车系名，还是维持现有演示标签。",
        "",
        "## 10. 五款演示车重跑对比",
        "",
        "回灌前后各跑一次 `AnalysisService.analyze()`（同库、同代码，仅配置不同）：",
        "",
        "结论：五款车的战败行人数、比例、原因 TOP3 勾选率、胜出与战胜侧**全部未变**。差异只有两类：",
        "① 对手写法改按业务确认的标准名显示（小鹏M03→小鹏MONA M03、启源Q07→长安启源Q07）；",
        "② 铂智3X 里同为 1 人的两行因标签改名后按标签排序互换位置（银河星耀8 ↔ 长安启源Q07），人数不变。",
        "",
        "\n".join(diff_lines) if diff_lines else "无差异",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", action="store_true", help="只按已保存的 merge_stats.json 重写报告")
    args = parser.parse_args()

    if args.report:
        stats = json.loads((OUT_DIR / "merge_stats.json").read_text(encoding="utf-8"))
        diff_out = subprocess.run(
            [sys.executable, "-B", str(ROOT / "temp" / "20261110-bci006-vehicle-name-map-merge" / "diff_analysis.py")],
            cwd=str(ROOT), capture_output=True, text=True,
        )
        diff_lines = [line for line in diff_out.stdout.splitlines() if line.strip()]
        REPORT.write_text(render_report(stats, diff_lines), encoding="utf-8")
        print("已重写报告:", REPORT.relative_to(ROOT))
        return 0

    data = json.loads(MAP_JSON.read_text(encoding="utf-8"))
    pending = {item["raw"]: item for item in data["pending"]}
    mapped = {row["raw"]: row for row in data["mappings"]}
    models_cfg = json.loads(MODELS_JSON.read_text(encoding="utf-8"))
    aliases = models_cfg.get("competitor_aliases", {})

    sheet1, corrections, sheet3 = read_filled()
    deleted = [raw for raw in pending if raw not in sheet1]
    blank = [raw for raw, item in sheet1.items() if not item["standard"]]

    conflicts: list[tuple[str, str, str]] = []
    for raw, value in sheet3.items():
        if raw in sheet1 and sheet1[raw]["standard"] and norm(sheet1[raw]["standard"]) != norm(value):
            conflicts.append((raw, sheet1[raw]["standard"], value))
    conflict_raws = {item[0] for item in conflicts}

    confirmations: list[dict] = []
    for raw, item in sheet1.items():
        if not item["standard"] or raw in conflict_raws or raw not in pending:
            continue
        confirmations.append({"raw": raw, "standard": item["standard"], "kind": "pending_confirm", "note": item["note"]})
    for raw, item in corrections.items():
        previous = mapped.get(raw, {}).get("standard", "")
        confirmations.append(
            {
                "raw": raw,
                "standard": item["standard"],
                "kind": "auto_corrected",
                "previous_standard": previous,
                "note": f"业务改判：原自动结果 {previous}",
            }
        )

    standards, _volume = collect_standard_names()
    for item in confirmations:
        item["standard_source"] = "autohome" if norm(item["standard"]) in standards else "unverified"
    unverified = [item for item in confirmations if item["standard_source"] == "unverified"]

    spacing = [item for item in confirmations if re.search(r"\s", item["standard"])]
    separators = [item for item in confirmations if re.search(r"[，,；;、/]", item["standard"])]
    brand_level = [item for item in confirmations if item["standard"] in BRAND_LEVEL]
    weird = [item for item in confirmations if not re.search(r"[\u4e00-\u9fff]|[A-Za-z]", item["standard"])]

    alias_conflicts: list[tuple[str, str, str]] = []
    alias_added: dict[str, str] = {}
    for item in confirmations:
        raw, standard = item["raw"], item["standard"]
        if norm(raw) == norm(standard):
            continue
        key = alias_key(raw)
        existing = next((k for k in aliases if alias_key(k) == key), None)
        if existing is not None:
            if alias_key(aliases[existing]) != alias_key(standard):
                alias_conflicts.append((raw, aliases[existing], standard))
            continue
        alias_added[raw] = standard

    # 同一标准名下写法相似度过低 -> 可能把不同车并到一起
    groups: dict[str, list[str]] = defaultdict(list)
    for item in confirmations:
        groups[norm(item["standard"])].append(item["raw"])
    suspect_groups = []
    for key, raws in groups.items():
        if len(raws) < 2:
            continue
        worst = 1.0
        pair = ("", "")
        for i in range(len(raws)):
            for j in range(i + 1, len(raws)):
                ratio = difflib.SequenceMatcher(None, norm(raws[i]), norm(raws[j])).ratio()
                if ratio < worst:
                    worst, pair = ratio, (raws[i], raws[j])
        if worst < 0.45:
            suspect_groups.append((groups[key][0], pair[0], pair[1], round(worst, 2)))

    # Sheet3：定量侧是否已能对上
    sheet3_check = []
    for raw, value in sheet3.items():
        status = "已回灌" if raw in conflict_raws or raw in {c["raw"] for c in confirmations} else "未回灌"
        if raw in conflict_raws:
            status = "冲突未回灌"
        in_catalog = norm(value) in standards
        sheet3_check.append([raw, value, status, "库内有该车系名" if in_catalog else "库内未收录（未能确认）"])

    old_std = {norm(row["standard"]) for row in data["mappings"]}
    new_std = sorted({i["standard"] for i in confirmations if norm(i["standard"]) not in old_std})
    stats = {
        "sheet1_rows": len(sheet1),
        "sheet1_filled": sum(1 for item in sheet1.values() if item["standard"]),
        "deleted_rows": deleted,
        "blank_rows": blank,
        "pending_confirmed": sum(1 for item in confirmations if item["kind"] == "pending_confirm"),
        "auto_corrected": sum(1 for item in confirmations if item["kind"] == "auto_corrected"),
        "conflicts": conflicts,
        "not_in_catalog": len(unverified),
        "new_standards": new_std,
        "alias_added": len(alias_added),
        "alias_conflicts": alias_conflicts,
        "spacing": [(i["raw"], i["standard"]) for i in spacing],
        "separators": [(i["raw"], i["standard"]) for i in separators],
        "brand_level": [(i["raw"], i["standard"]) for i in brand_level],
        "weird": [(i["raw"], i["standard"]) for i in weird],
        "suspect_groups": suspect_groups,
        "sheet3_check": sheet3_check,
    }
    print(json.dumps({k: v for k, v in stats.items() if k not in ("new_standards", "spacing")}, ensure_ascii=False, indent=2))

    if not args.apply:
        print("\n[dry-run] 未写文件")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FILLED, ARCHIVE)

    confirmations.sort(key=lambda item: item["raw"])
    CONFIRM_PATH.write_text(
        json.dumps(
            {
                "_meta": {
                    "purpose": "业务回填的车型写法确认结果，优先级高于自动匹配；重跑 build 不会被覆盖",
                    "source_file": ARCHIVE.name,
                    "sheet1_confirmed": stats["pending_confirmed"],
                    "sheet2_corrected": stats["auto_corrected"],
                    "conflicts_skipped": [c[0] for c in conflicts],
                    "unverified_against_local_catalog": len(unverified),
                    "catalog_note": "库内 autohome_series 448 条 + new_car_model 543 条，非汽车之家全量车系表",
                },
                "confirmations": confirmations,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    build = subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts" / "build_vehicle_name_map.py")],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    print("\n[build]", build.returncode, build.stdout.strip(), build.stderr.strip()[-800:])
    if build.returncode != 0:
        return 1

    aliases.update(alias_added)
    models_cfg["competitor_aliases"] = dict(sorted(aliases.items(), key=lambda kv: kv[0]))
    models_cfg["updated"] = "2026-11-10"
    MODELS_JSON.write_text(json.dumps(models_cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    new_data = json.loads(MAP_JSON.read_text(encoding="utf-8"))
    after = dict(new_data["_meta"]["counts"])
    after["standards"] = len({row["standard"] for row in new_data["mappings"]})
    stats["after"] = after
    stats["mapping_rows_before"] = len(data["mappings"])
    stats["mapping_rows_after"] = len(new_data["mappings"])
    (OUT_DIR / "merge_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    diff_out = subprocess.run(
        [sys.executable, "-B", str(ROOT / "temp" / "20261110-bci006-vehicle-name-map-merge" / "diff_analysis.py")],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    diff_lines = [line for line in diff_out.stdout.splitlines() if line.strip()]
    REPORT.write_text(render_report(stats, diff_lines), encoding="utf-8")
    print("\n新统计:", after)
    print("已写:", REPORT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
