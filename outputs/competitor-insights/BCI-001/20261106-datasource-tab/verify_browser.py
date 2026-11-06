"""BCI-001 浏览器级验收：竞品洞察 → 数据源筛选。

前置：7860 已加载最新 home.html（app.py 启动时读入内存）且
`POST /api/bci/datasource/availability` 可用。

运行（项目根目录）：
    ../Scripts/python.exe -B outputs/competitor-insights/BCI-001/20261106-datasource-tab/verify_browser.py

产出：本目录 screenshots/*.png；退出码 0 表示全部断言通过。
只读页面，不修改业务数据。
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:7860"
HERE = Path(__file__).resolve().parent
SHOT = HERE / "screenshots"
SHOT.mkdir(parents=True, exist_ok=True)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail) if detail else ""))


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 980})
    errors = []
    bad_urls = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append("PAGEERROR " + str(e)))
    page.on("response", lambda r: bad_urls.append(r.url) if r.status == 404 else None)

    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)

    nav = page.locator("a.nav-item[data-view='bci']")
    check("左导航存在「竞品洞察」", nav.count() == 1, nav.inner_text() if nav.count() else "not found")
    nav.click()
    page.wait_for_timeout(1500)

    view = page.locator(".view[data-view='bci']")
    check("竞品洞察视图可见", view.is_visible())

    tabs = page.locator(".bci-tab")
    check("4 个 tab", tabs.count() == 4, [tabs.nth(i).inner_text().replace("\n", " ") for i in range(tabs.count())])
    check("仅第 1 个 tab 可点", tabs.nth(0).is_enabled() and not tabs.nth(1).is_enabled())

    page.wait_for_selector("#bci-sources .bci-source", timeout=15000)
    cards = page.locator("#bci-sources .bci-source")
    check("5 张数据源卡片", cards.count() == 5, cards.count())

    statuses = page.eval_on_selector_all(
        "#bci-sources .bci-source",
        "els => els.map(e => e.className.replace('bci-source ', '') + '::' + e.querySelector('.bci-source__name').textContent + '::' + e.querySelector('.bci-badge').textContent.trim())",
    )
    print("  状态:", json.dumps(statuses, ensure_ascii=False))

    chips = page.locator("#bci-chips-target .bci-chip")
    check("本品 5 个 chip", chips.count() == 5, chips.count())
    check("本品无任何数据的车型标 is-empty",
          page.locator("#bci-chips-target .bci-chip.is-empty").count() == 4,
          page.locator("#bci-chips-target .bci-chip.is-empty").count())

    rows = page.locator("#bci-matrix tbody tr")
    check("可用性矩阵 5 行", rows.count() == 5, rows.count())
    cells = page.locator("#bci-matrix tbody tr:first-child td .bci-cell")
    check("矩阵首行 5 列", cells.count() == 5, [cells.nth(i).inner_text() for i in range(cells.count())])

    alert = page.locator("#bci-alert")
    check("空样本告警可见", alert.is_visible(), alert.inner_text()[:120].replace("\n", " "))

    rules = page.locator("#bci-contract .bci-rule")
    check("下游参数契约 7 条", rules.count() == 7, rules.count())
    comp_rule = page.locator("#bci-contract .bci-rule").nth(4)
    check("competitor_compare 标记「选择不生效」", "选择不生效" in comp_rule.inner_text(), comp_rule.inner_text().replace("\n", " ")[:80])

    page.screenshot(path=str(SHOT / "bci-datasource-default.png"), full_page=True)

    # 切到唯一有定量样本的车型
    page.locator("#bci-chips-target .bci-chip", has_text="小鹏M03").click()
    page.wait_for_timeout(600)
    q_rule = page.locator("#bci-contract .bci-rule").first
    check("切到小鹏M03 后定量规则生效", "生效" in q_rule.inner_text(), q_rule.inner_text().replace("\n", " ")[:100])
    check("切换本品后告警按新集合重算", "3 台" in alert.inner_text(), alert.inner_text().split("\n")[0])

    # 应用口径
    page.locator("#bci-apply").click()
    page.wait_for_timeout(400)
    scope = page.evaluate("() => localStorage.getItem('bci.scope')")
    check("应用后写入 bci.scope", bool(scope) and "小鹏M03" in (scope or ""), (scope or "")[:120])
    check("头部口径回显", "小鹏M03" in page.locator("#bci-scope-text").inner_text(), page.locator("#bci-scope-text").inner_text())

    page.screenshot(path=str(SHOT / "bci-datasource-applied.png"), full_page=True)

    # 恢复默认
    page.locator("#bci-reset").click()
    page.wait_for_timeout(400)
    check("恢复默认清空存储", page.evaluate("() => localStorage.getItem('bci.scope')") is None)
    check("恢复后本品回到埃安RT", "埃安RT" in page.locator("#bci-scope-text").inner_text(), page.locator("#bci-scope-text").inner_text())

    check("无 JS 运行时错误", len([e for e in errors if "Failed to load resource" not in e]) == 0, errors[:4])
    print("  404 资源:", bad_urls[:6])

    browser.close()

failed = [r for r in results if not r[1]]
print("\n===== 汇总: %d/%d PASS =====" % (len(results) - len(failed), len(results)))
sys.exit(1 if failed else 0)
