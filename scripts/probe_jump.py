from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.goto("http://127.0.0.1:7860/reputation-detail", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    # Click the first insight button (五菱扬光L)
    btn = page.locator("button.insight-btn").first
    print("button text:", btn.text_content(), flush=True)
    btn.click()
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_timeout(2500)
    print("URL after click:", page.url, flush=True)
    # Verify the reputation section is in viewport
    rect = page.evaluate("""() => {
        const el = document.querySelector('#reputation');
        if (!el) return {error: 'no #reputation'};
        const r = el.getBoundingClientRect();
        const topbarH = document.querySelector('.topbar')?.getBoundingClientRect().height ?? 0;
        return {top: r.top, height: r.height, bottom: r.bottom, topbarH, inViewport: r.top >= -10 && r.top < window.innerHeight};
    }""")
    print("REP SECTION:", rect, flush=True)
    # Check that reputation content has loaded
    rep_text = page.locator("#reputationContent").text_content()
    print("REP TEXT (first 200):", (rep_text or "")[:200], flush=True)
    page.screenshot(path="E:/AI/data/envs/helloagent/myproject/screenshots/reputation_jump_target.png", full_page=False)
    page.screenshot(path="E:/AI/data/envs/helloagent/myproject/screenshots/reputation_jump_full.png", full_page=True)
    browser.close()