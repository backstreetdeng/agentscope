"""汽车咨询行业报告数据质量门禁。

质量门禁不是一个独立菜单，而是报告生成链路中的审计层：
1. 智能体先回答业务问题。
2. 质量门禁读取问题、报告、工具审计结果。
3. 给出通过/待核验/风险/阻断状态。
4. 前端据此提示补证据、限制或提醒生成 PPT。
"""

from __future__ import annotations

import re
from typing import Any


QUALITY_RULES: list[dict[str, str]] = [
    {
        "id": "source_authority",
        "name": "数据来源权威性",
        "description": "关键数据应来自官方、行业机构、授权数据库或明确可追溯网页。",
    },
    {
        "id": "freshness",
        "name": "数据时效性",
        "description": "销量、政策、价格、竞品动态必须说明统计周期或发布时间。",
    },
    {
        "id": "metric_consistency",
        "name": "数据口径一致性",
        "description": "批发、零售、上险、交付、订单、指导价、成交价等口径不得混用。",
    },
    {
        "id": "scope_alignment",
        "name": "分析边界一致性",
        "description": "区域、价格带、能源类型、车型级别应与用户问题保持一致。",
    },
    {
        "id": "completeness",
        "name": "关键维度完整性",
        "description": "市场机会、风险、区域、竞品/用户、进入建议、证据缺口应覆盖。",
    },
    {
        "id": "cross_validation",
        "name": "交叉验证充分性",
        "description": "关键结论需要多来源证据，或明确标注为假设/待补充数据。",
    },
    {
        "id": "anomaly_conflict",
        "name": "异常与冲突识别",
        "description": "同比、环比、份额、排名、政策变化等异常必须有解释或待核验标记。",
    },
    {
        "id": "traceability",
        "name": "结论可追溯性",
        "description": "进入/暂缓/产能调配等建议必须能回溯到证据、假设或数据缺口。",
    },
]


AUTHORITY_TERMS = [
    "中汽协",
    "中国汽车工业协会",
    "乘联会",
    "乘联分会",
    "工信部",
    "商务部",
    "财政部",
    "公安部",
    "交强险",
    "上险量",
    "MarkLines",
    "盖世汽车",
    "懂车帝",
    "汽车之家",
    "麦肯锡",
    "杰兰路",
    "CCRT",
    "http://",
    "https://",
]


def evaluate_report_quality(report: str, question: str = "", tool_events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """按汽车咨询报告要求执行 8 项质量门禁。"""

    text = normalize(report)
    q = normalize(question)
    tool_events = tool_events or []
    checks = [
        check_source_authority(text, tool_events),
        check_freshness(text),
        check_metric_consistency(text),
        check_scope_alignment(text, q),
        check_completeness(text),
        check_cross_validation(text),
        check_anomaly_conflict(text),
        check_traceability(text),
    ]

    score = round(sum(item["score"] for item in checks) / len(checks))
    blocked = [item for item in checks if item["status"] == "阻断"]
    risks = [item for item in checks if item["status"] == "风险"]
    pending = [item for item in checks if item["status"] == "待核验"]

    if blocked:
        overall = "阻断"
        impact = "不建议直接用于正式汇报或生成PPT；应先补充关键来源、口径或证据链。"
    elif risks:
        overall = "风险"
        impact = "可以作为草稿讨论，但生成PPT前应补充风险说明和待核验数据。"
    elif pending:
        overall = "待核验"
        impact = "可以继续问答和生成草稿报告，但应在报告中显式保留待补充数据。"
    else:
        overall = "通过"
        impact = "可进入报告沉淀和PPT生成环节。"

    return {
        "overall_status": overall,
        "score": score,
        "pass_count": sum(1 for item in checks if item["status"] == "通过"),
        "warning_count": len(pending) + len(risks),
        "block_count": len(blocked),
        "checks": checks,
        "impact": impact,
        "suggested_actions": build_suggested_actions(checks),
    }


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def make_check(rule_id: str, status: str, score: int, evidence: str, suggestion: str) -> dict[str, Any]:
    rule = next(item for item in QUALITY_RULES if item["id"] == rule_id)
    return {
        "id": rule_id,
        "name": rule["name"],
        "description": rule["description"],
        "status": status,
        "score": score,
        "evidence": evidence,
        "suggestion": suggestion,
    }


def check_source_authority(text: str, tool_events: list[dict[str, Any]]) -> dict[str, Any]:
    hits = [term for term in AUTHORITY_TERMS if term.lower() in text.lower()]
    tool_count = len([event for event in tool_events if event.get("status") == "success"])
    if len(hits) >= 3 or tool_count >= 2:
        return make_check("source_authority", "通过", 92, f"识别到权威/可追溯来源 {len(hits)} 个，真实工具成功调用 {tool_count} 次。", "保留来源名称、链接和发布时间。")
    if hits or tool_count:
        return make_check("source_authority", "待核验", 68, f"仅识别到有限来源 {hits[:3]}，工具成功调用 {tool_count} 次。", "关键销量、政策、竞品数据建议补充原始链接或机构出处。")
    return make_check("source_authority", "风险", 35, "未识别到明确权威来源或真实工具审计。", "不应把无来源数据写成确定事实，应标注为示范假设。")


def check_freshness(text: str) -> dict[str, Any]:
    years = re.findall(r"20[2-3]\d", text)
    has_period = bool(re.search(r"(Q[1-4]|[1-9]月|1-?4月|上半年|下半年|统计周期|分析时点|发布时间|截至)", text))
    if years and has_period:
        return make_check("freshness", "通过", 90, f"包含年份 {sorted(set(years))[:4]} 且有统计周期/分析时点。", "继续保持每个关键数据的时间口径。")
    if years:
        return make_check("freshness", "待核验", 65, f"包含年份 {sorted(set(years))[:4]}，但统计周期不充分。", "补充数据发布日期、统计区间和政策执行窗口。")
    return make_check("freshness", "风险", 30, "未识别到数据年份或统计周期。", "市场报告必须标注分析时点和数据时间范围。")


def check_metric_consistency(text: str) -> dict[str, Any]:
    metrics = [term for term in ["批发", "零售", "上险", "交付", "订单", "指导价", "成交价", "终端价", "渗透率"] if term in text]
    has_scope_note = any(term in text for term in ["口径", "数据说明", "不可直接比较", "同口径", "统计口径"])
    if len(metrics) <= 1 or has_scope_note:
        return make_check("metric_consistency", "通过", 88, f"涉及口径：{metrics or ['未明显混用']}。", "涉及不同口径时继续保留说明。")
    return make_check("metric_consistency", "待核验", 58, f"同时出现多个数据口径：{metrics}，但缺少口径说明。", "补充批发/零售/上险/交付/价格口径说明，避免直接相加比较。")


def check_scope_alignment(text: str, question: str) -> dict[str, Any]:
    required = []
    for token in ["15-20", "新能源", "SUV", "乘用车"]:
        if token.lower() in question.lower():
            required.append(token)
    hits = [token for token in required if token.lower() in text.lower()]
    if not required or len(hits) == len(required):
        return make_check("scope_alignment", "通过", 90, f"问题边界关键词覆盖：{hits or ['未设定强边界']}。", "保持价格带、车型、区域和能源类型贯穿全篇。")
    missing = sorted(set(required) - set(hits))
    return make_check("scope_alignment", "风险", 45, f"报告缺少问题边界关键词：{missing}。", "修订报告，确保不混入其他价格带、车型级别或能源类型。")


def check_completeness(text: str) -> dict[str, Any]:
    dimensions = {
        "机会": ["机会", "增量", "潜力"],
        "风险": ["风险", "衰退", "预警"],
        "区域": ["区域", "华东", "华南", "西南", "产能"],
        "建议": ["进入", "暂缓", "建议", "决策"],
        "证据": ["证据", "来源", "依据"],
        "缺口": ["待补充", "假设", "待核验"],
    }
    passed = [name for name, terms in dimensions.items() if any(term in text for term in terms)]
    if len(passed) >= 5:
        return make_check("completeness", "通过", 90, f"覆盖关键维度：{passed}。", "正式报告建议保留证据和待补充数据章节。")
    if len(passed) >= 3:
        return make_check("completeness", "待核验", 62, f"仅覆盖部分维度：{passed}。", "补齐机会、风险、区域、建议、证据、缺口中的缺失项。")
    return make_check("completeness", "阻断", 20, f"关键维度覆盖不足：{passed}。", "报告结构不足以支撑咨询结论，需重新生成或补写。")


def check_cross_validation(text: str) -> dict[str, Any]:
    source_count = len(set(term for term in AUTHORITY_TERMS if term.lower() in text.lower()))
    has_assumption = any(term in text for term in ["假设", "待补充", "待核验", "数据缺口"])
    evidence_lines = len(re.findall(r"(证据|来源|依据|数据显示|报告|政策)", text))
    if source_count >= 3 and evidence_lines >= 5:
        return make_check("cross_validation", "通过", 90, f"来源数 {source_count}，证据表达 {evidence_lines} 处。", "关键结论继续保持多来源支撑。")
    if source_count >= 1 or has_assumption:
        return make_check("cross_validation", "待核验", 60, f"来源数 {source_count}，假设/缺口标记={has_assumption}。", "关键市场进入/暂缓结论建议至少补充两类证据。")
    return make_check("cross_validation", "风险", 35, "未形成交叉验证或假设标记。", "增加来源表，或把缺证据判断降级为假设。")


def check_anomaly_conflict(text: str) -> dict[str, Any]:
    anomaly_terms = ["同比", "环比", "份额", "排名", "暴涨", "下滑", "退坡", "收紧", "异常"]
    explain_terms = ["原因", "触发", "解释", "风险", "待核验", "假设", "受", "由于"]
    has_anomaly = any(term in text for term in anomaly_terms)
    has_explain = any(term in text for term in explain_terms)
    if not has_anomaly:
        return make_check("anomaly_conflict", "通过", 82, "未识别到明显异常指标表达。", "出现同比/环比/份额异常时应补充原因解释。")
    if has_explain:
        return make_check("anomaly_conflict", "通过", 86, "识别到异常/变化指标，并包含原因或风险解释。", "保留异常解释和触发条件。")
    return make_check("anomaly_conflict", "待核验", 55, "出现同比/环比/份额/政策变化，但解释不足。", "补充异常原因、数据核验或业务触发条件。")


def check_traceability(text: str) -> dict[str, Any]:
    decision_terms = ["进入", "暂缓", "调配", "投放", "缩减", "扩张", "建议"]
    evidence_terms = ["证据", "依据", "来源", "因为", "由于", "数据显示", "假设", "待补充"]
    decision_count = sum(text.count(term) for term in decision_terms)
    evidence_count = sum(text.count(term) for term in evidence_terms)
    if decision_count and evidence_count >= max(2, decision_count // 2):
        return make_check("traceability", "通过", 90, f"决策表达 {decision_count} 处，证据/依据表达 {evidence_count} 处。", "建议在表格中进一步绑定“结论-证据-动作”。")
    if decision_count:
        return make_check("traceability", "风险", 42, f"决策表达 {decision_count} 处，但证据/依据表达仅 {evidence_count} 处。", "每条进入/暂缓/产能建议都应补充来源、假设或数据缺口。")
    return make_check("traceability", "待核验", 58, "报告缺少明确决策动作。", "如果是咨询报告，应输出可执行建议和证据链。")


def build_suggested_actions(checks: list[dict[str, Any]]) -> list[str]:
    actions = [item["suggestion"] for item in checks if item["status"] in {"待核验", "风险", "阻断"}]
    if not actions:
        return ["质量门禁通过，可进入报告沉淀、PPT生成和后续汇报。"]
    deduped: list[str] = []
    for action in actions:
        if action not in deduped:
            deduped.append(action)
    return deduped[:5]
