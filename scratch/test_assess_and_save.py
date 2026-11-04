import asyncio
from playwright.async_api import async_playwright
from backend.db import Session, User, Job, now
from backend.platform_agent import user_browser_session, release_browser, assess_quickly, build_job, posting_text
from backend.indeed import canonical

async def main():
    user_id = 'ccf6395d-e103-4df4-bcdd-32c81a846158'
    with Session() as db:
        user = db.get(User, user_id)
        profile = dict(user.profile)
        settings = dict(user.settings)
    
    session = await user_browser_session(user_id)
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(session['connectUrl'])
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        
        test_url = "https://in.indeed.com/viewjob?jk=471e3bc84cc92b81"
        print("Visiting:", test_url)
        await page.goto(test_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2000)
        
        text = (await page.inner_text('main') if await page.locator('main').count() else await page.inner_text('body'))[:20000]
        print("Extracted text length:", len(text))
        
        print("Running DeepSeek assessment...")
        result = await assess_quickly(profile, False, page.url, text)
        print("Assessment result:", result.get('score'), result.get('explanation')[:150])
        
        result['description'] = posting_text(text, 5000)
        payload = build_job(result, profile, settings, False, test_url, text, source='Indeed')
        
        canon = canonical(test_url)
        with Session() as db:
            job = db.query(Job).filter_by(user_id=user_id, canonical=canon).first()
            if job:
                job.payload = payload
            else:
                import uuid
                job = Job(id=str(uuid.uuid4()), user_id=user_id, canonical=canon, payload=payload)
                db.add(job)
            db.commit()
            print("Job saved to database successfully! Job ID:", job.id)
            print("Title:", payload['title'], "| Company:", payload['company'], "| Score:", payload['match']['score'])
        
        await browser.close()
    await release_browser(session['id'])

asyncio.run(main())
