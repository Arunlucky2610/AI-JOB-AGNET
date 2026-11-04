import asyncio
import hashlib
import secrets
from datetime import timedelta
from backend.db import Session, Login, now
from playwright.async_api import async_playwright

USER_ID = 'ccf6395d-e103-4df4-bcdd-32c81a846158'

def make_session():
    token = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(token.encode()).hexdigest()
    with Session() as db:
        db.add(Login(token=hashed, user_id=USER_ID, expires=now() + timedelta(days=7)))
        db.commit()
    return token

async def main():
    cookie_value = make_session()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()
        await context.add_cookies([{
            'name': 'orbit_session',
            'value': cookie_value,
            'domain': 'localhost',
            'path': '/',
            'httpOnly': True,
            'secure': False,
            'sameSite': 'Lax'
        }])
        page = await context.new_page()
        
        # 1. Overview
        await page.goto('http://localhost:3000')
        await page.wait_for_timeout(3000)
        await page.screenshot(path='/Users/arunsudhaveni/.gemini/antigravity/brain/687eedc5-cb26-4076-98cc-b2800635c5c7/matched_overview.png', full_page=True)

        # 2. Jobs tab
        await page.locator('nav button:has-text("Jobs")').click()
        await page.wait_for_timeout(2000)
        await page.screenshot(path='/Users/arunsudhaveni/.gemini/antigravity/brain/687eedc5-cb26-4076-98cc-b2800635c5c7/matched_jobs_tab.png', full_page=True)

        # 3. Live agent tab
        await page.locator('nav button:has-text("Live agent")').click()
        await page.wait_for_timeout(2000)
        await page.screenshot(path='/Users/arunsudhaveni/.gemini/antigravity/brain/687eedc5-cb26-4076-98cc-b2800635c5c7/matched_live_agent.png', full_page=True)

        # 4. Applications tab
        await page.locator('nav button:has-text("Applications")').click()
        await page.wait_for_timeout(2000)
        await page.screenshot(path='/Users/arunsudhaveni/.gemini/antigravity/brain/687eedc5-cb26-4076-98cc-b2800635c5c7/matched_applications_tab.png', full_page=True)

        await browser.close()
        print("All matched view screenshots taken successfully!")

asyncio.run(main())
