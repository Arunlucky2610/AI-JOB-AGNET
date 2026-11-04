import asyncio
from playwright.async_api import async_playwright
from backend.platform_agent import user_browser_session, release_browser

async def test_cards2():
    user_id = 'ccf6395d-e103-4df4-bcdd-32c81a846158'
    session = await user_browser_session(user_id)
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(session['connectUrl'])
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://in.indeed.com/jobs?q=AI+Engineer&l=Hyderabad%2C+India&sort=date&fromage=7", wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        
        cards_info = await page.evaluate('''() => {
            const res = [];
            document.querySelectorAll('[data-jk]').forEach(link => {
                const jk = link.getAttribute('data-jk');
                const card = link.closest('.cardOutline, .job_seen_beacon, li') || link;
                const text = card.innerText || '';
                const hasEasilyApply = /easily apply|apply now|responsive employer|indeed apply/i.test(text);
                const title = link.querySelector('span[title]')?.getAttribute('title') || link.innerText || '';
                res.push({
                    jk,
                    title: title.split('\\n')[0].trim(),
                    hasEasilyApply,
                    preview: text.replace(/\\s+/g, ' ').slice(0, 200)
                });
            });
            return res;
        }''')
        print(f"Total cards found: {len(cards_info)}")
        for c in cards_info[:10]:
            print(f"- [{c['jk']}] {c['title']} | EasilyApply: {c['hasEasilyApply']}")
            print(f"    Preview: {c['preview']}")
        await browser.close()
    await release_browser(session['id'])

asyncio.run(test_cards2())
