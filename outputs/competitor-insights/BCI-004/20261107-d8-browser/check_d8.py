"""D8 浏览器验收：真实 7861 服务 + 真实库 + 已落库 10 份档案。

断言：63 人列表、单人 43 维、8 个无来源维、评分缺失/有分数、找原话、多人导出 xlsx、
模板切换。截图与日志落在同目录。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:7861"
OUT = Path(__file__).resolve().parent
RESULTS: list[tuple[bool, str]] = []
CONSOLE_ERRORS: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    RESULTS.append((ok, label))
    print(("PASS" if ok else "FAIL") + " | " + label + (" | " + detail if detail else ""))


def choose(page, group: str, value: str) -> None:
    page.click(f".bci-select[data-bci-group='{group}'] .bci-select__btn")
    page.click(f".bci-select[data-bci-group='{group}'] input[value='{value}']")
    page.wait_for_timeout(250)


def search(page, keyword: str) -> None:
    box = page.locator("[data-bci-profile] .bp-search")
    box.fill(keyword)
    page.wait_for_timeout(600)


def wait_item(page, code: str) -> None:
    page.wait_for_function(
        "(code) => { const items = [...document.querySelectorAll('[data-bci-profile] .bp-item')];"
        " return items.length === 1 && items[0].innerText.includes(code); }",
        arg=code,
        timeout=15000,
    )


def open_person(page, code: str) -> None:
    search(page, code)
    wait_item(page, code)
    page.click("[data-bci-profile] .bp-item__main")
    page.wait_for_function(
        "(code) => (document.querySelector('[data-bci-profile] .bp-doc__meta') || {})"
        ".textContent.includes(code)",
        arg=code,
        timeout=20000,
    )
    page.wait_for_selector("[data-bci-profile] .bp-table tbody tr", timeout=15000)


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 1080})
    page.on("pageerror", lambda exc: CONSOLE_ERRORS.append(str(exc)))
    page.goto(BASE + "/#bci", wait_until="domcontentloaded")
    page.click("a.nav-item[data-view='bci']")
    page.wait_for_selector(".view[data-view='bci']", state="visible")

    # ① 选数据源与模板（模板清单异步加载）
    page.wait_for_selector(
        ".bci-select[data-bci-group='insight_template'] input[value='user_insight_archive']",
        state="attached",
        timeout=15000,
    )
    choose(page, "interview_parsed", "2025")
    choose(page, "insight_template", "user_insight_archive")

    # ② 切到 tab ②
    page.click("[data-bci-tab='profile']")
    page.wait_for_selector("[data-bci-profile] .bp-item", timeout=20000)
    page.wait_for_function(
        "document.querySelectorAll('[data-bci-profile] .bp-item').length === 63",
        timeout=20000,
    )
    check(True, "真实 63 人列表", str(page.locator("[data-bci-profile] .bp-item").count()))

    # ③ 单人查看 R003
    open_person(page, "R003")
    rows = page.locator("[data-bci-profile] .bp-table tbody tr").count()
    check(rows == 43, "R003 单人 43 维", str(rows))
    nosource = page.locator("[data-bci-profile] tr.bp-row--nosource")
    count = nosource.count()
    check(count == 8, "8 个无来源维如实显示", str(count))
    texts = nosource.all_inner_texts()
    check(all("本期无来源" in t for t in texts), "无来源行均带「本期无来源」")
    check(all(len(t.split("本期无来源")[-1].strip()) > 0 for t in texts), "无来源行均带原因")
    page.screenshot(path=str(OUT / "profile-r003.png"), full_page=True)

    # ④ 评分：R010 有 9 分，R003 明确未给出
    open_person(page, "R010")
    score_row = page.locator("[data-bci-profile] .bp-table tbody tr", has_text="满意度评分")
    score_text = score_row.inner_text()
    check("9" in score_text and "分" in score_text, "有评分样本显示 9 分", score_text.replace("\n", " ")[:80])
    page.screenshot(path=str(OUT / "profile-r010.png"), full_page=True)

    open_person(page, "R003")
    warn_row = page.locator("[data-bci-profile] tr.bp-row--warn")
    check(warn_row.count() == 1, "评分缺失行使用醒目样式", str(warn_row.count()))
    check(
        "未给出明确评分" in warn_row.inner_text(),
        "评分缺失写明原因",
        warn_row.inner_text().replace("\n", " ")[:80],
    )

    # ⑤ 找原话（R003）
    page.fill("[data-bci-profile] .bp-quote__input", "车")
    page.click("[data-bci-profile] .bp-quote__form .bp-btn")
    page.wait_for_selector("[data-bci-profile] .bp-quote__item", timeout=15000)
    quotes = page.locator("[data-bci-profile] .bp-quote__item").count()
    check(quotes > 0, "找原话返回结果", str(quotes))
    page.screenshot(path=str(OUT / "profile-quote.png"), full_page=True)

    # ⑥ 勾选 R003 + R046 并导出 xlsx
    search(page, "R003")
    wait_item(page, "R003")
    page.check("[data-bci-profile] .bp-item input[type='checkbox']")
    search(page, "R046")
    wait_item(page, "R046")
    page.check("[data-bci-profile] .bp-item input[type='checkbox']")
    button = page.locator("[data-bci-profile] .bp-actions .bp-btn--primary")
    check("已勾选 2 人" in button.inner_text(), "导出按钮反映勾选人数", button.inner_text())
    with page.expect_download(timeout=60000) as info:
        button.click()
    download = info.value
    target = OUT / "pilot-export.xlsx"
    download.save_as(target)
    check(target.is_file() and target.stat().st_size > 1000, "浏览器下载 xlsx", f"{target.stat().st_size} bytes")
    workbook = load_workbook(target, read_only=True)
    check(len(workbook.sheetnames) == 3, "xlsx 含 3 个 Sheet", "、".join(workbook.sheetnames))
    archive_sheet = workbook[workbook.sheetnames[0]]
    header = [
        str(cell.value)
        for row in archive_sheet.iter_rows(min_row=1, max_row=2)
        for cell in row
        if cell.value is not None
    ]
    check(
        any("R003" in v for v in header) and any("R046" in v for v in header),
        "xlsx 主表含两名受访者列",
        "、".join(header[:4]),
    )
    check(archive_sheet.max_row == 45, "xlsx 主表 43 行维度", str(archive_sheet.max_row))
    meta_sheet = workbook[workbook.sheetnames[1]]
    meta = [
        str(cell.value)
        for row in meta_sheet.iter_rows(min_row=1, max_row=5)
        for cell in row
        if cell.value is not None
    ]
    check("2" in meta, "xlsx 口径页记录导出人数 2", "、".join(meta[:6]))
    evidence_sheet = workbook[workbook.sheetnames[2]]
    people = {
        str(row[0])
        for row in evidence_sheet.iter_rows(min_row=2, values_only=True)
        if row and row[0]
    }
    check({"R003", "R046"} <= people, "xlsx 证据页含两名受访者", "、".join(sorted(people)))
    workbook.close()

    # ⑦ 模板切换
    page.click("[data-bci-tab='datasource']")
    choose(page, "insight_template", "nev_user_insight")
    page.click("[data-bci-tab='profile']")
    page.wait_for_function(
        "document.querySelector('[data-bci-profile] .bp-scope__template')"
        ".textContent.includes('新能源')",
        timeout=20000,
    )
    page.wait_for_selector("[data-bci-profile] .bp-item", timeout=20000)
    check(True, "模板切换后重新加载", page.locator("[data-bci-profile] .bp-scope__template").inner_text())
    page.screenshot(path=str(OUT / "profile-template-switch.png"), full_page=True)

    check(not CONSOLE_ERRORS, "页面无 JS 错误", "；".join(CONSOLE_ERRORS[:3]))
    browser.close()

failed = [label for ok, label in RESULTS if not ok]
print(f"\n合计 {len(RESULTS)} 项，通过 {len(RESULTS) - len(failed)}，失败 {len(failed)}")
if failed:
    print("失败项：" + "、".join(failed))
sys.exit(1 if failed else 0)
