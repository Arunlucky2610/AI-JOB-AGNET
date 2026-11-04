import asyncio
from playwright.async_api import async_playwright
from backend.platform_agent import user_browser_session, release_browser
from backend.indeed import apply_state_settled, STATE_JS

async def test_view():
    user_id = 'ccf6395d-e103-4df4-bcdd-32c81a846158'
    session = await user_browser_session(user_id)
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(session['connectUrl'])
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Test a viewjob URL
        test_url = "https://in.indeed.com/viewjob?jk=2d42c261d33be2b6"
        print("Visiting:", test_url)
        await page.goto(test_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        
        title = await page.title()
        print("Page title:", title)
        
        state_raw = await page.evaluate(STATE_JS)
        print("State raw:", state_raw)
        
        verdict = await apply_state_settled(page)
        print("Verdict:", verdict)
        
        # Check buttons and links on page
        buttons = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('button, a[role="button"], #indeedApplyButton, [data-testid="indeedApplyButton"]')).map(b => ({
                tag: b.tagName,
                id: b.id,
                testId: b.getAttribute('data-testid'),
                text: b.innerText,
                href: b.href
            })).filter(x => x.text && (x.text.toLowerCase().includes('apply') || x.id.includes('indeed') || (x.testId && x.testId.includes('indeed'))));
        }''')
        print("Apply buttons found:", buttons)
        await browser.close()
    await release_browser(session['id'])

asyncio.run(test_view())
