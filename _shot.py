import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={'width': 1440, 'height': 900})
        page = await context.new_page()
        await page.goto('http://127.0.0.1:7860/', wait_until='networkidle', timeout=15000)
        await page.wait_for_timeout(3000)
        await page.evaluate('document.fonts.ready')
        await page.wait_for_timeout(2000)
        await page.screenshot(path='E:/AI/data/envs/helloagent/screenshots/koubei_card.png', full_page=False)
        # Scroll to WOM card
        await page.evaluate("document.querySelector('[data-domain=wom]').scrollIntoView({behavior: 'smooth', block: 'center'})")
        await page.wait_for_timeout(1000)
        await page.screenshot(path='E:/AI/data/envs/helloagent/screenshots/koubei_card_closeup.png', full_page=False)
        await browser.close()
        print('Done')

asyncio.run(test())
