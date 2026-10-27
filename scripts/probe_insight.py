from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    msgs = []
    page.on("console", lambda m: msgs.append(f"[{m.type}] {m.text}"))
    page.on("pageerror", lambda e: msgs.append(f"[pageerror] {e}"))
    # 直接访问新页面
    page.goto("http://127.0.0.1:7860/reputation-insight?model=" + "理想i8", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3500)
    info = page.evaluate("""() => {
        const rep = document.querySelector('#reputationContent');
        const repText = (rep ? rep.textContent : '').slice(0, 200);
        const treeEl = document.querySelector('#kbTree');
        const treeText = (treeEl ? treeEl.textContent : '').slice(0, 200);
        const paneEl = document.querySelector('#kbReviewPane');
        const paneText = (paneEl ? paneEl.textContent : '').slice(0, 200);
        const tags = document.querySelectorAll('.kb-tree-tag').length;
        const title = document.querySelector('#title')?.textContent.trim();
        return {repText, treeText, paneText, tags, title};
    }""")
    print("DIRECT VIEW:", info, flush=True)
    print("CONSOLE:", flush=True)
    for m in msgs[:15]: print(" ", m, flush=True)
    page.screenshot(path="E:/AI/data/envs/helloagent/myproject/screenshots/reputation_insight_direct.png", full_page=True)

    # 然后从 reputation-detail 跳
    page.goto("http://127.0.0.1:7860/reputation-detail", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2500)
    btn = page.locator("button.insight-btn").first
    print("FIRST BTN text:", btn.text_content(), flush=True)
    btn.click()
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_timeout(3500)
    print("URL AFTER CLICK:", page.url, flush=True)
    info2 = page.evaluate("""() => {
        const rep = document.querySelector('#reputationContent');
        return {repText: (rep ? rep.textContent : '').slice(0, 200), title: document.querySelector('#title')?.textContent.trim()};
    }""")
    print("AFTER JUMP:", info2, flush=True)
    page.screenshot(path="E:/AI/data/envs/helloagent/myproject/screenshots/reputation_insight_jump.png", full_page=True)
    browser.close()