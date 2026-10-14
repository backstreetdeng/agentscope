"""Policy presentation adapter: the same remote MCP catalog as agent tools.

No local snapshot fallback and no independent database credentials.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any



def decode_result(result: Any) -> dict:
    if result.isError:
        raise ValueError("政策 MCP 工具查询失败")
    for block in result.content:
        if getattr(block, "type", "") == "text":
            value = json.loads(block.text)
            if value.get("success") is not True:
                raise ValueError("政策 MCP 未返回成功数据")
            return value
    raise ValueError("政策 MCP 返回格式不受支持")


def _latest_collection_date(status: dict, records: list[dict]) -> str:
    """Use the newest policy monitoring date from the formal MCP result.

    Historical imports did not persist a batch completion timestamp.  The
    policy table's monitor_date is the authoritative collection/publication
    date exposed in the MCP record, so it is a truthful replacement rather
    than showing a misleading placeholder or a static snapshot date.
    """
    declared = str(status.get("latest_collection_date") or "").strip()
    if declared:
        return declared
    dates = []
    for record in records:
        value = str(record.get("监测日期/发布日期") or "").strip()
        matched = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", value)
        if not matched:
            continue
        try:
            dates.append(datetime(*(int(part) for part in matched.groups())).date())
        except ValueError:
            continue
    return max(dates).isoformat() if dates else "未提供"


def summarize(status: dict, records: list[dict]) -> dict:
    year = str(datetime.now().year)
    rules = [("购车补贴", "购车补贴|汽车补贴|补助"), ("消费券", "消费券"),
             ("以旧换新", "以旧换新|报废更新|置换"), ("金融贴息", "贴息|贷款|金融"),
             ("新能源专项", "新能源|纯电|电动汽车")]
    topics = [{"label": label, "count": sum(bool(re.search(pattern, " ".join(
        str(r.get(k) or "") for k in ("政策名称", "当前政策补贴内容",
        "适用客群（首购/增换购；个人/单位消费者；新能源/燃油车）")))) for r in records)}
        for label, pattern in rules]
    latest = sorted((r for r in records if r.get("政策名称")),
                    key=lambda r: str(r.get("监测日期/发布日期") or ""), reverse=True)[:1]
    return {"total": len(records), "year": year,
            "yearCount": sum(str(r.get("监测日期/发布日期") or "").startswith(year + "-") for r in records),
            "provinceCount": len({r["省份"] for r in records if r.get("省份")}),
            "cityCount": len({(r.get("省份", ""), r["城市"]) for r in records if r.get("城市")}),
            "topics": topics, "latest": latest,
            "fieldCount": len({k for r in records for k in r}),
            "source": status.get("source") or "来源信息未提供",
            "storage": status.get("storage_backend") or "MCP 服务未提供存储类型",
            "dataVersion": status.get("data_version") or "未提供",
            "lastSuccessfulImport": status.get("last_successful_import") or "未提供",
            "latestCollectionDate": _latest_collection_date(status, records),
            "asOf": status.get("as_of") or "未提供",
            "blankCount": sum(not any(r.get(k) for k in ("政策名称", "省份", "城市", "当前政策补贴内容", "信息来源链接")) for r in records)}


async def fetch_policy_overview(config: dict) -> dict:
    from .market_data_api import get_data
    return await get_data(config, "policy/overview", plugin_id="policy")


async def load_policy_overview(config: dict) -> dict:
    return await asyncio.wait_for(fetch_policy_overview(config), timeout=90)
