"""Run the real monthly headline workflow against one persisted card package."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from integrations.market_mcp_plugins import load_market_mcp_plugins
from utils.config import load_json_config
from utils.monthly_report_narrative import generate_monthly_narratives
import utils.monthly_report_narrative as narrative_workflow


SKILL_DIR = PROJECT_DIR / "skills" / "market-analysis-skill" / "passenger-car-monthly-report"


async def run(package_path: Path, run_id: str, provider: str, pages: tuple[int, ...] = ()) -> dict:
    if pages:
        # Focused local acceptance of the same production prompt, model and
        # validators; this is not an archived/completed web job.
        if any(page not in narrative_workflow.TARGET_PAGES for page in pages):
            raise ValueError("评审页码不在业务数据页范围内。")
        narrative_workflow.BATCHES = (pages,)
        narrative_workflow.TARGET_PAGES = pages
    load_dotenv(PROJECT_DIR / ".env", override=True)
    load_dotenv(PROJECT_DIR / ".env.zhipu", override=True)
    config = load_json_config()
    config["active_provider"] = provider
    bundle = await load_market_mcp_plugins(
        config,
        agent_key="market_strategy",
        selected_plugin_ids=["policy", "rights", "new-car", "reputation"],
    )
    print(json.dumps(bundle.as_dict(), ensure_ascii=False), flush=True)
    package = json.loads(package_path.read_text(encoding="utf-8"))
    result = await generate_monthly_narratives(
        package,
        run_id=run_id,
        config=config,
        plugin_tools=bundle.tools,
        mapping_path=SKILL_DIR / "assets" / "乘用车月报-数据源映射指标.xlsx",
        examples_path=SKILL_DIR / "assets" / "expert-headline-examples.json",
        output_dir=PROJECT_DIR / "outputs" / "monthly-report-data",
        progress=lambda message, progress: print(f"{progress}% {message}", flush=True),
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--run-id", default="monthly-narrative-eval")
    parser.add_argument("--provider", default="minimax")
    parser.add_argument("--pages", default="", help="定向评审页码，如9,10,11；不创建或覆盖网页任务")
    args = parser.parse_args()
    pages = tuple(int(value) for value in args.pages.split(",") if value.strip())
    result = asyncio.run(run(args.package.resolve(), args.run_id, args.provider, pages))
    print(json.dumps({
        "path": result["path"],
        "slides": len(result["slides"]),
        "evidence": len(result["evidence"]),
        "headlines": [{"slide": item["slide"], "headline": item["headline"]} for item in result["slides"]],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
