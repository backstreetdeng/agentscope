"""生成竞品洞察车系名称映射库（标准名以汽车之家车系名为准）。

输入（全部只读）：
- 定量 `user_insight.quant_sample`：`Q3_22_1__1/2/3` 三格对比车型自由文本、`purchase_model`
- 定量 `user_insight.quant_question`：Q3_24 系列只有环节单选题，无车型文本（脚本内校验并记录）
- 深访 `user_insight.interview.vehicle_model`
- 口碑 `public.autohome_koubei.carname`、`public.dongchedi_koubei.carname`
- 配置 `miit.ods_pz_base_info.model_name`
- 标准名参考：`public.autohome_series.series_name`（汽车之家车系表）与口碑 `carname`

输出：
- `competitor_insight/config/vehicle_name_map.json`：主资产，含 mappings / pending 两节
- `competitor_insight/config/vehicle_name_map.csv`：同一张表的扁平版，便于人工复核

匹配顺序：归一后精确匹配 → 品牌前缀剥离 → 高相似度模糊匹配（>=0.86）；
其余不硬并，进 pending 待业务确认。脚本只读业务库，不写数据库。
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db, name_rules  # noqa: E402

OUT_JSON = ROOT / "competitor_insight" / "config" / "vehicle_name_map.json"
OUT_CSV = ROOT / "competitor_insight" / "config" / "vehicle_name_map.csv"
# 业务回填的确认结果（scripts/merge_vehicle_name_backfill.py 生成）：优先级高于自动匹配，重跑不被覆盖。
CONFIRM_PATH = ROOT / "competitor_insight" / "config" / "vehicle_name_confirmations.json"

# 业务 2026-11-10 定稿：以下写法对应的车型不存在，映射库不再维护，重跑时直接丢弃。
EXCLUDED_RAW = {
    "吉利星耀E5",
    "吉普自由者",
    "小鹏YU7",
    "红旗SH7",
    "阿尔法T1",
    "领克001",
    "风行S7",
}

# 业务 2026-11-10 定稿：「无」是问卷里的没填占位，只出现在 Q3_22_1__1/2/3 对比车型三格，
# 按空值处理，不收集进映射库、不进待确认。
COMPARE_EMPTY_RAW = {"无"}


def load_confirmations() -> dict[str, dict]:
    if not CONFIRM_PATH.exists():
        return {}
    payload = json.loads(CONFIRM_PATH.read_text(encoding="utf-8"))
    return {str(item["raw"]): item for item in payload.get("confirmations", [])}

BRAND_TOKENS = (
    "比亚迪", "奇瑞", "吉利", "银河", "长安", "长城", "上汽", "广汽", "东风", "一汽",
    "北汽", "江淮", "五菱", "宝骏", "领克", "极氪", "蔚来", "乐道", "小鹏", "理想",
    "问界", "智界", "享界", "尊界", "小米", "特斯拉", "大众", "丰田", "本田", "日产",
    "别克", "雪佛兰", "福特", "现代", "起亚", "马自达", "标致", "雪铁龙", "奥迪",
    "宝马", "奔驰", "沃尔沃", "凯迪拉克", "雷克萨斯", "保时捷", "路虎", "捷豹",
    "林肯", "红旗", "荣威", "名爵", "传祺", "埃安", "哪吒", "零跑", "深蓝", "启源",
    "奕派", "岚图", "阿维塔", "智己", "飞凡", "极狐", "极越", "方程豹", "腾势",
    "仰望", "捷途", "星途", "哈弗", "魏牌", "坦克", "欧拉", "广汽传祺", "北京汽车",
)


def norm_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", text)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def catalog_connect():
    cfg = db.load_env()
    conn = psycopg2.connect(
        host=cfg.get("NEW_CAR_PG_HOST", ""),
        port=int(cfg.get("NEW_CAR_PG_PORT", "5432")),
        dbname=cfg.get("NEW_CAR_PG_DATABASE", ""),
        user=cfg.get("NEW_CAR_PG_USER", ""),
        password=cfg.get("NEW_CAR_PG_PASSWORD", ""),
        connect_timeout=10,
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


def collect_variants() -> dict[str, Counter]:
    """来源表 -> 原始写法计数。"""
    sources: dict[str, Counter] = {}
    conn = db.connect()
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()

    for column in ("Q3_22_1__1", "Q3_22_1__2", "Q3_22_1__3"):
        cur.execute(
            "SELECT answers_text->>%s AS value, count(*) FROM user_insight.quant_sample "
            "WHERE coalesce(trim(answers_text->>%s), '') <> '' GROUP BY 1",
            (column, column),
        )
        sources[f"quant_sample.{column}"] = Counter(
            {
                clean(value): count
                for value, count in cur.fetchall()
                if clean(value) and clean(value) not in COMPARE_EMPTY_RAW
            }
        )

    cur.execute("SELECT purchase_model, count(*) FROM user_insight.quant_sample GROUP BY 1")
    sources["quant_sample.purchase_model"] = Counter(
        {clean(value): count for value, count in cur.fetchall() if clean(value)}
    )

    cur.execute("SELECT vehicle_model, count(*) FROM user_insight.interview GROUP BY 1")
    sources["interview.vehicle_model"] = Counter(
        {clean(value): count for value, count in cur.fetchall() if clean(value)}
    )

    cur.execute(
        "SELECT question_id, question_text FROM user_insight.quant_question "
        "WHERE question_id LIKE 'Q3_24%%' ORDER BY question_id"
    )
    sources["note.Q3_24"] = Counter(
        {row[0]: row[1] or "" for row in cur.fetchall()}  # 仅用于确认无车型文本
    )

    cur.execute("SELECT model_name, count(*) FROM miit.ods_pz_base_info GROUP BY 1")
    sources["miit.ods_pz_base_info.model_name"] = Counter(
        {clean(value): count for value, count in cur.fetchall() if clean(value)}
    )
    conn.close()

    catalog = catalog_connect()
    ccur = catalog.cursor()
    ccur.execute("SELECT carname, count(*) FROM public.autohome_koubei GROUP BY 1")
    sources["autohome_koubei.carname"] = Counter(
        {clean(value): count for value, count in ccur.fetchall() if clean(value)}
    )
    ccur.execute("SELECT carname, count(*) FROM public.dongchedi_koubei GROUP BY 1")
    sources["dongchedi_koubei.carname"] = Counter(
        {clean(value): count for value, count in ccur.fetchall() if clean(value)}
    )
    catalog.close()
    return sources


def collect_standard_names() -> tuple[dict[str, str], dict[str, int]]:
    """汽车之家车系名 -> 归一键；同时返回各标准名的口碑条数用于排序。"""
    catalog = catalog_connect()
    cur = catalog.cursor()
    cur.execute("SELECT series_name FROM public.autohome_series WHERE coalesce(series_name,'') <> ''")
    names = {norm_key(row[0]): clean(row[0]) for row in cur.fetchall()}
    cur.execute("SELECT carname, count(*) FROM public.autohome_koubei GROUP BY 1")
    volume: dict[str, int] = defaultdict(int)
    for carname, count in cur.fetchall():
        name = clean(carname)
        if not name:
            continue
        names.setdefault(norm_key(name), name)
        volume[name] += int(count)
    # 车型主数据同样来自汽车之家口径，用来补齐车系表未收录的车系名。
    cur.execute("SELECT DISTINCT model FROM public.new_car_model WHERE coalesce(model,'') <> ''")
    for (model,) in cur.fetchall():
        name = clean(model)
        if name:
            names.setdefault(norm_key(name), name)
    catalog.close()
    return names, dict(volume)


ENERGY_SUFFIXES = ("ev", "phev", "dm", "dmi", "增程", "插混", "纯电", "新能源", "混动")


# 品牌写法差异
BRAND_ALIASES = {
    "方程豹": "豹",
    "埃安": "AION",
    "吉利银河": "银河",
    "启源": "长安启源",
    "哈佛": "哈弗",
    "领跑": "零跑",
    "博智": "铂智",
}


def match(raw: str, standards: dict[str, str], ordered: list[tuple[str, str]]) -> tuple[str | None, str, float]:
    """返回 (候选标准名, 匹配方式, 相似度)。方式为 fuzzy_below_threshold 时不采用候选。"""
    key = norm_key(raw)
    if key in standards:
        return standards[key], "exact", 1.0

    # 品牌前缀可叠加：一汽大众id4 → 大众id4 → id4
    stripped = key
    for _ in range(3):
        changed = False
        for brand in BRAND_TOKENS:
            bkey = norm_key(brand)
            if stripped.startswith(bkey) and len(stripped) > len(bkey):
                stripped = stripped[len(bkey):]
                changed = True
                break
        if not changed:
            break
    if stripped != key and stripped in standards:
        return standards[stripped], "brand_prefix", 0.98

    for raw_alias, canonical in sorted(BRAND_ALIASES.items(), key=lambda pair: -len(pair[0])):
        akey = norm_key(raw_alias)
        if key.startswith(akey):
            rewritten = norm_key(canonical) + key[len(akey):]
            if rewritten in standards:
                return standards[rewritten], "brand_alias", 0.99

    # 仅当「带能源后缀」不是独立车系时，才退回无后缀车系（如 汉EV → 汉）。
    for base in (stripped, key):
        for suffix in ENERGY_SUFFIXES:
            if base.endswith(suffix) and len(base) > len(suffix):
                head = base[: -len(suffix)]
                if base not in standards and head in standards:
                    return standards[head], "energy_suffix", 0.95

    best_name, best_score = None, 0.0
    for candidate_key, candidate in ordered:
        if not candidate_key:
            continue
        score = difflib.SequenceMatcher(None, key, candidate_key).ratio()
        if score > best_score:
            best_name, best_score = candidate, score
    method = "fuzzy" if best_name and best_score >= 0.84 and len(key) >= 4 else "fuzzy_below_threshold"
    return best_name, method, round(best_score, 3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只打印统计，不写文件")
    args = parser.parse_args()

    sources = collect_variants()
    excluded_hits: set[str] = set()
    for counter in sources.values():
        for raw in list(counter):
            if raw in EXCLUDED_RAW:
                excluded_hits.add(raw)
                del counter[raw]
    standards, volume = collect_standard_names()
    ordered = sorted(standards.items(), key=lambda pair: -volume.get(pair[1], 0))
    confirmations = load_confirmations()

    q3_24_text = sources.pop("note.Q3_24")
    q3_24_with_model = [
        qid for qid, text in q3_24_text.items() if re.search(r"车型", text or "")
    ]

    rows: list[dict] = []
    pending: dict[str, dict] = {}
    seen: set[tuple[str, str]] = set()
    for source, counter in sources.items():
        for raw, count in counter.items():
            key = (source, raw)
            if key in seen:
                continue
            seen.add(key)
            candidate, method, score = match(raw, standards, ordered)
            confirmed = confirmations.get(raw)
            if confirmed:
                standard = confirmed["standard"]
                extra: dict[str, str] = {"standard_source": confirmed.get("standard_source", "autohome")}
                if confirmed.get("kind") == "auto_corrected":
                    extra["previous_standard"] = confirmed.get("previous_standard") or ""
                    extra["business_note"] = confirmed.get("note") or "业务改判自动归一结果"
                else:
                    method = "business_confirm"
                    extra["business_note"] = confirmed.get("note") or ""
                rows.append(
                    {
                        "raw": raw,
                        "standard": standard,
                        "source": source,
                        "count": int(count),
                        "method": method,
                        **extra,
                    }
                )
                continue
            if candidate and method in ("exact", "brand_prefix", "brand_alias", "energy_suffix", "fuzzy"):
                rows.append(
                    {"raw": raw, "standard": candidate, "source": source, "count": int(count), "method": method}
                )
            else:
                entry = pending.setdefault(
                    raw,
                    {"raw": raw, "candidate": None, "score": 0.0, "reason": "", "sources": []},
                )
                entry["sources"].append({"source": source, "count": int(count)})
                if score > entry["score"]:
                    entry["candidate"] = candidate if score >= 0.6 else None
                    entry["score"] = score
                entry["reason"] = (
                    "疑似同款但写法差异大，需业务确认"
                    if entry["candidate"]
                    else "库内无对应之家车系记录，建议补录标准名"
                )

    # 标准名一律去动力/能源后缀，只留简称；同一原始写法仍只指向一个标准名。
    deduped: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        row["standard"] = name_rules.strip_power_suffix(row["standard"])
        deduped[(row["raw"], row["standard"], row["source"])] = row
    rows = list(deduped.values())

    total_variants = len({raw for counter in sources.values() for raw in counter})
    mapped_variants = len({row["raw"] for row in rows})
    standard_names = len({row["standard"] for row in rows})
    print(f"来源表: {len(sources)}；原始写法 {total_variants}；已归一 {mapped_variants}；"
          f"待确认 {len(pending)}；标准名 {standard_names}")
    print("已剔除不存在车型:", sorted(excluded_hits) or "无")
    for source, counter in sources.items():
        print(f"  {source}: {len(counter)} 种")
    print("Q3_24 含「车型」字样的题号:", q3_24_with_model or "无（均为环节单选）")

    by_method = Counter(row["method"] for row in rows)
    print("匹配方式:", dict(by_method))
    print("待确认样例:", [entry["raw"] for entry in list(pending.values())[:15]])

    if args.dry_run:
        return 0

    payload = {
        "_meta": {
            "purpose": "竞品洞察车系名称统一映射；标准名以汽车之家车系名（autohome_series.series_name）为准",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "generator": "scripts/build_vehicle_name_map.py",
            "standard_source": "public.autohome_series.series_name + autohome_koubei.carname",
            "method": "归一后精确匹配 → 品牌前缀剥离 → 模糊相似度>=0.86；其余不硬并；标准名去动力/能源后缀只留简称",
            "counts": {
                "variants": total_variants,
                "mapped": mapped_variants,
                "pending": len(pending),
                "standards": standard_names,
                "business_confirmed": len(confirmations),
            },
            "power_note": "动力/燃料类型不是映射属性：标准名不保留动力后缀，动力形式按问卷题项"
                          "（靶心 Q2_2、对比车型 Q3_22_2_1/2/3）在分析时实时取，映射库不设静态列",
            "confirmation_source": "competitor_insight/config/vehicle_name_confirmations.json（业务回填，优先级高于自动匹配）",
            "q3_24_note": "Q3_24 系列仅 Q3_24_2/4/6 为环节单选题，库内无车型自由文本",
        },
        "mappings": sorted(rows, key=lambda row: (row["standard"], row["source"], row["raw"])),
        "pending": sorted(pending.values(), key=lambda entry: entry["raw"]),
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["原始写法", "标准名", "来源表", "命中条数", "匹配方式", "状态", "标准名来源", "业务备注"]
        )
        for row in payload["mappings"]:
            writer.writerow([
                row["raw"], row["standard"], row["source"], row["count"], row["method"], "已归一",
                row.get("standard_source", "autohome"), row.get("business_note", ""),
            ])
        for entry in payload["pending"]:
            sources_text = "；".join(f"{item['source']}({item['count']})" for item in entry["sources"])
            total = sum(item["count"] for item in entry["sources"])
            writer.writerow([
                entry["raw"], entry["candidate"] or "", sources_text, total,
                f"相似度 {entry['score']}" if entry["candidate"] else "无候选", "待业务确认", "", "",
            ])

    print(f"已写入 {OUT_JSON.relative_to(ROOT)} 与 {OUT_CSV.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
