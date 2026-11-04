"""Bounded, read-only navigation for an employer's explicitly migrated portal."""
import re
from urllib.parse import urlparse

async def prepare_portal(page, job):
    host=urlparse(page.url).hostname or ''
    if host.endswith('.myworkdayjobs.com') and '/apply' in urlparse(page.url).path:
        # Workday renders its shell before the application controls arrive.
        await page.get_by_text(re.compile(r'Start Your Application|Sign In|Create Account',re.I)).first.wait_for(state='visible',timeout=30000)
    body=await page.inner_text('body')
    if 'cookies' in body.lower():
        decline=page.get_by_role('button',name=re.compile(r'^(Decline|Reject all|Reject cookies)$',re.I))
        if await decline.count():await decline.first.click(timeout=5000)
    migrated=(host=='harman.wd3.myworkdayjobs.com' and re.search(r'switched to a new system',body,re.I)) or (host in ['jobs.harman.com','jobsearch.harman.com'] and 'ApplicationMethods' not in page.url and urlparse(job['url']).hostname=='harman.wd3.myworkdayjobs.com')
    if migrated:
        # Follow observed employer links, never submit into the deprecated form.
        if host=='jobsearch.harman.com' and urlparse(page.url).path.endswith('/Error'):
            await page.goto('https://jobsearch.harman.com/en_US/careers/SearchJobs',wait_until='domcontentloaded',timeout=45000)
        if host=='harman.wd3.myworkdayjobs.com':
            await page.get_by_role('button',name='New Careers Site',exact=True).click(timeout=15000)
            await page.wait_for_url('https://jobs.harman.com/**',timeout=45000)
        if host!='jobsearch.harman.com':
            positions=page.get_by_role('link',name=re.compile(r'open\s+positions',re.I))
            await positions.wait_for(state='visible',timeout=20000)
            search_url=await positions.get_attribute('href')
            if urlparse(search_url).hostname!='jobsearch.harman.com':raise ValueError('Unexpected replacement portal')
            await page.goto(search_url,wait_until='domcontentloaded',timeout=45000)
        # Avature places the query in a URL path; slashes in AI/ML break that route.
        await page.locator('input[name="search"]').fill(re.sub(r'[^\w\s]',' ',job['title']),timeout=20000)
        await page.get_by_role('button',name=re.compile(r'^search jobs$',re.I)).click(timeout=15000)
        title=page.get_by_role('link',name=re.compile('^'+re.escape(job['title']).replace('/',r'\/')+'$',re.I))
        await title.first.wait_for(state='visible',timeout=20000)
        card=title.first.locator('xpath=ancestor::article[1]')
        # Avature uses div cards on some layouts.
        if not await card.count():card=title.first.locator('xpath=ancestor::div[contains(@class,"article")][1]')
        req=urlparse(job['url']).path.split('_')[-1].removesuffix('/apply')
        if not req or req not in await card.inner_text():raise ValueError('Replacement requisition does not match')
        apply=card.get_by_role('link',name=re.compile(r'^apply$',re.I))
        url=await apply.get_attribute('href')
        if urlparse(url).hostname!='jobsearch.harman.com':raise ValueError('Unexpected application host')
        await page.goto(url,wait_until='domcontentloaded',timeout=45000)
        await page.get_by_role('button',name=re.compile(r'^upload from computer$',re.I)).wait_for(state='visible',timeout=20000)
        return url
    if re.search(r'information submitted.*will not be reviewed|no longer accept.*applications',body,re.I):
        raise ValueError('Employer portal is deprecated')
    return None
