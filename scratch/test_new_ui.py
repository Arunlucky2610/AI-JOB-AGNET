import asyncio
import hashlib
import secrets
from datetime import timedelta
from backend.db import Session, Login, now
from playwright.async_api import async_playwright

USER_ID = '04c58992-9c0b-46cc-ab6b-e248b7f9da2f'
OUT_DIR = '/Users/arunsudhaveni/.gemini/antigravity/brain/f653f70f-3783-42a5-8a19-f8842c5c4ce0'

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
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1360, 'height': 850})
        await context.add_cookies([{
            'name': 'orbit_session',
            'value': cookie_value,
            'domain': '127.0.0.1',
            'path': '/',
            'httpOnly': True,
            'secure': False,
            'sameSite': 'Lax'
        }])
        page = await context.new_page()

        print("Navigating to Live Agent...")
        await page.goto('http://127.0.0.1:3000')
        await page.locator('nav').wait_for(state='visible', timeout=20000)
        await page.locator('nav button:has-text("Live agent")').click()
        await page.wait_for_timeout(1500)

        # Screenshot 1: Expanded sidebar with redesigned 6-step pipeline
        print("Capturing 1: Expanded sidebar with new flow...")
        await page.screenshot(path=f'{OUT_DIR}/new_ui_sidebar_expanded.png')

        # Click collapse sidebar button
        print("Collapsing sidebar...")
        collapse_btn = page.locator('.sidebar-collapse-btn')
        await collapse_btn.click()
        await page.wait_for_timeout(600)

        # Screenshot 2: Collapsed sidebar (full screen main content)
        print("Capturing 2: Collapsed sidebar...")
        await page.screenshot(path=f'{OUT_DIR}/new_ui_sidebar_collapsed.png')

        # Click topbar toggle button to reopen
        print("Re-expanding sidebar...")
        toggle_btn = page.locator('.sidebar-toggle-btn')
        await toggle_btn.click()
        await page.wait_for_timeout(600)

        await browser.close()
        print("Both screenshots captured successfully!")

if __name__ == '__main__':
    asyncio.run(main())
