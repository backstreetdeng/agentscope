"""D4 真实库只读探针：模板 / 受访者列表 / 详情空态 / 找原话。

只读，不写 bci.*；不打印任何连接凭据。
用法：在项目根执行
  ../Scripts/python.exe -B outputs/competitor-insights/BCI-004/20261107-d4-api/probe_api.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from competitor_insight.server.archive_api import ApiError, ArchiveService  # noqa: E402
from competitor_insight.server.archive_store import PostgresArchiveStore  # noqa: E402
from competitor_insight.server.db import connect  # noqa: E402
from competitor_insight.server.quote_service import QuoteService  # noqa: E402


def main() -> int:
    service = ArchiveService(
        PostgresArchiveStore(connect), quotes=QuoteService(connect), background=False
    )
    failures = 0

    template = service.template()["data"]
    print(
        f"[template] id={template['template_id']} version={template['version']} "
        f"dimensions={template['dimension_count']} groups={len(template['groups'])} "
        f"source_map_ready={template['source_map_ready']}"
    )
    failures += template["dimension_count"] != 43

    respondents = service.respondents(limit=200)["data"]
    archived = sum(1 for item in respondents["items"] if item["archive"])
    print(
        f"[respondents] total={respondents['total']} returned={len(respondents['items'])} "
        f"with_archive={archived}"
    )
    failures += respondents["total"] != 63

    sample = respondents["items"][0]
    print(
        f"[respondent] {sample['interview_id']} city={sample['city']} "
        f"model={sample['vehicle_model']} purchase={sample['purchase_type']} "
        f"archive={sample['archive']}"
    )

    detail = service.detail(sample["interview_id"])["data"]
    print(
        f"[detail] interview={sample['interview_id']} archive={detail['archive']} "
        f"fields={len(detail['fields'])}"
    )

    quotes = service.quote(sample["interview_id"], "空间", limit=5)["data"]
    print(
        f"[quote] keyword={quotes['keyword']} total={quotes['total']} "
        f"counts={quotes['counts']}"
    )

    try:
        service.export([sample["interview_id"]])
    except ApiError as exc:
        print(f"[export] blocked_as_expected code={exc.code} ids={exc.extra.get('interview_ids')}")
        failures += exc.code != "archive_missing"

    print(f"[result] failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
