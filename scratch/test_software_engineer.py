import asyncio
from playwright.async_api import async_playwright
from backend.platform_agent import user_browser_session, release_browser

async def test_se():
    user_id = 'ccf6395d-e103-4df4-bcdd-32c81a846158'
    session = await user_browser_session(user_id)
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(session['connectUrl'])
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        url = "https://in.indeed.com/jobs?q=Software+Engineer&l=Hyderabad%2C+India&sort=date&fromage=7"
        print("Navigating to:", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        
        cards = await page.evaluate('''() => {
            const list = [];
            document.querySelectorAll('[data-jk]').forEach(link => {
                const jk = link.getAttribute('data-jk');
                const card = link.closest('.cardOutline, .job_seen_beacon, li') || link;
                const text = card.innerText || '';
                const title = link.querySelector('span[title]')?.getAttribute('title') || link.innerText || '';
                const hasEasilyApply = /easily apply|apply now/i.test(text);
                list.push({ jk, title: title.split('\\n')[0].trim(), hasEasilyApply });
            });
            return list;
        }''')
        print(f"Total cards for Software Engineer: {len(cards)}")
        for c in cards:
            print(f"- {c['title']} (jk={c['jk']}, EasilyApply={c['hasEasilyApply']})")
        await browser.close()
    await release_browser(session['id'])

asyncio.run(test_se())
