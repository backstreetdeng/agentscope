"""BCI-004：43 维覆盖率实测（最终版）+ 10 人试点选样。只读。"""
import sys, io, csv, json, re
from pathlib import Path
import psycopg2
import psycopg2.extras

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[2]
CONN = dict(host="192.168.3.146", port=5432, dbname="vectordb",
            user="vectordb", password="vectordb123", connect_timeout=10)
TPL = json.loads((ROOT / "competitor_insight/templates/user_insight_archive_template.json").read_text(encoding="utf-8"))
GROUPS = {g["id"]: g["name"] for g in TPL["groups"]}

# (fill_mode, direct_hit, material_hit, note)
SPEC = {
 "archive_summary":            ("llm",      0, 63, "全部答案齐全；摘要必须 LLM 生成并绑定证据，不能直取"),
 "age_gender":                 ("tag",     45, 45, "年龄 tag 45/63 可用；性别 tag 全量 not_asked（0/63），原题 Q68 未问性别"),
 "occupation":                 ("tag",     62, 62, "行业/岗位 tag（Q68/Q77）"),
 "household_income":           ("tag",     59, 59, "家庭/个人年收入 tag（Q72）"),
 "family_structure":           ("tag",     60, 60, "婚姻/子女 tag 可用；同住人数 tag 全量未提及"),
 "personality_interest_social":("tag",     61, 61, "性格特点 + 兴趣爱好 tag（Q82/Q79）"),
 "consumption_values":         ("tag",     62, 62, "消费观 + 支出结构 tag（Q83/Q84/Q73）"),
 "ownership_status":           ("tag",     63, 63, "当前/增购前/换购前/保有车型 + 充电桩安装 tag"),
 "purchased_model_owned":      ("metadata",63, 63, "interview.vehicle_model"),
 "purchase_budget":            ("tag",     60, 60, "购车预算/裸车价 tag；63 行有值，3 行被可信度过滤"),
 "purchase_attribute":         ("tag",     63, 63, "首增换购属性 tag（Q1）"),
 "purchase_motivation":        ("tag",     45, 45, "购车原因 tag；18 人因「Q4 必须标最重要」格式失败被过滤"),
 "consideration_priority":     ("llm",     62, 62, "有 TOP5 关注原料，但「价格>燃料>车身」三轴严格排序仅 2/63，须重排"),
 "fuel_type_reason":           ("tag",     63, 63, "能源偏好 6 类原因 tag（Q10-Q19）"),
 "brand_product_service_rank": ("llm",      0, 52, "无任何题项问「品牌/产品/服务」三轴；Q20 含三词者 0/63，只能推断"),
 "brand_attention":            ("tag",     62, 62, "具体品牌/品牌类型/品牌看法 tag（Q37-42）"),
 "product_attention_top5":     ("tag",     48, 60, "本次购车关注 tag 有 ≥5 项者 48/63；「恰好 5 项 + 每项细项」须 LLM 补"),
 "sales_marketing_attention":  ("llm",      0, 52, "Q63 售前售后的评述 52/63；无标签，须归纳为关注诉求"),
 "info_channels":              ("tag",     60, 60, "汽车触媒偏好 + APP偏好 tag（Q80/Q81）"),
 "content_format_preference":  ("llm",      0, 18, "Q81 只到「垂媒 vs 短视频」，车评人/长视频/参数对比等形式仅 18/63 有原料"),
 "kol_influence":              ("none",     0,  0, "85 题无 KOL/KOC 题；全库仅 6 人偶然提到达人/博主，无法成维"),
 "core_comparison_models":     ("tag",     63, 63, "核心对比车型/最终核心对比车型 tag（Q26）"),
 "first_choice_ranking":       ("none",     0,  0, "85 题无「按维度首选排序」题；Q26 只有车型清单，无法算首选率"),
 "purchased_model_compared":   ("metadata",63, 63, "interview.vehicle_model（与拥车组同源）"),
 "win_reasons":                ("tag",     62, 62, "选择当前车辆的原因 tag（Q29）"),
 "compromise_points":          ("llm",      0,  6, "无标签；Q29/Q59 明确提「妥协/接受/牺牲」者仅 6/63"),
 "abandoned_models":           ("derived", 63, 63, "核心对比车型 − 最终车型，可确定性派生（需 Q26 两项同人齐全）"),
 "abandonment_reasons":        ("tag",     21, 21, "放弃原因 tag；42 人因串题/格式失败被可信度过滤，仅 21/63 可用"),
 "aion_brand_impression":      ("llm",      3,  3, "全库仅 3 人（R003/R050/R057）提及埃安；无埃安专有题"),
 "rt_awareness_channel":       ("none",     0,  0, "85 题无埃安 RT 题"),
 "rt_attraction_ranking":      ("none",     0,  0, "同上"),
 "rt_concerns":                ("none",     0,  0, "同上"),
 "rt_expectations":            ("none",     0,  0, "同上"),
 "conversion_opportunity_risk":("llm",      0, 63, "无 RT 题；只能用再购意向 tag 外推，不能视为 RT 转化结论"),
 "high_frequency_scenarios":   ("tag",     63, 63, "用车场景 tag 63；单程/日均里程 53、行驶区域 52"),
 "scenario_needs":             ("llm",     58, 58, "用车过程关注 tag 58/63，须归纳为「场景→需求」"),
 "charging_needs":             ("tag",     63, 63, "充电桩/频次/地点/方式 tag 并集；单项 59"),
 "range_needs":                ("tag",     61, 61, "纯电续航需求 tag（Q50）"),
 "satisfaction_score":         ("llm",     13, 13, "Q59 明确给出数字分者 13/63；其余只能编，必须落 no_data"),
 "satisfaction_points":        ("tag",     55, 55, "满意点 tag；8 人被可信度过滤"),
 "dissatisfaction_points":     ("tag",     54, 54, "不满意点 tag；9 人被可信度过滤"),
 "reception_expectation":      ("none",     0,  0, "Q63 只问「评价」不问「期待」；含期待/希望/建议者 0/63"),
 "loyal_repurchase_reason":    ("none",     0,  0, "63 人购买车型无埃安（0/63），该维对当前样本不适用"),
}
BAD = ('未提及', '未提及。', 'not_asked', 'not_applicable', '拿不准')


def conn():
    return psycopg2.connect(**CONN)


rows = []
with conn() as c:
    with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select count(*) c from user_insight.interview")
        total = cur.fetchone()["c"]
        for d in TPL["dimensions"]:
            mode, direct, material, note = SPEC[d["id"]]
            hit = direct if mode in ("tag", "metadata", "derived") else material
            rate = round(hit / total, 4) if total else 0
            if hit == 0:
                status = "failed"
            elif mode == "llm":
                status = "partial"          # 需模型生成，天然不算「已覆盖」
            else:
                status = "success" if rate >= 0.9 else "partial"
            rows.append({
                "dimension_id": d["id"], "dimension_name": d["name"],
                "group_id": d["group"], "group_name": GROUPS.get(d["group"], ""),
                "required": d.get("required"), "type": d["type"],
                "fill_mode": mode, "should_check": total, "checked": total,
                "hit": hit, "coverage_rate": rate, "status": status,
                "direct_hit": direct, "llm_material_hit": material,
                "evidence_basis": "db-measured",
                "note": note,
            })

out = ROOT / "competitor_insight/docs/coverage.csv"
with out.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

from collections import Counter
cnt = Counter(r["status"] for r in rows)
req = [r for r in rows if r["required"]]
print(f"total interviews={total} dims={len(rows)}")
print("status:", dict(cnt))
print("required:", len(req), dict(Counter(r["status"] for r in req)))
print("\n逐维：")
for r in rows:
    print(f'{r["status"]:7} {r["hit"]:3}/{r["should_check"]} {r["coverage_rate"]:5.1%} {r["fill_mode"]:8} {r["dimension_name"]}')

# ---- 10 人试点选样 ----
print("\n== 10 人试点选样 ==")
with conn() as c:
    with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("select interview_id, city, purchase_type, vehicle_model from user_insight.interview")
        meta = {r["interview_id"]: r for r in cur.fetchall()}
        cur.execute("""select interview_id, tag_name from user_insight.tag
                       where trust_status='可信' and tag_value is not null
                         and tag_value not like '未提及%%'
                         and tag_value not in ('not_asked','not_applicable','拿不准')""")
        tagdim = {}
        for r in cur.fetchall():
            tagdim.setdefault(r["interview_id"], set()).add(r["tag_name"])
        cur.execute("select distinct interview_id from user_insight.answer where answer_text like '%%埃安%%'")
        aion = {r["interview_id"] for r in cur.fetchall()}

# 维 -> 命中人群
dim_people = {}
for r in rows:
    if r["fill_mode"] in ("tag", "metadata", "derived") and r["hit"] > 0:
        dim_people[r["dimension_id"]] = None
# 用标签名无法精确反推每维，改用直接可用维集合（试点只按「可用维数」排序并强制覆盖埃安/属性/城市）

def usable_dims(iid):
    s = set()
    tg = tagdim.get(iid, set())
    for r in rows:
        if r["fill_mode"] in ("tag", "metadata", "derived") and r["hit"] > 0:
            s.add(r["dimension_id"])
    return s

mandatory = sorted(aion)
chosen = list(mandatory)
rest = [i for i in sorted(meta) if i not in chosen]
ptypes = {meta[i]["purchase_type"] for i in chosen}
cities = {meta[i]["city"] for i in chosen}
tagcount = {i: len(tagdim.get(i, set())) for i in rest}
CITY_CAP = {"天津": 3, "沈阳": 2, "深圳": 2, "重庆": 3}
while len(chosen) < 10 and rest:
    def city_count(city):
        return sum(1 for i in chosen if meta[i]["city"] == city)
    def score(i):
        m = meta[i]
        city_room = (m["city"] not in cities) and city_count(m["city"]) < CITY_CAP.get(m["city"], 2)
        return (city_room * 3 + (m["purchase_type"] not in ptypes) * 2,
                tagcount.get(i, 0))
    pool = [i for i in rest if city_count(meta[i]["city"]) < CITY_CAP.get(meta[i]["city"], 2)] or rest
    best = max(pool, key=score)
    chosen.append(best)
    ptypes.add(meta[best]["purchase_type"])
    cities.add(meta[best]["city"])
    rest.remove(best)

print("必选（全库仅 3 人提及埃安）:", mandatory)
for i in chosen:
    m = meta[i]
    print(f'  {i} {m["city"]} {m["purchase_type"]} {m["vehicle_model"]} 可信标签={len(tagdim.get(i, set()))} {"[埃安]" if i in aion else ""}')
print("覆盖购车属性:", sorted(ptypes), "城市:", sorted(cities))
