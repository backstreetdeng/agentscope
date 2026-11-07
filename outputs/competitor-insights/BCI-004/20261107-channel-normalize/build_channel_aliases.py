"""根据全库分布生成渠道归并表（呈现/统计层）。只读产物，写入模板目录。

映射原则：
- 同义/简称/子频道 → 模板标准渠道；
- 模板未单列但可识别的具体渠道 → 「其他」（依据写明）；
- 非渠道描述、复合短语、噪声 → 「未归类」，不硬塞。

用法：../Scripts/python.exe -B outputs/competitor-insights/BCI-004/20261107-channel-normalize/build_channel_aliases.py
"""

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
sys.path.insert(0, str(ROOT))

TARGETS = [
    "抖音", "小红书", "B站", "懂车帝", "汽车之家", "豆包/AI问答",
    "车展", "商场展车", "到店咨询", "朋友推荐", "其他",
]
UNCATEGORIZED = "未归类"

# raw -> (target, basis)
MAPPING = {
    "抖音": ("抖音", "标准值"),
    "懂车帝": ("懂车帝", "标准值"),
    "汽车之家": ("汽车之家", "标准值"),
    "小红书": ("小红书", "标准值"),
    "B站": ("B站", "标准值"),
    "朋友推荐": ("朋友推荐", "标准值"),
    "哔哩哔哩": ("B站", "同义/简称（B站全称）"),
    "线下门店": ("到店咨询", "同义（线下到店）"),
    "朋友介绍": ("朋友推荐", "同义（口语表述）"),
    "朋友分享": ("朋友推荐", "同义（口语表述）"),
    "车展活动": ("车展", "同义（车展活动）"),
    "抖音精选": ("抖音", "平台子频道（抖音精选）"),
    "抖音搜索车型视频": ("抖音", "平台子频道（抖音内搜索）"),
    "视频号": ("其他", "模板未单列渠道（微信视频号）"),
    "微信": ("其他", "模板未单列渠道（微信生态）"),
    "微信朋友圈": ("其他", "模板未单列渠道（微信生态）"),
    "微信推送": ("其他", "模板未单列渠道（微信生态）"),
    "微信视频号": ("其他", "模板未单列渠道（微信生态）"),
    "公众号": ("其他", "模板未单列渠道（微信生态）"),
    "微信读书": ("其他", "模板未单列渠道（阅读应用）"),
    "微博": ("其他", "模板未单列渠道"),
    "快手": ("其他", "模板未单列渠道"),
    "今日头条": ("其他", "模板未单列渠道"),
    "头条": ("其他", "同义（今日头条简称），模板未单列"),
    "淘宝": ("其他", "模板未单列渠道（电商）"),
    "京东": ("其他", "模板未单列渠道（电商）"),
    "拼多多": ("其他", "模板未单列渠道（电商）"),
    "闲鱼": ("其他", "模板未单列渠道（二手平台）"),
    "瓜子二手车": ("其他", "模板未单列渠道（二手车平台）"),
    "大众点评": ("其他", "模板未单列渠道（生活平台）"),
    "支付宝": ("其他", "模板未单列渠道（生活平台）"),
    "百度": ("其他", "模板未单列渠道（搜索）"),
    "腾讯": ("其他", "模板未单列渠道"),
    "腾讯新闻": ("其他", "模板未单列渠道"),
    "腾讯视频": ("其他", "模板未单列渠道（视频平台）"),
    "视频平台": ("其他", "模板未单列渠道（泛指视频平台）"),
    "优酷": ("其他", "模板未单列渠道（视频平台）"),
    "爱奇艺": ("其他", "模板未单列渠道（视频平台）"),
    "西瓜视频": ("其他", "模板未单列渠道（视频平台）"),
    "直播吧": ("其他", "模板未单列渠道（社区）"),
    "论坛": ("其他", "模板未单列渠道（社区）"),
    "车友群": ("其他", "模板未单列渠道（社区）"),
    "知乎": ("其他", "模板未单列渠道（社区）"),
    "虎扑车区": ("其他", "模板未单列渠道（社区板块）"),
    "QQ": ("其他", "模板未单列渠道（社交）"),
    "收音机": ("其他", "模板未单列渠道（传统媒体）"),
    "官网": ("其他", "模板未单列渠道（品牌官网）"),
    "汽车博主": ("其他", "模板未单列渠道（自媒体）"),
    "自媒体": ("其他", "模板未单列渠道（泛指自媒体）"),
    "未提及": (UNCATEGORIZED, "无数据表述，原样保留但不计入渠道"),
    "主动定向检索": (UNCATEGORIZED, "非渠道描述（检索行为）"),
    "主要由对象获取": (UNCATEGORIZED, "非渠道描述（信息获取主体）"),
    "对象每天看汽车视频": (UNCATEGORIZED, "非渠道描述（主体+内容）"),
    "偏好网上综合信息": (UNCATEGORIZED, "非渠道描述（偏好表述）"),
    "关注新款配置": (UNCATEGORIZED, "非渠道描述（内容偏好）"),
    "网上看车型信息": (UNCATEGORIZED, "非渠道描述（泛化描述）"),
    "官方发布": (UNCATEGORIZED, "无法归并（信息类型）"),
    "大咖测评": (UNCATEGORIZED, "无法归并（内容类型，非渠道）"),
    "大众点评及多种财经资讯应用": (UNCATEGORIZED, "无法归并（复合短语）"),
    "科普视频与新闻发布会": (UNCATEGORIZED, "无法归并（复合短语）"),
    "说车内容及工信部新车信息": (UNCATEGORIZED, "无法归并（复合短语）"),
    "车主实际用车分享和车展": (UNCATEGORIZED, "无法归并（复合短语，含车展但不硬拆）"),
    "股票类应用": (UNCATEGORIZED, "无法归并（非汽车信息渠道）"),
    "王者荣耀": (UNCATEGORIZED, "无法归并（非汽车信息渠道）"),
}

distribution = json.loads((BASE / "channel_distribution.json").read_text(encoding="utf-8"))
raw_set = {item["raw"] for item in distribution["entries"]}

missing = sorted(raw_set - set(MAPPING))
extra = sorted(set(MAPPING) - raw_set)
if missing or extra:
    raise SystemExit(f"映射未覆盖全部写法：missing={missing} extra={extra}")

entries = [
    {"raw": item["raw"], "target": MAPPING[item["raw"]][0],
     "count": item["count"], "basis": MAPPING[item["raw"]][1]}
    for item in distribution["entries"]
]

payload = {
    "version": 1,
    "dimension_id": "info_channels",
    "scope": "presentation",  # 仅呈现/统计层；原始写法保留在 archive_field.source_ref
    "snapshot": "2026-11-07",
    "source": distribution["source"],
    "targets": TARGETS,
    "uncategorized": UNCATEGORIZED,
    "coverage": {
        "distinct_raw": len(raw_set),
        "mapped": len(entries),
        "tag_records": distribution["total_tag_records"],
    },
    "entries": entries,
}

out = ROOT / "competitor_insight/templates/info_channel_aliases.json"
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"covered {len(entries)}/{len(raw_set)} writings -> {out}")
