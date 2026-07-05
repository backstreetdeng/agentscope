"""调研音频任务编排与用户标签分析引擎。

当前文件是 Demo 版的本地业务引擎，用于把“访谈类音频处理工作流”
抽象成可被 Web 页面调用的结构化结果。后续接入真实系统时，可以把这里的
规则打标替换为 ASR、说话人分离、LLM 标签抽取、向量库和结构化数据库。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any


DEFAULT_TAG_TAXONOMY: dict[str, list[str]] = {
    "用户身份": ["家庭用户", "首购青年", "增换购", "网约运营", "科技尝鲜"],
    "购车动机": ["通勤", "家庭出游", "面子", "智能体验", "省钱", "牌照政策"],
    "核心痛点": ["续航焦虑", "补能焦虑", "智驾信任", "空间", "舒适", "安全", "保值"],
    "配置诉求": ["800V", "热泵", "激光雷达", "冰箱", "彩电", "大沙发", "HUD", "座椅通风"],
    "付费意愿": ["必须有", "可选装", "无感知", "反感"],
    "竞品对比": ["Model Y", "问界", "理想", "比亚迪", "零跑", "小米"],
}


@dataclass(frozen=True)
class InterviewRecord:
    """访谈切片样例，模拟 ASR + 说话人分离 + 脱敏后的片段级数据。"""

    user_id: str
    audio_name: str
    region: str
    city_tier: str
    duration: str
    speaker_count: int
    transcript: str


SAMPLE_INTERVIEW_RECORDS: list[InterviewRecord] = [
    InterviewRecord(
        user_id="U001",
        audio_name="family_suv_depth_01.wav",
        region="华东",
        city_tier="新一线",
        duration="18:42",
        speaker_count=2,
        transcript=(
            "我家两个孩子，周末经常带老人一起出去，后排空间、安全气囊和主动刹车必须靠谱。"
            "冬天续航别掉太厉害，最好有热泵和800V快充，智驾可以选装但别太贵。"
        ),
    ),
    InterviewRecord(
        user_id="U002",
        audio_name="young_first_car_03.wav",
        region="华南",
        city_tier="一线",
        duration="12:08",
        speaker_count=1,
        transcript=(
            "我是第一辆车，通勤为主，希望车机流畅、HUD好用，外观有科技感。"
            "我会对比小米和Model Y，激光雷达有当然好，但价格超过预算就算了。"
        ),
    ),
    InterviewRecord(
        user_id="U003",
        audio_name="ride_hailing_owner_02.wav",
        region="华中",
        city_tier="二线",
        duration="21:15",
        speaker_count=2,
        transcript=(
            "跑网约车最关心省钱、续航和补能，电耗低、保值率高才敢买。"
            "座椅通风很实用，冰箱彩电这些我基本无感，维修成本不能高。"
        ),
    ),
    InterviewRecord(
        user_id="U004",
        audio_name="trade_in_family_04.wav",
        region="西南",
        city_tier="二线",
        duration="16:31",
        speaker_count=2,
        transcript=(
            "现在油车准备置换，主要是牌照政策和用车成本。我们看过比亚迪和理想，"
            "希望空间大、座椅舒服，智驾我不太信任，安全配置必须标配。"
        ),
    ),
    InterviewRecord(
        user_id="U005",
        audio_name="tech_early_adopter_05.wav",
        region="华北",
        city_tier="一线",
        duration="14:27",
        speaker_count=1,
        transcript=(
            "我比较愿意尝鲜，城市NOA、激光雷达、800V和OTA体验都很重要。"
            "问界和小米的智能化我会重点看，如果大沙发和音响也强，会更愿意付费。"
        ),
    ),
    InterviewRecord(
        user_id="U006",
        audio_name="budget_sensitive_06.wav",
        region="东北",
        city_tier="三线",
        duration="10:54",
        speaker_count=1,
        transcript=(
            "预算卡得很死，买新能源主要为了省钱，续航和冬季掉电我很担心。"
            "冰箱彩电我反感，不想为花哨配置付钱，热泵和安全配置倒是必须有。"
        ),
    ),
]


TAG_KEYWORDS: dict[str, list[str]] = {
    "家庭用户": ["孩子", "老人", "家庭", "周末", "后排"],
    "首购青年": ["第一辆车", "通勤", "外观", "科技感"],
    "增换购": ["置换", "油车", "换购"],
    "网约运营": ["网约车", "跑网约", "运营"],
    "科技尝鲜": ["尝鲜", "NOA", "OTA", "智能化"],
    "通勤": ["通勤"],
    "家庭出游": ["周末", "出去", "老人", "孩子"],
    "面子": ["外观", "科技感", "音响"],
    "智能体验": ["车机", "智驾", "NOA", "HUD", "OTA", "智能化"],
    "省钱": ["省钱", "电耗", "成本", "预算"],
    "牌照政策": ["牌照", "政策"],
    "续航焦虑": ["续航", "掉电"],
    "补能焦虑": ["补能", "快充", "800V"],
    "智驾信任": ["不太信任", "智驾"],
    "空间": ["空间", "后排"],
    "舒适": ["舒服", "座椅", "大沙发"],
    "安全": ["安全", "主动刹车", "气囊"],
    "保值": ["保值"],
    "800V": ["800V"],
    "热泵": ["热泵"],
    "激光雷达": ["激光雷达"],
    "冰箱": ["冰箱"],
    "彩电": ["彩电"],
    "大沙发": ["大沙发"],
    "HUD": ["HUD"],
    "座椅通风": ["座椅通风"],
    "必须有": ["必须", "标配"],
    "可选装": ["选装", "超过预算就算"],
    "无感知": ["无感"],
    "反感": ["反感", "不想为"],
    "Model Y": ["Model Y"],
    "问界": ["问界"],
    "理想": ["理想"],
    "比亚迪": ["比亚迪"],
    "零跑": ["零跑"],
    "小米": ["小米"],
}


CONFIG_MAPPING: dict[str, str] = {
    "续航焦虑": "电池热管理、长续航电池包、低温续航校准",
    "补能焦虑": "800V高压平台、快充兼容、充电路线规划",
    "智驾信任": "激光雷达冗余、AEB实测背书、智驾透明提示",
    "空间": "长轴距、后排纯平地台、后备箱拓展",
    "舒适": "座椅通风/加热、大沙发、静音玻璃",
    "安全": "主动安全、全车气囊、儿童安全场景",
    "省钱": "低电耗、保养成本、三电质保",
}


def build_audio_workflow(instruction: str) -> list[dict[str, str]]:
    """生成从音频上传到入库的任务链，并根据指令补充重点。"""

    priority = "标签与配置映射优先"
    if "隐私" in instruction or "脱敏" in instruction:
        priority = "隐私脱敏与合规优先"
    elif "向量" in instruction or "检索" in instruction:
        priority = "可检索数据资产优先"

    return [
        {"step": "原始音频接收", "owner": "调研音频编排Agent", "output": "音频文件、项目ID、受访者授权记录"},
        {"step": "ASR转写", "owner": "ASR模块", "output": "逐字稿、时间戳、置信度"},
        {"step": "说话人分离", "owner": "Diarization模块", "output": "说话人角色、轮次边界"},
        {"step": "隐私脱敏", "owner": "合规模块", "output": "脱敏文本、敏感字段审计"},
        {"step": "片段切分", "owner": "语义切片模块", "output": "按购车话题切分的语义片段"},
        {"step": "用户标签", "owner": "用户标签Agent", "output": f"标准标签、证据句、策略={priority}"},
        {"step": "情绪/强度评分", "owner": "洞察评分模块", "output": "情绪极性、需求强度、痛点强度"},
        {"step": "配置映射", "owner": "配置定义Agent", "output": "配置诉求、标配/选装建议"},
        {"step": "数据入库", "owner": "MCP数据连接层", "output": "结构化数据库、向量库、检索索引"},
    ]


def infer_tags(record: InterviewRecord) -> dict[str, Any]:
    """基于访谈文本进行轻量自动打标，返回标签、证据和配置映射。"""

    text = record.transcript
    matched = [tag for tag, words in TAG_KEYWORDS.items() if any(word in text for word in words)]
    category_tags = {
        category: [tag for tag in tags if tag in matched]
        for category, tags in DEFAULT_TAG_TAXONOMY.items()
    }
    labels = [tag for tags in category_tags.values() for tag in tags]
    pain_tags = category_tags["核心痛点"]
    config_tags = category_tags["配置诉求"]
    config_mapping = [CONFIG_MAPPING[tag] for tag in pain_tags if tag in CONFIG_MAPPING]
    if config_tags:
        config_mapping.extend([f"{tag}配置需求校准" for tag in config_tags])

    emotion_score = 62 + min(len(pain_tags) * 6, 24)
    intensity_score = 58 + min((len(pain_tags) + len(config_tags)) * 5, 32)

    return {
        "user_id": record.user_id,
        "audio_name": record.audio_name,
        "region": record.region,
        "city_tier": record.city_tier,
        "duration": record.duration,
        "speaker_count": record.speaker_count,
        "transcript": record.transcript,
        "labels": labels,
        "category_tags": category_tags,
        "emotion_score": min(emotion_score, 96),
        "intensity_score": min(intensity_score, 98),
        "config_mapping": config_mapping[:5],
        "evidence": record.transcript[:96] + ("..." if len(record.transcript) > 96 else ""),
    }


def build_tag_statistics(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """统计单标签用户占比，用于前端图表展示。"""

    total = max(len(records), 1)
    counts = Counter(tag for record in records for tag in record["labels"])
    stats = [
        {"tag": tag, "count": count, "ratio": round(count / total * 100, 1)}
        for tag, count in counts.most_common()
    ]
    return stats[:16]


def build_cross_analysis(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """生成标签关联分析，帮助发现潜在用户特征关联。"""

    pair_counts: Counter[tuple[str, str]] = Counter()
    for record in records:
        labels = sorted(set(record["labels"]))
        for index, left in enumerate(labels):
            for right in labels[index + 1 :]:
                pair_counts[(left, right)] += 1

    insights = []
    for (left, right), count in pair_counts.most_common(8):
        if count < 2:
            continue
        insights.append(
            {
                "pair": f"{left} + {right}",
                "count": count,
                "insight": f"同时出现 {count} 次，建议在筛选中联动观察配置诉求和付费意愿。",
            },
        )
    return insights


def filter_records(records: list[dict[str, Any]], selected_tags: list[str]) -> list[dict[str, Any]]:
    """按前端快速选择的标签组合过滤用户片段。"""

    if not selected_tags:
        return records
    selected = set(selected_tags)
    return [record for record in records if selected.issubset(set(record["labels"]))]


def run_audio_tagging_workflow(instruction: str, selected_tags: list[str] | None = None) -> dict[str, Any]:
    """执行完整调研音频处理 Demo，返回前端可视化所需结构。"""

    all_records = [infer_tags(record) for record in SAMPLE_INTERVIEW_RECORDS]
    filtered_records = filter_records(all_records, selected_tags or [])
    stats = build_tag_statistics(filtered_records)
    cross = build_cross_analysis(filtered_records)

    return {
        "workflow": build_audio_workflow(instruction),
        "taxonomy": DEFAULT_TAG_TAXONOMY,
        "records": filtered_records,
        "all_record_count": len(all_records),
        "filtered_count": len(filtered_records),
        "statistics": stats,
        "cross_analysis": cross,
        "dataset_plan": [
            "采集层：保留原始音频、授权记录、项目问卷、访谈大纲和样本画像，建立可追溯批次号。",
            "加工层：ASR逐字稿必须带时间戳、置信度、说话人ID；脱敏前后文本分区存储，敏感字段只进合规库。",
            "标注层：采用标签体系版本号、证据句、人工复核状态和一致性评分，保证标签可解释、可回滚。",
            "入库层：结构化库存用户画像和标签事实表，向量库存语义片段和证据句，二者用segment_id打通。",
            "质检层：抽样复核ASR字错率、说话人分离准确率、标签一致性和配置映射命中率，低置信度样本回流重标。",
        ],
    }
