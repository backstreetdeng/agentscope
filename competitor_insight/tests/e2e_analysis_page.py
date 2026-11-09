"""BCI-006 · 即时分析浏览器端到端断言（真实服务 + 真实库）。

运行：
    E:\\AI\\data\\envs\\helloagent\\Scripts\\python.exe -B competitor_insight/tests/e2e_analysis_page.py

产出：outputs/competitor-insights/BCI-006/20261107-analysis/screenshots/
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SHOT_DIR = ROOT / "outputs" / "competitor-insights" / "BCI-006" / "20261107-analysis" / "screenshots"
BASE_URL = "http://127.0.0.1:7860/"
FAILURES: list[str] = []
CONSOLE_ERRORS: list[str] = []
PAGE_ERRORS: list[str] = []
HTTP_ERRORS: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"PASS  {message}")
    else:
        FAILURES.append(message)
        print(f"FAIL  {message}")


def main() -> int:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1200}, device_scale_factor=1)
        page.on("console", lambda message: CONSOLE_ERRORS.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: PAGE_ERRORS.append(str(error)))
        page.on(
            "response",
            lambda response: HTTP_ERRORS.append(f"{response.status} {response.url}")
            if response.status >= 400 else None,
        )
        page.goto(BASE_URL + "#bci", wait_until="domcontentloaded", timeout=120000)

        nav = page.locator("[data-view='bci']").first
        if nav.count():
            nav.click()
        page.wait_for_selector("[data-bci-tab='analyze']:not([disabled])", timeout=30000)
        page.locator("[data-bci-tab='analyze']").click()

        page.wait_for_selector(".bci-a-entry", timeout=180000)
        page.wait_for_function(
            "() => document.querySelectorAll('.bci-a-entry').length === 4 && "
            "document.querySelectorAll('.bci-a-stack > div').length === 1 && "
            "document.body.innerText.includes('定量样本')",
            timeout=180000,
        )
        stack_ids = "Array.from(document.querySelectorAll('.bci-a-stack > div')).map(n => n.id)"

        # 入口卡片：四卡横排，默认只展开「用户画像」，其余不占版面。
        check(page.locator(".bci-a-entry").count() == 4, "入口共 4 张卡片")
        check(page.locator(".bci-a-entry.is-open").count() == 1, "默认仅 1 张卡片为展开态")
        check("已展开" in page.locator(".bci-a-entry.is-open").inner_text(), "已选中的卡片有「已展开」标记")
        check(page.evaluate(stack_ids) == ["bci-a-panel-profile"], "默认只渲染用户画像内容块")
        check(page.locator(".bci-a-tile").count() == 1, "未选中的三块不占版面")
        check(page.locator("[data-bci-analysis-model] option").count() == 5, "车型下拉 5 款")

        page.locator("[data-bci-analysis]").scroll_into_view_if_needed()
        page.screenshot(path=str(SHOT_DIR / f"analysis-b10-entries-{stamp}.png"))

        # 逐卡展开，验证多选叠加与选中顺序。
        for key, expect_count in (("attention", 2), ("winloss", 3), ("satisfaction", 4)):
            page.click(f"[data-bci-analysis-toggle='{key}']")
            page.wait_for_function(
                f"() => document.querySelectorAll('.bci-a-stack > div').length === {expect_count}",
                timeout=30000,
            )
        check(
            page.evaluate(stack_ids) == [
                "bci-a-panel-profile", "bci-a-panel-attention",
                "bci-a-panel-winloss", "bci-a-panel-satisfaction",
            ],
            "内容块按选中顺序纵向堆叠",
        )
        check(page.locator(".bci-a-entry.is-open").count() == 4, "四张卡片均为展开态")
        check(page.locator(".bci-a-tile").count() == 4, "四块内容全部可见")

        text = page.locator("[data-bci-analysis]").inner_text()
        for phrase in (
            "零跑B10", "定量样本", "深访", "口碑提及", "配置款型",
            "用户画像", "购车关注", "选择与放弃", "满意度", "综合结论",
        ):
            check(phrase in text, f"页面出现「{phrase}」")
        check("n=41" in text, "页面显示样本基数 n=41")
        check("第一排序" in text and "无排序题" in text, "第一排序空态 + 具体原因")
        check("对手为什么赢" in text and "没有未购车用户样本" in text, "对手为什么赢空态 + 具体原因")
        check("放弃核心对比车型的原因" in text, "使用用户确认的「放弃核心对比车型的原因」措辞")
        check("首增换购属性是人群分类" in text, "明确首增换购是人群分类而非原因")
        check("深访 4 人" in text, "深访原话标注人数")
        check("不做比例" in text, "深访原话声明不做比例")
        check("定性 " in text, "16 维明细带定性人数")
        check("/41" in text, "比例显示分子/分母")

        page.screenshot(path=str(SHOT_DIR / f"analysis-b10-{stamp}.png"), full_page=True)
        page.locator("[data-bci-analysis]").scroll_into_view_if_needed()
        page.screenshot(path=str(SHOT_DIR / f"analysis-b10-viewport-{stamp}.png"))
        for index, tile in enumerate(page.locator(".bci-a-tile").all(), start=1):
            tile.scroll_into_view_if_needed()
            tile.screenshot(path=str(SHOT_DIR / f"tile-{index}-b10-{stamp}.png"))
        print(f"SHOT  {SHOT_DIR / f'analysis-b10-{stamp}.png'}")

        # 收起单卡：内容块消失且其余顺序不变；再展开追加到末尾。
        page.click("[data-bci-analysis-toggle='profile']")
        page.wait_for_function(
            "() => document.querySelectorAll('.bci-a-stack > div').length === 3",
            timeout=30000,
        )
        check(page.locator("#bci-a-panel-profile").count() == 0, "收起用户画像后内容块不再占版面")
        check(
            page.evaluate(stack_ids) == [
                "bci-a-panel-attention", "bci-a-panel-winloss", "bci-a-panel-satisfaction",
            ],
            "收起后其余内容块顺序不变",
        )
        check(page.locator(".bci-a-entry.is-open").count() == 3, "收起后仅 3 张卡片为展开态")
        page.click("[data-bci-analysis-toggle='profile']")
        page.wait_for_function(
            "() => document.querySelectorAll('.bci-a-stack > div').length === 4",
            timeout=30000,
        )
        check(page.evaluate(stack_ids)[-1] == "bci-a-panel-profile", "重新展开的内容块追加到堆叠末尾")

        # 切到钛3，验证车型切换与 n=30。
        page.select_option("[data-bci-analysis-model]", "fangchengbao-tai3")
        page.wait_for_function(
            "() => document.body.innerText.includes('钛3：定量样本 30 人')",
            timeout=180000,
        )
        text2 = page.locator("[data-bci-analysis]").inner_text()
        check("钛3：定量样本 30 人" in text2, "切换钛3后综合结论更新为真实样本")
        check("n=30" in text2, "钛3 样本基数 n=30")
        check(page.locator(".bci-a-tile").count() == 4, "切换后仍为 4 个磁贴")
        page.screenshot(path=str(SHOT_DIR / f"analysis-tai3-{stamp}.png"), full_page=True)
        print(f"SHOT  {SHOT_DIR / f'analysis-tai3-{stamp}.png'}")

        browser.close()

    check(not PAGE_ERRORS, f"浏览器无 JS 运行时异常（{len(PAGE_ERRORS)}）")
    for item in PAGE_ERRORS[:5]:
        print("  pageerror:", item)
    # /api/health 是首页既有探活请求，与即时分析无关，列为已知基线。
    unexpected = [
        item for item in HTTP_ERRORS
        if "favicon" not in item.lower() and "/api/health" not in item
    ]
    check(not unexpected, f"页面资源无 4xx/5xx（{len(unexpected)}）")
    for item in unexpected[:5]:
        print("  http:", item)

    print("\n===== RESULT =====")
    if FAILURES:
        print(f"FAILED {len(FAILURES)} 项")
        for item in FAILURES:
            print(" -", item)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
