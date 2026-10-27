from playwright.sync_api import sync_playwright
import sys

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1100})
    page = context.new_page()
    msgs = []
    page.on("console", lambda m: msgs.append(f"[{m.type}] {m.text}"))
    page.on("pageerror", lambda e: msgs.append(f"[pageerror] {e}"))
    try:
        page.goto("http://127.0.0.1:7860/reputation-detail", wait_until="networkidle", timeout=30000)
    except Exception as e:
        print(f"goto error: {e}", flush=True)
    page.wait_for_timeout(2500)
    page.screenshot(path="E:/AI/data/envs/helloagent/myproject/screenshots/reputation_with_insight.png", full_page=True)

    # Inspect the table
    rows = page.evaluate("""() => {
        const tbl = document.querySelector('.review-table');
        if (!tbl) return {error: 'no table'};
        const ths = Array.from(tbl.querySelectorAll('thead th')).map(t => t.textContent.trim());
        const btns = Array.from(tbl.querySelectorAll('button.insight-btn'));
        const disabled = btns.filter(b => b.disabled).length;
        const enabled = btns.length - disabled;
        const firstFew = Array.from(tbl.querySelectorAll('tbody tr')).slice(0, 8).map(r => {
            const tds = r.querySelectorAll('td');
            return Array.from(tds).map(t => t.textContent.trim().slice(0, 50));
        });
        const modelLinks = tbl.querySelectorAll('a.model-link').length;
        return {ths, btnTotal: btns.length, btnEnabled: enabled, btnDisabled: disabled, modelLinks, firstFew};
    }""")
    print("TABLE INFO:", flush=True)
    print(rows, flush=True)
    print("CONSOLE:", flush=True)
    for m in msgs[:30]:
        print(" ", m, flush=True)
    browser.close()