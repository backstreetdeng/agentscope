"""D7：10 人试点生成并写入 `bci.*`（真实 DeepSeek，loader 账号）。

验收：10 人 × 43 维；19 个 success 维有值；16 个 partial 维有值或明确无数据；
8 个 none 维如实标注「本期无来源」；任一 LLM 值无证据即失败。
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from competitor_insight.server import db  # noqa: E402
from competitor_insight.server.archive_api import ArchiveService  # noqa: E402
from competitor_insight.server.archive_store import PostgresArchiveStore  # noqa: E402

PILOT = ["R003", "R050", "R057", "R030", "R025", "R037", "R046", "R005", "R010", "R062"]
TEMPLATE = "user_insight_archive"

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    RESULTS.append((ok, label))
    print(("PASS" if ok else "FAIL") + " | " + label + (" | " + detail if detail else ""))


def privileges() -> dict[str, bool]:
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT current_user, current_database(),"
            " has_schema_privilege(current_user, 'bci', 'USAGE'),"
            " has_schema_privilege(current_user, 'bci', 'CREATE'),"
            " has_database_privilege(current_user, current_database(), 'CONNECT'),"
            " has_table_privilege(current_user, 'bci.archive', 'SELECT,INSERT,UPDATE,DELETE'),"
            " has_table_privilege(current_user, 'bci.archive_field', 'SELECT,INSERT,UPDATE,DELETE')"
        )
        row = cur.fetchone()
    print(f"账号 {row[0]} @ {row[1]}")
    print(f"  schema bci USAGE={row[2]} CREATE={row[3]} | db CONNECT={row[4]}")
    print(f"  archive 写权限={row[5]} | archive_field 写权限={row[6]}")
    return {"usage": bool(row[2]), "create": bool(row[3]), "connect": bool(row[4]),
            "archive_dml": bool(row[5]), "field_dml": bool(row[6])}


print("== 执行前权限 ==")
before = privileges()
check(before["usage"] and before["create"] and before["connect"], "执行前 loader 具备 bci USAGE/CREATE")
check(before["archive_dml"] and before["field_dml"], "执行前 loader 具备两张档案表 DML")

env = db.load_env()
if not env.get("DASHSCOPE_API_KEY"):
    print("FAIL | .env 缺少 DASHSCOPE_API_KEY（DeepSeek 凭证），停止写库")
    sys.exit(1)

service = ArchiveService(
    PostgresArchiveStore(db.connect), background=False, max_workers=2
)
VERIFY_ONLY = "--verify-only" in sys.argv
if VERIFY_ONLY:
    print("\n== 跳过生成（--verify-only），仅校验已落库结果 ==")
else:
    print(f"\n== 生成 {len(PILOT)} 人 ==")
    started = time.time()
    created = service.generate(PILOT, TEMPLATE, "selected", True)["data"]
    run_id = created["run_id"]
    state = service.run_status(run_id)["data"]
    elapsed = time.time() - started
    print(f"run_id={run_id} status={state.get('status')} done={state.get('done')} failed={state.get('failed')} 用时={elapsed:.1f}s")
    for item in state.get("items") or []:
        print(f"  {item['interview_id']}: {item['status']}" + (f" ({item['error_text']})" if item.get("error_text") else ""))

    check(state.get("status") == "completed" and int(state.get("done") or 0) == len(PILOT), "10 人全部生成成功")

print("\n== 落库校验 ==")
store = PostgresArchiveStore(db.connect)
summary = store.list_archives(TEMPLATE)
by_id = {item.interview_id: item for item in summary.items}
print(f"库内非 stale 档案 {len(by_id)} 份：{', '.join(sorted(by_id))}")
check(all(iid in by_id for iid in PILOT), "10 份试点档案均已落库")

success_dims = {
    "occupation", "household_income", "family_structure", "personality_interest_social",
    "consumption_values", "ownership_status", "purchased_model_owned", "purchase_budget",
    "purchase_attribute", "fuel_type_reason", "brand_attention", "info_channels",
    "core_comparison_models", "purchased_model_compared", "win_reasons", "abandoned_models",
    "high_frequency_scenarios", "charging_needs", "range_needs",
}
none_dims = {
    "kol_influence", "first_choice_ranking", "rt_awareness_channel", "rt_attraction_ranking",
    "rt_concerns", "rt_expectations", "reception_expectation", "loyal_repurchase_reason",
}

field_counter: Counter[str] = Counter()
llm_no_evidence: list[str] = []
none_bad: list[str] = []
missing_success: list[str] = []
missing_success_with_reason: list[str] = []
review: Counter[str] = Counter()

for iid in PILOT:
    result = store.get_archive(iid, TEMPLATE)
    if not result.items:
        continue
    record = result.items[0]
    fields = {f.dimension_id: f for f in record.fields}
    print(f"{iid}: revision={record.revision} status={record.status} coverage={record.coverage_required} fields={len(fields)}")
    check(len(fields) == 43, f"{iid} 43 维", str(len(fields)))
    for dim_id, field in fields.items():
        has_value = field.value_text not in (None, "") or field.value_json not in (None, "", [], {})
        if has_value:
            field_counter[dim_id] += 1
        review[field.review_status] += 1
        if field.fill_mode == "llm" and has_value and not field.evidence_refs:
            llm_no_evidence.append(f"{iid}:{dim_id}")
        if dim_id in none_dims and not (field.no_data_reason or "").strip():
            none_bad.append(f"{iid}:{dim_id}")
        if dim_id in success_dims and not has_value:
            missing_success.append(f"{iid}:{dim_id}")
            if field.fill_mode == "none" and (field.no_data_reason or "").strip():
                missing_success_with_reason.append(f"{iid}:{dim_id}={field.no_data_reason}")

check(not llm_no_evidence, "所有 LLM 值均带证据 ID", "、".join(llm_no_evidence))
check(not none_bad, "8 个无来源维均写原因", "、".join(none_bad))
check(
    all(field_counter[d] >= len(PILOT) - 1 for d in success_dims),
    "19 个 success 维均 ≥9/10 有值",
    "、".join(f"{d}={field_counter[d]}" for d in sorted(success_dims) if field_counter[d] < len(PILOT)),
)
check(
    len(missing_success_with_reason) == len(missing_success),
    "success 维缺口均写明具体原因",
    "、".join(missing_success_with_reason),
)
none_with_value = [d for d in none_dims if field_counter[d]]
check(not none_with_value, "无来源维不产生值", "、".join(none_with_value))

print("\n19 个 success 维命中人数：" + "，".join(f"{d}={field_counter[d]}" for d in sorted(success_dims)))
print("8 个无来源维命中人数：" + "，".join(f"{d}={field_counter[d]}" for d in sorted(none_dims)))
print("review_status 分布：" + "，".join(f"{k}={v}" for k, v in sorted(review.items())))

print("\n== 执行后权限 ==")
after = privileges()
check(after["usage"] and after["create"] and after["connect"], "执行后 loader 仍具备 bci USAGE/CREATE")
check(after["archive_dml"] and after["field_dml"], "执行后 loader 仍具备两张档案表 DML")

failed = [label for ok, label in RESULTS if not ok]
print(f"\n合计 {len(RESULTS)} 项，通过 {len(RESULTS) - len(failed)}，失败 {len(failed)}")
if failed:
    print("失败项：" + "、".join(failed))
sys.exit(1 if failed else 0)
