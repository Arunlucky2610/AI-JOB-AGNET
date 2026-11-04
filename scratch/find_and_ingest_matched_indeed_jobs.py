import asyncio
import os
import uuid
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from backend.db import Session, User, Job, now
from backend.platform_agent import (
    user_browser_session, release_browser, assess_quickly, career_report,
    build_job, posting_text, title_skip_reason
)
from backend.indeed import collect_job_urls, card_titles, canonical, apply_state_settled

load_dotenv()

USER_ID = 'ccf6395d-e103-4df4-bcdd-32c81a846158'

async def search_and_ingest():
    with Session() as db:
        user = db.get(User, USER_ID)
        profile = dict(user.profile)
        settings = dict(user.settings)
        # Check fresher matching
        relaxed = settings.get('matching') == 'fresher_ai'

    session = await user_browser_session(USER_ID)
    print("Browser session created:", session['id'])

    search_queries = [
        "https://in.indeed.com/jobs?q=AI+Engineer&l=Hyderabad%2C+Telangana&sort=date",
        "https://in.indeed.com/jobs?q=AI+Developer&l=Hyderabad%2C+Telangana&sort=date",
        "https://in.indeed.com/jobs?q=Junior+AI+Engineer&l=India&sort=date",
        "https://in.indeed.com/jobs?q=Python+AI+Developer&l=Hyderabad&sort=date",
        "https://in.indeed.com/jobs?q=Software+Engineer+Trainee&l=Hyderabad&sort=date"
    ]

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(session['connectUrl'])
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        candidate_urls = []
        for q_url in search_queries:
            print(f"Searching query: {q_url}")
            try:
                await page.goto(q_url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(2500)
                found = await collect_job_urls(page)
                titles = await card_titles(page)
                print(f"  Found {len(found)} candidate links")
                for u in found:
                    if u not in candidate_urls:
                        candidate_urls.append(u)
                if len(candidate_urls) >= 20:
                    break
            except Exception as e:
                print(f"  Error on search page: {e}")

        print(f"\nTotal candidate vacancies collected: {len(candidate_urls)}")

        evaluated_count = 0
        matched_count = 0

        for url in candidate_urls:
            if matched_count >= 3:
                print("Found 3 great matches! Stopping discovery.")
                break

            canon = canonical(url)
            with Session() as db:
                existing = db.query(Job).filter_by(user_id=USER_ID, canonical=canon).first()
                if existing and existing.payload.get('match', {}).get('matched'):
                    matched_count += 1
                    continue

            try:
                print(f"\nNavigating to job: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(2000)

                page_title = await page.title()
                unfit = title_skip_reason(page_title, profile, relaxed)
                if unfit:
                    print(f"  Skipped title: {unfit} ({page_title[:60]})")
                    continue

                text = (await page.inner_text('main') if await page.locator('main').count() else await page.inner_text('body'))[:20000]
                if len(text) < 200:
                    print("  Text too short, skipping.")
                    continue

                print("  Evaluating with DeepSeek...")
                result = await assess_quickly(profile, relaxed, page.url, text)
                if result.get('is_job') is not True or result.get('closed') is not False:
                    print(f"  Not open job: {result.get('explanation')}")
                    continue

                result['description'] = posting_text(text, 5000)
                payload = build_job(result, profile, settings, relaxed, url, text, source='Indeed')

                match = payload['match']
                score = match.get('score', 0)
                is_matched = match.get('matched', False)
                print(f"  Verdict: {payload['company']} - {payload['title']} | Fit: {score}% | Matched: {is_matched}")

                if is_matched:
                    matched_count += 1
                    print("  Building full Career Ops evidence report for matched job...")
                    try:
                        report = await career_report(profile, relaxed, page.url, text)
                        payload = build_job(result, profile, settings, relaxed, url, text, report=report, source='Indeed')
                    except Exception as err:
                        print("  Report building warning:", err)

                with Session() as db:
                    job = db.query(Job).filter_by(user_id=USER_ID, canonical=canon).first()
                    if job:
                        job.payload = payload
                    else:
                        job = Job(id=str(uuid.uuid4()), user_id=USER_ID, canonical=canon, payload=payload)
                        db.add(job)
                    db.commit()
                evaluated_count += 1
                await asyncio.sleep(2)
            except Exception as e:
                print(f"  Error processing job {url}: {e}")

        await browser.close()
    await release_browser(session['id'])
    print(f"\nCompleted! Total evaluated: {evaluated_count}, Total matched: {matched_count}")

asyncio.run(search_and_ingest())
