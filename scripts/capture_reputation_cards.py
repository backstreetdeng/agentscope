"""Capture homepage reputation cards with a separately owned Playwright browser.

Run from the project with ../Scripts/python.exe scripts/capture_reputation_cards.py.
Reads localhost:7860; writes task screenshots below outputs/reputation-card-capture.
Launches and closes only its own temporary browser, not the monthly BI browser.
"""
import asyncio
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

async def test():
    output = Path(__file__).resolve().parents[1] / 'outputs' / 'reputation-card-capture' / datetime.now().strftime('%Y%m%d-%H%M%S')
    shots = output / 'screenshots'
    shots.mkdir(parents=True, exist_ok=True)
    (output / 'README.md').write_text('Purpose: homepage reputation card capture.\nSource: http://127.0.0.1:7860/\nReproduce: ../Scripts/python.exe scripts/capture_reputation_cards.py\nRetention: reproducible; review after task acceptance and before cleanup.\n', encoding='utf-8')
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={'width': 1440, 'height': 900})
        page = await context.new_page()
        await page.goto('http://127.0.0.1:7860/', wait_until='networkidle', timeout=15000)
        await page.wait_for_timeout(3000)
        await page.evaluate('document.fonts.ready')
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(shots / 'koubei_card.png'), full_page=False)
        # Scroll to WOM card
        await page.evaluate("document.querySelector('[data-domain=wom]').scrollIntoView({behavior: 'smooth', block: 'center'})")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(shots / 'koubei_card_closeup.png'), full_page=False)
        await browser.close()
        print('Done')

if __name__ == '__main__':
    asyncio.run(test())
