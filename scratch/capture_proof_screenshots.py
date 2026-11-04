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

        print("Navigating to http://127.0.0.1:3000...")
        await page.goto('http://127.0.0.1:3000')
        await page.locator('nav').wait_for(state='visible', timeout=20000)
        print("Dashboard loaded successfully.")

        # Step 1: Preferences tab - Sources (LinkedIn, Indeed, Naukri)
        print("Capturing 1: Preferences...")
        await page.locator('nav button:has-text("Preferences")').click()
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f'{OUT_DIR}/proof_1_preferences_sources.png')

        # Step 2: Live Agent Tab - Telemetry Panel with Indeed
        print("Capturing 2: Live Agent...")
        await page.locator('nav button:has-text("Live agent")').click()
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f'{OUT_DIR}/proof_2_live_agent_telemetry.png')

        # Step 3: Jobs Tab - Discovered Indeed Jobs
        print("Capturing 3: Jobs...")
        await page.locator('nav button:has-text("Jobs")').click()
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f'{OUT_DIR}/proof_3_indeed_jobs_discovered.png')

        # Step 4: Job Detail & Fit Evaluation Modal
        print("Capturing 4: Job Detail Modal...")
        job_btn = page.locator('button:has-text("AI Engineer – Agentic AI & RAG"), button:has-text("AI Engineer")').first
        if await job_btn.count() > 0:
            await job_btn.click()
            await page.wait_for_timeout(1500)
            await page.screenshot(path=f'{OUT_DIR}/proof_4_job_detail_evaluation.png')
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(800)

        # Step 5: Applications Tab
        print("Capturing 5: Applications...")
        await page.locator('nav button:has-text("Applications")').click()
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f'{OUT_DIR}/proof_5_applications_tab.png')

        # Step 6: Application Review Modal (Tailored Resume + Cover Letter)
        print("Capturing 6: Application Review...")
        review_btn = page.locator('button:has-text("Review & approve"), button:has-text("Review")').first
        if await review_btn.count() > 0:
            await review_btn.click()
            await page.wait_for_timeout(2000)
            await page.screenshot(path=f'{OUT_DIR}/proof_6_tailored_application_package.png')

        await browser.close()
        print("All proof screenshots captured successfully!")

if __name__ == '__main__':
    asyncio.run(main())
