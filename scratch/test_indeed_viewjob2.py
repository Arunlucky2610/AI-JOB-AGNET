import asyncio
from playwright.async_api import async_playwright
from backend.platform_agent import user_browser_session, release_browser
from backend.indeed import apply_state_settled, STATE_JS

async def test_view2():
    user_id = 'ccf6395d-e103-4df4-bcdd-32c81a846158'
    session = await user_browser_session(user_id)
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(session['connectUrl'])
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        
        test_url = "https://in.indeed.com/viewjob?jk=471e3bc84cc92b81"
        print("Visiting:", test_url)
        await page.goto(test_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        
        title = await page.title()
        print("Page title:", title)
        
        state_raw = await page.evaluate(STATE_JS)
        print("State raw:", state_raw)
        
        verdict = await apply_state_settled(page)
        print("Verdict:", verdict)
        await browser.close()
    await release_browser(session['id'])

asyncio.run(test_view2())
