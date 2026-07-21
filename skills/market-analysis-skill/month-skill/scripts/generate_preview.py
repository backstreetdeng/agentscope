"""Generate a five-slide editable PPTX preview without calling MiniMax."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
sys.path.insert(0, str(PAYLOAD))

from utils.monthly_report_pptx import build_monthly_report_pptx  # noqa: E402


REPORT = """# 2026年6月中国乘用车市场分析报告（安装包预览）

## 2.1 车型类别
### 类别市场继续分化，主力车型产品周期决定短期修复节奏
6月，各车型类别走势仍有差异，轿车、SUV与MPV的变化需要结合代表车型和产品周期判断；本预览只验证数据映射与PPTX版式，正式结论须通过证据门禁。

## 2.2 车型级别
### 主流级别竞争加剧，份额迁移由新品承接与存量产品表现共同推动
6月，各级别市场结构继续变化，新增供给、价格竞争和同期基数是需要重点核验的原因；正式报告应落到2至3个代表车型并说明结构含义。

## 2.3 轿车级别分析
### 轿车内部结构分化，主力车型增减量反映不同产品周期
6月，轿车各级别表现分化，代表车型的同比、环比和排名变化用于识别增量与拖累；产品改款、促销和能源替代原因需与事件时间一致后才能写为确定结论。

## 2.4 SUV级别分析
### SUV主流级别竞争延续，新品爬坡与老产品切换影响结构表现
6月，SUV市场仍由主力价格带和核心车型竞争主导，报告应区分单一车型波动与级别需求变化，并持续跟踪新老产品承接和价格调整。

## 2.5 MPV级别分析
### MPV核心车型波动放大，产品换新窗口仍是主要观察变量
6月，MPV市场对少数核心车型更为敏感，车型换代、交付节奏和同期基数需结合内部资料核验，避免把短期单车波动直接解释为长期趋势。
"""


def main() -> None:
    profile = ROOT / "profiles" / "passenger_vehicle_monthly"
    output = ROOT / "dist" / "month-skill-preview-2026-06.pptx"
    output.parent.mkdir(parents=True, exist_ok=True)
    result = build_monthly_report_pptx(
        REPORT,
        output,
        profile / "assets" / "demo_monthly_data.xlsx",
        profile / "assets" / "monthly_report_template.pptx",
        sheet_name="6月",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
