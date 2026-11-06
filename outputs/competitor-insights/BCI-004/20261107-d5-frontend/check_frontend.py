"""D5 前端离线验收：Playwright 加载 fixture.html，验证 43 行 / 无来源 / 评分缺失 / 证据 / 找原话 / 生成轮询。

不启动 7860，不访问真实库；只加载本地 CSS/JS 与 mock fetch。
用法：在项目根执行
  ../Scripts/python.exe -B outputs/competitor-insights/BCI-004/20261107-d5-frontend/check_frontend.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Playwright 浏览器实际装在用户缓存目录；默认的 AppData\Local\ms-playwright 不存在。
_BROWSER_CACHE = Path.home() / ".cache" / "ms-playwright"
if _BROWSER_CACHE.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSER_CACHE))

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture.html"
SHOT = HERE / "profile.png"

checks: list[str] = []
errors: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    checks.append(f"{'PASS' if condition else 'FAIL'} | {name}" + (f" | {detail}" if detail else ""))
    if not condition:
        errors.append(name)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1320, "height": 900})
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
        page.on("console", lambda msg: errors.append(f"console: {msg.text}") if msg.type == "error" else None)

        try:
            run_checks(page)
        except Exception as exc:  # noqa: BLE001 - 保留已收集的 PASS/失败证据
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            browser.close()

    print("\n".join(checks))
    print(f"[page] screenshot={SHOT.name} errors={len(errors)}")
    if errors:
        print("\n".join(f"ERROR | {item}" for item in errors))
        return 1
    return 0


def run_checks(page) -> None:
    page.goto(FIXTURE.as_uri())
    page.wait_for_selector("#profile .bp-table tbody tr")

    rows = page.locator("#profile .bp-table tbody tr")
    check("43 维度行", rows.count() == 43, f"rows={rows.count()}")
    check("左侧 3 位受访者", page.locator("#profile .bp-item").count() == 3)
    check("模板信息已渲染", "用户洞察档案模板" in page.locator("#profile .bp-scope__template").inner_text())
    group_cells = page.locator("#profile .bp-table tbody .bp-cell--group")
    check("模块列按分组合并", group_cells.count() == 4, f"cells={group_cells.count()}")
    check("首组 rowspan 覆盖连续同组", group_cells.first.get_attribute("rowspan") == "11")

    nosource = page.locator("#profile .bp-row--nosource")
    check("无来源行样式", nosource.count() == 1, f"rows={nosource.count()}")
    check("无来源文案", "本期无来源" in nosource.inner_text() if nosource.count() else False)
    page.screenshot(path=str(SHOT), full_page=True)

    page.locator("#profile .bp-item", has_text="R002").locator(".bp-item__main").click()
    page.wait_for_selector("#profile .bp-row--warn")
    warn = page.locator("#profile .bp-row--warn")
    check("评分缺失醒目行", warn.count() == 1)
    check("评分缺失文案", "访谈中未给出明确评分" in warn.inner_text())
    check("切换受访者更新头部", "R002" in page.locator("#profile .bp-doc__meta").inner_text())

    page.locator("#profile .bp-item", has_text="R001").locator(".bp-item__main").click()
    page.wait_for_selector("#profile .bp-row--warn", state="detached")
    chips = page.locator("#profile .bp-chip")
    check("证据 chip 存在", chips.count() >= 1, f"chips={chips.count()}")
    chips.first.click()
    page.wait_for_selector(".bp-pop")
    pop = page.locator(".bp-pop")
    check("证据浮层显示原话", "原话" in pop.inner_text())
    page.mouse.click(5, 5)

    page.fill("#profile .bp-quote__input", "空间")
    page.locator("#profile .bp-quote__form .bp-btn").click()
    page.wait_for_selector("#profile .bp-quote__item")
    check("找原话结果", page.locator("#profile .bp-quote__item").count() == 2)
    check("命中关键词高亮", page.locator("#profile .bp-quote mark").count() >= 2)

    page.fill("#profile .bp-search", "R003")
    page.wait_for_function("document.querySelectorAll('#profile .bp-item').length === 1")
    check("搜索过滤", page.locator("#profile .bp-item").count() == 1)
    page.locator("#profile .bp-item .bp-item__main").click()
    page.wait_for_selector("#profile .bp-empty")
    check("未生成档案空态", "尚未生成档案" in page.locator("#profile .bp-doc__body").inner_text())

    export_btn = page.locator("#profile .bp-actions .bp-btn").nth(2)
    check("未勾选时导出禁用", export_btn.is_disabled())
    page.locator("#profile .bp-item input[type=checkbox]").check()
    check("勾选后可导出", not export_btn.is_disabled())

    page.fill("#profile .bp-search", "")
    page.wait_for_function("document.querySelectorAll('#profile .bp-item').length === 3")
    page.locator("#profile .bp-actions .bp-btn").first.click()
    page.wait_for_selector("#profile .bp-run:not([hidden])")
    page.wait_for_function(
        "() => { const a = document.querySelector('#profile .bp-alert'); return a && a.textContent.indexOf('归档完成') >= 0; }",
        timeout=10000,
    )
    check("生成轮询完成提示", "归档完成" in page.locator("#profile .bp-alert").inner_text())

    page.screenshot(path=str(SHOT.with_name("profile-run.png")), full_page=True)


if __name__ == "__main__":
    sys.exit(main())
