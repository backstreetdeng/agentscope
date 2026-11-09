"""BCI-001（口径纠正后）浏览器级验收：竞品洞察 → 数据源筛选 = 四类选择器。

前提：7860 已加载最新 home.html（app.py 启动时读入内存）。
运行（项目根目录）：
    ../Scripts/python.exe -B outputs/competitor-insights/BCI-001/20261106-datasource-selector-r2/verify_selector.py

产出：本目录 screenshots/*.png 与 stdout；退出码 0 = 全部断言通过。只读页面。
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
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    # 每次运行前清掉上次口径，保证从「全部不选」的默认态开始。
    context.add_init_script("try { localStorage.removeItem('bci.scope'); } catch (e) {}")
    page = context.new_page()
    console_errors = []
    bad_urls = []
    asset_status = {}
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append("PAGEERROR " + str(e)))

    def on_response(resp):
        if resp.status == 404:
            bad_urls.append(resp.url)
        if "templates.json" in resp.url:
            asset_status["templates"] = resp.status

    page.on("response", on_response)

    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(900)

    nav = page.locator("a.nav-item[data-view='bci']")
    check("左导航存在「竞品洞察」", nav.count() == 1)
    # 首页初始化是异步的，等 Home 挂载后再点，必要时重试一次。
    page.wait_for_function("() => window.Home && typeof window.Home === 'object'", timeout=15000)
    page.wait_for_timeout(600)
    nav.click()
    for _ in range(10):
        if not page.evaluate("() => document.querySelector(\".view[data-view='bci']\").hidden"):
            break
        page.wait_for_timeout(300)
        nav.click()
    page.wait_for_timeout(600)

    check("视图可见", page.locator(".view[data-view='bci']").is_visible())
    tabs = page.locator(".bci-tab")
    check("4 个 tab：①②③ 可点、④ 未开发不可点",
          tabs.count() == 4 and tabs.nth(0).is_enabled() and tabs.nth(1).is_enabled()
          and tabs.nth(2).is_enabled() and not tabs.nth(3).is_enabled(),
          [tabs.nth(i).is_enabled() for i in range(tabs.count())])

    # 2026-11-09 既有问题修复：前端探活 /api/health 原先无路由，控制台持续刷 404。
    health = page.request.get(BASE + "/api/health")
    try:
        health_body = health.json()
    except Exception:
        health_body = {}
    check("探活接口 /api/health 返回 200 且 status=ok",
          health.status == 200 and health_body.get("status") == "ok" and bool(health_body.get("service")),
          {"status": health.status, "body": health_body})

    groups = page.locator("#bci-groups .bci-block")
    check("四类数据源分组", groups.count() == 4, groups.count())
    check("控制台不再出现 /api/health 404",
          not any("/api/health" in u for u in bad_urls), bad_urls)
    titles = page.eval_on_selector_all("#bci-groups .bci-block__title", "e => e.map(x => x.textContent.trim())")
    print("  分组:", json.dumps(titles, ensure_ascii=False))
    check("分组标题与业务口径一致",
          [t.replace("1", "").replace("2", "").replace("3", "").replace("4", "") for t in titles] ==
          ["定量结构化数据", "定性深访解析数据", "深访用户洞察档案模板", "流通数据（增换购流转分析）"])

    selects = page.locator("#bci-groups .bci-select")
    check("每类一个下拉", selects.count() == 4, selects.count())
    values = page.eval_on_selector_all("#bci-groups .bci-select__value", "e => e.map(x => x.textContent.trim())")
    check("默认全部「不选」", values == ["不选"] * 4, values)

    scope = page.evaluate("() => JSON.parse(localStorage.getItem('bci.scope') || 'null')")
    check("默认不写入作用域", scope is None)
    check("顶部口径显示全部不选", page.locator("#bci-scope-text").inner_text().strip() == "全部不选",
          page.locator("#bci-scope-text").inner_text())
    # 2026-11-09 越界修复：选源阶段不得出现「本次分析口径」与「报告输出」两块。
    out_of_scope = page.evaluate("""() => ({
        preview: document.querySelectorAll('#bci-scope-preview').length,
        status: document.querySelectorAll('#bci-scope-status').length,
        scopeBlock: document.querySelectorAll('.bci-block--scope').length,
        soon: document.querySelectorAll('.bci-soon').length,
        reportPanel: document.querySelectorAll("[data-bci-panel='report']").length })""")
    check("选源阶段无「本次分析口径」块",
          out_of_scope["preview"] == 0 and out_of_scope["status"] == 0 and out_of_scope["scopeBlock"] == 0,
          out_of_scope)
    check("选源阶段无「报告输出」占位",
          out_of_scope["soon"] == 0 and out_of_scope["reportPanel"] == 0, out_of_scope)
    visible_panels = page.eval_on_selector_all(
        "[data-bci-panel]",
        "els => els.filter(e => getComputedStyle(e).display !== 'none').map(e => e.dataset.bciPanel)")
    check("可见 tab 面板只有数据源筛选", visible_panels == ["datasource"], visible_panels)

    # —— 定量：多选 ——
    q_box = page.locator(".bci-select[data-bci-group='quant_structured']")
    q_box.locator(".bci-select__btn").click()
    check("下拉可展开", q_box.locator(".bci-select__panel").is_visible())
    page.screenshot(path=str(SHOT / "bci-selector-open.png"), full_page=True)
    year_inputs = q_box.locator("input")
    check("定量三年可多选（checkbox）", year_inputs.count() == 3 and
          all(year_inputs.nth(i).get_attribute("type") == "checkbox" for i in range(3)), year_inputs.count())
    year_inputs.nth(0).check()
    year_inputs.nth(2).check()
    page.wait_for_timeout(250)
    check("多选回显 2023、2025", q_box.locator(".bci-select__value").inner_text().strip() == "2023、2025",
          q_box.locator(".bci-select__value").inner_text())
    scope = page.evaluate("() => JSON.parse(localStorage.getItem('bci.scope'))")
    check("定量写入 quant_structured", scope["datasources"]["quant_structured"] == ["2023", "2025"],
          scope["datasources"]["quant_structured"])

    # —— 定性：单选 + 2026 不可选 ——
    page.keyboard.press("Escape")  # 收起上一组下拉，避免浮层覆盖下一个按钮
    i_box = page.locator(".bci-select[data-bci-group='interview_parsed']")
    i_box.locator(".bci-select__btn").click()
    opts = i_box.locator(".bci-option")
    check("定性含「不选」+ 两个年度", opts.count() == 3, opts.count())
    opt_2026 = i_box.locator(".bci-option[data-bci-value='2026']")
    check("2026 年不可选", opt_2026.locator("input").is_disabled())
    check("2026 年给出原因", "尚未转写解析" in opt_2026.inner_text(), opt_2026.inner_text().replace("\n", " "))
    i_box.locator(".bci-option[data-bci-value='2025'] input").check()
    page.wait_for_timeout(250)
    scope = page.evaluate("() => JSON.parse(localStorage.getItem('bci.scope'))")
    check("定性写入 interview_parsed", scope["datasources"]["interview_parsed"] == "2025",
          scope["datasources"]["interview_parsed"])

    # —— 模板：新能源可选，新车型待业务提供 ——
    page.keyboard.press("Escape")
    t_box = page.locator(".bci-select[data-bci-group='insight_template']")
    t_box.locator(".bci-select__btn").click()
    t_opts = t_box.locator(".bci-option")
    disabled = t_box.locator(".bci-option.is-disabled").count()
    check("模板清单含「不选」+ 三套模板", t_opts.count() == 4, t_opts.count())
    check("仅新车型不可选", disabled == 1, f"options={t_opts.count()} disabled={disabled}")
    check("模板清单经 templates.json 提供", asset_status.get("templates") == 200, asset_status)
    nev = t_box.locator(".bci-option[data-bci-value='nev_user_insight']")
    check("新能源模板可选", nev.locator("input").is_disabled() is False)
    check("新能源模板标注 v1 与维度数", "v1" in nev.inner_text() and "43" in nev.inner_text(),
          nev.inner_text().replace("\n", " "))
    newcar = t_box.locator(".bci-option[data-bci-value='new_model_user_insight']")
    check("新车型模板不可选", newcar.locator("input").is_disabled())
    check("新车型原因写明待业务提供", "业务提供" in newcar.inner_text(), newcar.inner_text().replace("\n", " "))
    nev.locator("input").check()
    page.wait_for_timeout(250)
    scope = page.evaluate("() => JSON.parse(localStorage.getItem('bci.scope'))")
    check("模板写入 insight_template", scope["datasources"]["insight_template"] == "nev_user_insight",
          scope["datasources"]["insight_template"])

    # —— 流通：待业务提供 ——
    page.keyboard.press("Escape")
    f_box = page.locator(".bci-select[data-bci-group='flow_data']")
    f_box.locator(".bci-select__btn").click()
    check("流通数据不可选并说明原因",
          f_box.locator(".bci-option.is-disabled").count() == 1 and "业务数据尚未提供" in f_box.inner_text(),
          f_box.inner_text().replace("\n", " ")[:80])

    # 关闭：点击下拉以外的区域（页面顶部标题，不会被浮层覆盖）
    page.locator(".bci-hero__title").click()
    page.wait_for_timeout(200)
    check("点击外部收起下拉", f_box.locator(".bci-select__panel").is_hidden())

    header = page.locator("#bci-scope-text").inner_text()
    check("顶部口径汇总已选 3 类", "已选 3 类" in header, header)
    page.screenshot(path=str(SHOT / "bci-selector-selected.png"), full_page=True)

    # —— 清空 ——
    page.locator("#bci-reset").click()
    page.wait_for_timeout(300)
    check("清空后回到全部不选",
          page.eval_on_selector_all("#bci-groups .bci-select__value", "e => e.map(x => x.textContent.trim())") == ["不选"] * 4)
    check("清空后存储移除", page.evaluate("() => localStorage.getItem('bci.scope')") is None)
    check("清空后口径回显", page.locator("#bci-scope-text").inner_text().strip() == "全部不选")

    # —— 布局：桌面 2×2，窄屏单列 ——
    def card_boxes():
        return page.eval_on_selector_all(
            "#bci-groups .bci-block",
            """els => els.map(e => {
                const r = e.getBoundingClientRect();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
            })""")

    page.wait_for_timeout(250)
    desktop = card_boxes()
    xs = sorted({b["x"] for b in desktop})
    ys = sorted({b["y"] for b in desktop})
    check("桌面布局 2 列 × 2 行", len(xs) == 2 and len(ys) == 2, desktop)
    check("桌面四张卡片等宽等高",
          len({b["w"] for b in desktop}) == 1 and len({b["h"] for b in desktop}) == 1,
          {"widths": sorted({b["w"] for b in desktop}), "heights": sorted({b["h"] for b in desktop})})
    row_gap = ys[1] - max(b["y"] + b["h"] for b in desktop if b["y"] == ys[0])
    check("桌面行间距沿用 12px 栅格", abs(row_gap - 12) <= 1, row_gap)
    page.screenshot(path=str(SHOT / "bci-layout-desktop.png"), full_page=True)

    page.set_viewport_size({"width": 1000, "height": 1000})
    page.wait_for_timeout(400)
    narrow = card_boxes()
    check("窄屏（1000px）回落单列",
          len({b["x"] for b in narrow}) == 1 and len({b["y"] for b in narrow}) == 4, narrow)
    check("窄屏卡片宽度撑满且未被挤压",
          all(b["w"] > 500 for b in narrow), sorted({b["w"] for b in narrow}))
    page.screenshot(path=str(SHOT / "bci-layout-narrow.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.wait_for_timeout(300)

    # —— 旧实现已移除 ——
    legacy = page.evaluate("""() => ({
        chip: document.querySelectorAll('.bci-chip').length,
        matrix: document.querySelectorAll('.bci-matrix').length,
        alert: document.querySelectorAll('.bci-alert').length,
        rule: document.querySelectorAll('.bci-rule').length,
        sourceCard: document.querySelectorAll('.bci-source').length })""")
    check("5×5 可用性矩阵/车型 chip/告警/契约块已移除",
          all(v == 0 for v in legacy.values()), legacy)

    errors = [e for e in console_errors if "Failed to load resource" not in e]
    check("无 JS 运行时错误", len(errors) == 0, errors[:4])
    print("  404 资源:", bad_urls[:6])

    browser.close()

failed = [r for r in results if not r[1]]
print("\n===== 汇总: %d/%d PASS =====" % (len(results) - len(failed), len(results)))
for name, ok, detail in failed:
    print("  FAIL:", name, detail)
sys.exit(1 if failed else 0)
