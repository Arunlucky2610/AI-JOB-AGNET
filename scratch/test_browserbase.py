import asyncio
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from backend.platform_agent import user_browser_session, release_browser

load_dotenv()

async def test_bb():
    user_id = 'ccf6395d-e103-4df4-bcdd-32c81a846158'
    print("Requesting browser session...")
    session = await user_browser_session(user_id)
    print("Session created:", session['id'], session['connectUrl'])
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(session['connectUrl'])
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        print("Navigating to in.indeed.com...")
        await page.goto("https://in.indeed.com/jobs?q=AI+Engineer&l=Hyderabad%2C+India&sort=date&fromage=7", wait_until="domcontentloaded", timeout=45000)
        title = await page.title()
        print("Page loaded successfully! Title:", title)
        from backend.indeed import collect_job_urls, card_titles
        urls = await collect_job_urls(page)
        print(f"Collected {len(urls)} job URLs:")
        titles = await card_titles(page)
        for u in urls[:5]:
            print(" -", titles.get(u, 'No title'), u)
        await browser.close()
    await release_browser(session['id'])
    print("Browser released!")

asyncio.run(test_bb())
