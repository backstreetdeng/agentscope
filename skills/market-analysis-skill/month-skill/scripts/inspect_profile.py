"""Print a compact view of the monthly business profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise SystemExit("PyYAML is required. Run: python -m pip install -r requirements.txt") from exc


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect the monthly report profile")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    args = parser.parse_args()

    profile = yaml.safe_load(
        (ROOT / "profiles" / "passenger_vehicle_monthly" / "profile.yaml").read_text(encoding="utf-8")
    )
    specs = yaml.safe_load(
        (ROOT / "profiles" / "passenger_vehicle_monthly" / "page_specs.yaml").read_text(encoding="utf-8")
    )
    payload = {
        "id": profile["id"],
        "version": profile["version"],
        "agentscope": profile["compatibility"]["agentscope"],
        "tested_model": profile["compatibility"]["tested_model"],
        "pages": specs["pages"],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"Profile: {payload['id']} v{payload['version']}")
    print(f"Runtime: AgentScope {payload['agentscope']} / {payload['tested_model']}")
    print("Pages:")
    for page in payload["pages"]:
        lenses = "、".join(page.get("analysis_lens", []))
        print(
            f"  {page['order']}. {page['section']} {page['title']} | "
            f"data={page['data_block']} | renderer={page['renderer_handler']} | {lenses}"
        )


if __name__ == "__main__":
    main()
