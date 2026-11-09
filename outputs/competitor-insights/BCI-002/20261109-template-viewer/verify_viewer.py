"""BCI-002 增强验收：「查看模板」只读弹窗。

前提：7860 已加载最新 home.html（app.py 启动时读入内存）。
运行（项目根目录）：
    ../Scripts/python.exe -B outputs/competitor-insights/BCI-002/20261109-template-viewer/verify_viewer.py

产出：本目录 screenshots/*.png 与 stdout；退出码 0 = 全部断言通过。只读页面。
断言模板内容时以 competitor_insight/templates/*.json 原文件为唯一真值。
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:7860"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SHOT = HERE / "screenshots"
SHOT.mkdir(parents=True, exist_ok=True)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (" | " + str(detail) if detail else ""))


neV = json.loads((ROOT / "competitor_insight/templates/nev_user_insight_template.json").read_text(encoding="utf-8"))
archive = json.loads((ROOT / "competitor_insight/templates/user_insight_archive_template.json").read_text(encoding="utf-8"))
manifest = json.loads((ROOT / "competitor_insight/web/templates.json").read_text(encoding="utf-8"))
templates = manifest["templates"]

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("try { localStorage.removeItem('bci.scope'); } catch (e) {}")
    page = context.new_page()
    console_errors = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append("PAGEERROR " + str(e)))

    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_function("() => window.Home && typeof window.Home === 'object'", timeout=15000)
    page.wait_for_timeout(600)
    nav = page.locator("a.nav-item[data-view='bci']")
    nav.click()
    for _ in range(10):
        if not page.evaluate("() => document.querySelector(\".view[data-view='bci']\").hidden"):
            break
        page.wait_for_timeout(300)
        nav.click()
    page.wait_for_timeout(600)

    block = page.locator("#bci-groups .bci-block").filter(has_text="深访用户洞察档案模板")
    trigger = block.locator("[data-bci-template-view]")
    check("模板块右侧有「查看模板」入口", trigger.count() == 1 and trigger.is_visible(),
          trigger.inner_text() if trigger.count() else "0")
    check("入口只出现在模板块（其他三类无入口）",
          page.locator("[data-bci-template-view]").count() == 1,
          page.locator("[data-bci-template-view]").count())

    select_value_before = block.locator(".bci-select__value").inner_text().strip()
    scope_before = page.evaluate("() => localStorage.getItem('bci.scope')")

    trigger.click()
    page.wait_for_selector(".bci-tpl-item", timeout=10000)
    modal = page.locator("[data-bci-template-modal]")
    check("弹窗打开且为 dialog", modal.is_visible() and
          modal.locator("[role='dialog']").count() == 1)
    check("弹窗可关闭（关闭按钮存在）", modal.locator(".bci-modal__close").count() == 1)

    items = page.locator(".bci-tpl-item")
    check("模板清单条数与 templates.json 一致", items.count() == len(templates),
          [items.count(), len(templates)])
    labels = page.eval_on_selector_all(".bci-tpl-item__name", "e => e.map(x => x.textContent.trim())")
    check("清单含全部模板名称", [t["label"] for t in templates] == labels, labels)

    page.wait_for_selector(".bci-tpl-table", timeout=10000)
    first_id = templates[0]["id"]
    expect = neV if first_id == "nev_user_insight" else archive
    head_meta = page.locator(".bci-tpl-head__meta").inner_text()
    check("默认详情组数/维度数与 JSON 一致",
          ("%d 组" % len(expect["groups"])) in head_meta and ("%d 维" % len(expect["dimensions"])) in head_meta,
          head_meta)
    check("详情维度行数与 JSON 一致",
          page.locator(".bci-tpl-table tbody tr").count() == len(expect["dimensions"]),
          [page.locator(".bci-tpl-table tbody tr").count(), len(expect["dimensions"])])
    group_names = page.eval_on_selector_all(".bci-tpl-group__head b", "e => e.map(x => x.textContent.trim())")
    check("分组名称与 JSON 一致",
          group_names == [g["name"] for g in expect["groups"]], group_names)
    check("每维展示必填/类型/说明",
          page.locator(".bci-tpl-table tbody tr td").count() == len(expect["dimensions"]) * 5,
          page.locator(".bci-tpl-table tbody tr td").count())
    page.screenshot(path=str(SHOT / "modal-ready.png"), full_page=False)

    search = page.locator("[data-bci-tpl-search]")
    search.fill("新车型")
    page.wait_for_timeout(200)
    check("按名称筛选生效", page.locator(".bci-tpl-item").count() == 1 and
          "新车型" in page.locator(".bci-tpl-item__name").inner_text(),
          page.locator(".bci-tpl-item__name").inner_text())
    search.fill("")
    page.wait_for_timeout(150)

    page.locator("[data-bci-tpl-status]").select_option("pending")
    page.wait_for_timeout(200)
    pending_items = page.locator(".bci-tpl-item")
    check("按状态筛选只留待提供模板", pending_items.count() == 1,
          [pending_items.count(), pending_items.inner_text() if pending_items.count() else ""])
    pending_items.first.click()
    page.wait_for_timeout(300)
    check("待提供模板给出状态与原因", page.locator(".bci-tpl-pending").count() == 1 and
          page.locator(".bci-tpl-pending .bci-tpl-badge--pending").count() == 1,
          page.locator(".bci-tpl-pending p").inner_text() if page.locator(".bci-tpl-pending p").count() else "")
    check("待提供模板不渲染空内容页", page.locator(".bci-tpl-group").count() == 0)
    page.screenshot(path=str(SHOT / "modal-pending.png"), full_page=False)

    page.locator("[data-bci-tpl-status]").select_option("ready")
    page.wait_for_timeout(200)
    check("按状态筛选已就绪为 2 套", page.locator(".bci-tpl-item").count() == 2,
          page.locator(".bci-tpl-item").count())

    page.locator(".bci-tpl-item").nth(1).click()
    page.wait_for_timeout(400)
    second = [t for t in templates if t["status"] == "ready"][1]
    expect2 = neV if second["id"] == "nev_user_insight" else archive
    check("切换模板后内容跟随", page.locator(".bci-tpl-head__row h4").inner_text().strip() ==
          (expect2.get("name") or second["label"]),
          page.locator(".bci-tpl-head__row h4").inner_text())

    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    check("Esc 可关闭弹窗", not modal.is_visible())
    check("关闭后下拉已选值不变",
          block.locator(".bci-select__value").inner_text().strip() == select_value_before,
          select_value_before)
    check("弹窗未写入 bci.scope", page.evaluate("() => localStorage.getItem('bci.scope')") == scope_before)

    trigger.click()
    page.wait_for_selector("[data-bci-template-modal]", timeout=5000)
    page.locator(".bci-modal__mask").click(position={"x": 12, "y": 12})
    page.wait_for_timeout(250)
    check("点遮罩可关闭", not modal.is_visible())
    page.screenshot(path=str(SHOT / "tab1-after.png"), full_page=False)

    real_errors = [e for e in console_errors if "favicon" not in e.lower() and "404" not in e]
    check("无 JS 运行时错误", not real_errors, real_errors[:3])

    browser.close()

passed = sum(1 for _, ok, _ in results if ok)
print("\n%d/%d PASS" % (passed, len(results)))
raise SystemExit(0 if passed == len(results) else 1)
