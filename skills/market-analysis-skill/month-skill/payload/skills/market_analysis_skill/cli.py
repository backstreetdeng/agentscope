"""市场月报分析 Skill 的本地调试入口，不调用大模型、不消耗 Token。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runtime import ANALYSIS_TYPE, MarketAnalysisSkill


def main() -> None:
    parser = argparse.ArgumentParser(description="校验中国乘用车市场月报 Excel 数据集。")
    parser.add_argument("--input", help="待校验的 .xlsx 路径；不传时使用项目配置/业务验数样本。")
    parser.add_argument("--question", default="请生成中国乘用车月度市场分析报告。", help="用于验证触发规则的业务问题。")
    parser.add_argument("--auto", action="store_true", help="按关键词自动触发；默认显式激活月报 Skill。")
    parser.add_argument("--json", action="store_true", help="输出 JSON，便于接入 CI 或后续编排。")
    args = parser.parse_args()

    skill = MarketAnalysisSkill()
    context = skill.prepare(
        question=args.question,
        analysis_type="" if args.auto else ANALYSIS_TYPE,
        dataset_path=Path(args.input) if args.input else None,
    )
    payload = context.as_response()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"Skill: {payload['name']} v{payload['version']}")
    print(f"激活状态: {payload['active']} ({payload['trigger_mode']})")
    print(f"数据集: {payload['dataset']['path'] or '未找到'}")
    print(f"输入门禁: {payload['input_gate']}")
    for check in payload["input_checks"]:
        print(f"- [{check['status']}] {check['name']}: {check['evidence']}")
    print("\n模型上下文预览：")
    print(context.prompt_context[:3000])


if __name__ == "__main__":
    main()
