"""Indeed page helpers: search URLs, job discovery, and the Indeed Apply flow.

Nothing here reads or types credentials. Signing in, verification and CAPTCHAs are left to the person in
Live View (see human_gate.login_required). Indeed's one-click apply ("Apply now" / "Easily apply") opens
either an in-page container (#ia-container) or smartapply.indeed.com.
"""
import re
from urllib.parse import quote_plus
from .domain import career_level

# Scope selector for Indeed Apply in-page containers or dialogs
MODAL = '#ia-container, [data-testid="indeedApplyIframe"], [id*="indeedapply" i], .ia-App, .ia-BasePage, [data-testid="ia-container"], [role="dialog"], dialog, main, #app-root'
JOB_ID = re.compile(r'[?&](?:jk|vjk)=([0-9a-f]{8,})', re.I)   # vjk names the same job in a search page's split view
SENT = re.compile(r'application (?:has been |was )?(?:successfully )?(?:submitted|received)|your application (?:has been |was )?sent|thanks for applying|application complete|your application was submitted|thank you for applying|application received|submitted to', re.I)

def is_indeed_domain(url):
    """Verify that a given URL belongs to an allowed Indeed domain."""
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or '').lower()
        return host == 'indeed.com' or host.endswith('.indeed.com')
    except Exception:
        return False

# Indeed runs one site per country (e.g. in.indeed.com for India, uk.indeed.com for UK).
COUNTRY_HOSTS = {
    'india': 'in.indeed.com',
    'united kingdom': 'uk.indeed.com',
    'uk': 'uk.indeed.com',
    'canada': 'ca.indeed.com',
    'australia': 'au.indeed.com',
    'germany': 'de.indeed.com',
    'ireland': 'ie.indeed.com',
    'singapore': 'sg.indeed.com',
    'united arab emirates': 'ae.indeed.com',
    'uae': 'ae.indeed.com',
    'netherlands': 'nl.indeed.com',
    'france': 'fr.indeed.com'
}
JOB_HOST = re.compile(r'^https://([a-z]{2,3}\.indeed\.com)/', re.I)

def host_for(profile):
    return COUNTRY_HOSTS.get((profile.get('country') or '').strip().lower(), 'www.indeed.com')

def sign_in_url(profile):
    host = host_for(profile)
    return f'https://secure.indeed.com/account/login?hl=en&continue=https%3A%2F%2F{host}%2F'

async def is_signed_in(page):
    """Check if the user is currently signed in on Indeed."""
    try:
        url = page.url or ''
        if 'secure.indeed.com' in url or '/account/login' in url:
            return False
        # Profile menu element means signed in
        has_profile = await page.locator('[data-gnav-element-name="ProfileMenu"], [data-testid="gnav-ProfileMenu"], [aria-label*="Profile" i], [aria-label*="Account" i], a[href*="/account/manage"]').count() > 0
        if has_profile:
            return True
        # Visible sign-in link means NOT signed in
        has_signin = await page.locator('a[href*="account/login"], a[href*="secure.indeed.com"], a[data-gnav-element-name="SignIn"]').count() > 0
        if has_signin:
            return False
        from .human_gate import login_required
        return not await login_required(page)
    except Exception:
        return False

async def login_with_credentials(page, email: str, password: str, profile: dict = None) -> bool:
    """Automatically fills credentials into Indeed login flow and submits."""
    try:
        url = page.url or ''
        if not ('secure.indeed.com' in url or '/account/login' in url or '/auth' in url):
            target_url = sign_in_url(profile or {})
            await page.goto(target_url, wait_until='domcontentloaded', timeout=45000)
        await settle(page)

        # Step 1: Email field
        email_loc = page.locator('input[type="email"], input[name="__email"], #ifl-InputFormField-3, input[id*="email" i], input[placeholder*="email" i]').first
        if await email_loc.count() > 0:
            await email_loc.wait_for(state='visible', timeout=10000)
            await email_loc.click()
            await email_loc.fill('')
            await email_loc.type(email, delay=30)
            await page.wait_for_timeout(500)

            # Look for Continue / Submit button
            cont_btn = page.locator('button[type="submit"], button:has-text("Continue"), button:has-text("Next"), button:has-text("Sign in")').first
            if await cont_btn.count() > 0:
                await cont_btn.click(timeout=8000)
                await page.wait_for_timeout(2000)

        # Step 2: Password field (might already be visible or appeared after email submission)
        pw_loc = page.locator('input[type="password"], input[name="__password"], #ifl-InputFormField-password, input[id*="password" i]').first
        try:
            await pw_loc.wait_for(state='visible', timeout=10000)
            await pw_loc.click()
            await pw_loc.fill('')
            await pw_loc.type(password, delay=30)
            await page.wait_for_timeout(500)

            submit_btn = page.locator('button[type="submit"], button:has-text("Sign in"), button:has-text("Log in")').first
            if await submit_btn.count() > 0:
                await submit_btn.click(timeout=8000)
            else:
                await pw_loc.press('Enter')
            await page.wait_for_timeout(4000)
        except Exception:
            pass

        return await is_signed_in(page)
    except Exception:
        return False

def job_url(job_id, host='www.indeed.com'):
    return f'https://{host}/viewjob?jk={job_id}'

def canonical(url):
    """One stable URL per vacancy, whatever tracking parameters or view the link carried."""
    match = JOB_ID.search(url or '')
    if not match:
        return (url or '').split('?')[0].rstrip('/')
    host = JOB_HOST.match(url or '')
    return job_url(match.group(1), host.group(1).lower() if host and not host.group(1).lower().startswith('smartapply') else 'www.indeed.com')

def search_urls(profile, roles=None, country_only=False, any_location=False):
    """Job searches from the profile: one per role, newest first, past week, filtered for 1-click Indeed Apply (iafilter=1)."""
    roles = [r.strip() for r in (roles if roles is not None else profile.get('roles', '')).split(',') if r.strip()][:5]
    city = (profile.get('locations') or '').split(',')[0].strip()
    country = (profile.get('country') or '').strip()
    place = '' if any_location else country if country_only or not city else f'{city}, {country}' if country else city
    location = f'&l={quote_plus(place)}' if place else ''
    host = host_for(profile)
    return [f'https://{host}/jobs?q={quote_plus(role)}{location}&sort=date&fromage=7&iafilter=1' for role in roles]

SCROLL_JS = '''() => {
  let el = document.querySelector('#mosaic-provider-jobcards, .jobsearch-ResultsList, [data-jk]');
  while (el && el.scrollHeight <= el.clientHeight + 5) el = el.parentElement;
  (el || document.scrollingElement || window).scrollBy(0, 1200);
}'''

COLLECT_JS = '''() => {
  const ids = new Set();
  document.querySelectorAll('[data-jk]').forEach(e => {
    const v = e.getAttribute('data-jk');
    if (v && /^[0-9a-f]{8,}$/i.test(v)) ids.add(v);
  });
  document.querySelectorAll('a[href*="jk="], a[data-jk]').forEach(a => {
    const v = a.getAttribute('data-jk');
    if (v && /^[0-9a-f]{8,}$/i.test(v)) { ids.add(v); return; }
    const m = a.href.match(/[?&]jk=([0-9a-f]{8,})/i);
    if (m) ids.add(m[1]);
  });
  return Array.from(ids);
}'''

async def collect_job_urls(page):
    """Vacancy links from the search results currently open in `page`."""
    await page.wait_for_timeout(2000)
    for _ in range(3):
        try:
            await page.evaluate(SCROLL_JS)
            await page.wait_for_timeout(600)
        except Exception:
            break
    host = JOB_HOST.match(page.url or '')
    host = host.group(1).lower() if host else 'www.indeed.com'
    return [job_url(i, host) for i in await page.evaluate(COLLECT_JS)]

TITLES_JS = r'''() => {
  const out = {};
  document.querySelectorAll('[data-jk]').forEach(e => {
    const id = e.getAttribute('data-jk');
    if (!id || !/^[0-9a-f]{8,}$/i.test(id)) return;
    const span = e.querySelector('span[title], span[id*="jobTitle"]');
    let title = span ? (span.getAttribute('title') || span.innerText) : '';
    if (!title) {
      title = e.innerText || '';
    }
    if (!title) {
      const label = e.getAttribute('aria-label') || '';
      title = label.replace(/^full details of\s+/i, '');
    }
    title = title.split('\n')[0].replace(/^full details of\s+/i, '').replace(/^(new|sponsored|urgently hiring)\s+/i, '').trim();
    if (title) out[id] = title;
  });
  return out;
}'''

async def card_titles(page):
    """{canonical job url: title} for the result cards that show one."""
    try:
        found = await page.evaluate(TITLES_JS)
        host = JOB_HOST.match(page.url or '')
        host = host.group(1).lower() if host else 'www.indeed.com'
    except Exception:
        return {}
    return {canonical(job_url(i, host)): t[:140] for i, t in found.items() if isinstance(t, str) and t.strip()}

STATE_JS = '''() => {
  const shown = e => e.getClientRects().length > 0;
  const caption = e => ((e.innerText || '') + ' ' + (e.getAttribute('aria-label') || '')).trim().toLowerCase();
  const controls = Array.from(document.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"]')).filter(shown).map(caption);
  const text = document.body ? document.body.innerText : '';
  const hasIndeedBtn = !!document.querySelector('[data-testid="indeedApplyButton"], #indeedApplyButton, [id*="indeedapply" i], .indeed-apply-button');
  const hasEasyCaption = controls.some(t => t.includes('apply now') || t.includes('easily apply'));
  const hasExternalCaption = controls.some(t => t.includes('apply on company site') || t.includes('apply on employer site') || t.includes('apply on website'));
  return {
    closed: /no longer accepting applications|this (?:job|posting) has expired|job is no longer available|this job has expired/i.test(text),
    easy: hasIndeedBtn || hasEasyCaption,
    applied: /you(?:'ve| have)? applied|you applied on|application submitted|already applied/i.test(text),
    external: !hasIndeedBtn && hasExternalCaption,
  };
}'''

async def apply_state(page):
    """'easy' | 'applied' | 'closed' | 'external' | 'unknown' for the job page open in `page`."""
    state = await page.evaluate(STATE_JS)
    if state['closed']:
        return 'closed'
    if state['easy']:
        return 'easy'
    if state['applied']:
        return 'applied'
    if state['external']:
        return 'external'
    return 'unknown'

async def settle(page, timeout=6000):
    try:
        await page.locator('main, #jobsearch-ViewjobPaneWrapper, [data-testid="jobsearch-ViewjobPaneWrapper"]').first.wait_for(state='visible', timeout=timeout)
    except Exception:
        pass
    await page.wait_for_timeout(500)

async def apply_state_settled(page, tries=4):
    """apply_state, retried briefly while the page is still rendering ('unknown')."""
    state = await apply_state(page)
    for _ in range(tries - 1):
        if state != 'unknown':
            break
        await page.wait_for_timeout(1000)
        state = await apply_state(page)
    return state

async def modal_open(page):
    """Whether the apply flow is currently open on Indeed."""
    u = page.url or ''
    if 'smartapply.indeed.com' in u or 'indeedapply' in u or '/apply/' in u:
        return True
    try:
        if await page.locator('#ia-container:visible, [data-testid="indeedApplyIframe"]:visible, [id*="indeedapply" i]:visible').count() > 0:
            return True
    except Exception:
        pass
    return False

async def open_easy_apply(page):
    """Click Apply now / Easily apply and follow onto Indeed's apply flow.
    
    If that opens a new tab, the original tab is redirected to the same address and the new one closed.
    Returns 'opened', or why not: 'closed' | 'applied' | 'not_easy'.
    """
    if await modal_open(page):
        return 'opened'
    state = await apply_state_settled(page, tries=7)
    if state != 'easy':
        return state if state in ('closed', 'applied') else 'not_easy'
    context = page.context
    before = set(context.pages)
    
    btn_locators = [
        page.locator('#jobsearch-ViewjobPaneWrapper button:visible, #jobsearch-ViewjobPaneWrapper a:visible, #jobsearch-ViewjobPaneWrapper [role="button"]:visible').filter(has_text=re.compile(r'^\s*(?:Apply now|Easily apply)\s*$', re.I)).first,
        page.locator('[data-testid="indeedApplyButton"]:visible, [id*="indeedApplyButton"]:visible').first,
        page.locator('button:visible, a:visible, [role="button"]:visible').filter(has_text=re.compile(r'^\s*(?:Apply now|Easily apply)\s*$', re.I)).first,
        page.locator('button:visible, a:visible').filter(has_text=re.compile(r'apply now|easily apply', re.I)).first
    ]
    btn_clicked = False
    for btn in btn_locators:
        if await btn.count():
            try:
                await btn.click(timeout=8000)
                btn_clicked = True
                break
            except Exception:
                pass
                
    if not btn_clicked:
        for frame in page.frames:
            try:
                f_btn = frame.locator('button:visible, a:visible, [role="button"]:visible').filter(has_text=re.compile(r'apply now|easily apply', re.I)).first
                if await f_btn.count():
                    await f_btn.click(timeout=8000)
                    btn_clicked = True
                    break
            except Exception:
                pass

    for _ in range(16):
        await page.wait_for_timeout(500)
        opened = [p for p in context.pages if p not in before and not p.is_closed()]
        if opened:
            new_page = opened[-1]
            for _ in range(10):
                if (new_page.url or '').startswith('http'): break
                await page.wait_for_timeout(400)
            target = new_page.url
            if target and target.startswith('http'):
                try:
                    await new_page.close()
                except Exception:
                    pass
                await page.goto(target, wait_until='domcontentloaded', timeout=20000)
                return 'opened'
        if await modal_open(page):
            return 'opened'
    return 'not_easy'

async def application_sent(page):
    try:
        if await page.get_by_text(SENT).count() > 0:
            return True
        body = (await page.inner_text('body', timeout=2000)).lower()
        return bool(SENT.search(body))
    except Exception:
        return False

async def close_modal(page):
    """Best effort: dismiss unfinished apply flow or go back."""
    try:
        dismiss = page.locator('button:visible, [role="button"]:visible').filter(has_text=re.compile(r'close|exit|cancel|dismiss', re.I)).first
        if await dismiss.count():
            await dismiss.click(timeout=4000)
            return
        if 'smartapply.indeed.com' in page.url or 'indeedapply' in page.url:
            await page.go_back(timeout=5000)
    except Exception:
        pass

# --- Dedicated Visible Browser Interactions for Indeed ---

async def perform_browser_search(page, role, location=''):
    """Visible browser search: types role and location into Indeed's real search inputs and submits."""
    # Find role / what input
    what_locators = [
        '#text-input-what',
        'input[name="q"]',
        'input[id*="what" i]',
        'input[aria-label*="job title" i]',
        'input[placeholder*="job title" i]',
    ]
    what_input = None
    for sel in what_locators:
        loc = page.locator(sel)
        if await loc.count() and await loc.first.is_visible():
            what_input = loc.first
            break
            
    if what_input:
        await what_input.click()
        await what_input.fill('')
        await what_input.type(role, delay=35)
        
    # Find location / where input
    if location:
        where_locators = [
            '#text-input-where',
            'input[name="l"]',
            'input[id*="where" i]',
            'input[aria-label*="city" i]',
            'input[placeholder*="city" i]',
        ]
        where_input = None
        for sel in where_locators:
            loc = page.locator(sel)
            if await loc.count() and await loc.first.is_visible():
                where_input = loc.first
                break
        if where_input:
            await where_input.click()
            await where_input.fill('')
            await where_input.type(location, delay=35)

    # Submit search
    btn_locators = [
        'button.yosegi-InlineWhatWhere-primaryButton',
        'button[type="submit"]',
        'form button[type="submit"]',
        'button:has-text("Find jobs")',
        'button:has-text("Search")',
    ]
    for sel in btn_locators:
        loc = page.locator(sel)
        if await loc.count() and await loc.first.is_visible():
            try:
                await loc.first.click(timeout=8000)
                await page.wait_for_load_state('domcontentloaded', timeout=15000)
                return True
            except Exception:
                pass
    if what_input:
        await what_input.press('Enter')
        await page.wait_for_load_state('domcontentloaded', timeout=15000)
        return True
    return False

EMPTY_SEARCH_RE = re.compile(r'did not match any jobs|no jobs found|try more general keywords|0 jobs|no matching jobs', re.I)

async def check_search_results_page(page):
    """Inspects search results page state: 'has_results', 'empty', 'challenge', 'auth'."""
    from .human_gate import challenge_shown, login_required
    if await challenge_shown(page):
        return 'challenge'
    if await login_required(page):
        return 'auth'
    # Check for job cards
    card_count = await page.locator('[data-jk], .job_seen_beacon, div.jobsearch-ResultsList').count()
    if card_count > 0:
        return 'has_results'
    # Check for empty text
    try:
        body_text = (await page.inner_text('body'))[:5000]
        if EMPTY_SEARCH_RE.search(body_text):
            return 'empty'
    except Exception:
        pass
    return 'empty' if card_count == 0 else 'has_results'

async def extract_job_page_details(page, target_url):
    """Visibly reads and extracts job information from the open Indeed job page."""
    data = {
        'url': canonical(target_url),
        'title': '',
        'company': '',
        'location': '',
        'description': '',
        'apply_type': 'unknown',
    }
    # Title locators
    for sel in [
        'h1[data-testid="jobsearch-JobInfoHeader-title"]',
        '.jobsearch-JobInfoHeader-title',
        'h1.jobTitle',
        'h1',
    ]:
        loc = page.locator(sel)
        if await loc.count():
            text = (await loc.first.inner_text()).strip()
            if text:
                data['title'] = text.split('\n')[0].strip()
                break
                
    # Company locators
    for sel in [
        '[data-testid="inlineHeader-companyName"] a',
        '[data-testid="inlineHeader-companyName"]',
        'span[data-testid="company-name"]',
        '.jobsearch-CompanyInfoContainer a',
        '.jobsearch-InlineCompanyRating-companyHeader',
    ]:
        loc = page.locator(sel)
        if await loc.count():
            text = (await loc.first.inner_text()).strip()
            if text:
                data['company'] = text
                break

    # Location locators
    for sel in [
        '[data-testid="inlineHeader-companyLocation"]',
        '[data-testid="job-location"]',
        '.jobsearch-JobInfoHeader-companyLocation',
    ]:
        loc = page.locator(sel)
        if await loc.count():
            text = (await loc.first.inner_text()).strip()
            if text:
                data['location'] = text
                break

    # Description locators
    for sel in [
        '#jobDescriptionText',
        '.jobsearch-jobDescriptionText',
        '[data-testid="jobDescriptionText"]',
        'main',
    ]:
        loc = page.locator(sel)
        if await loc.count():
            text = (await loc.first.inner_text()).strip()
            if len(text) > 40:
                data['description'] = text[:15000]
                break

    state = await apply_state_settled(page, tries=3)
    data['apply_type'] = state
    return data

async def detect_apply_button_action(page):
    """Inspects the actual application button rendered on page:
    Returns dict: {
        'action': 'apply_now' | 'easily_apply' | 'external' | 'applied' | 'closed' | 'unknown',
        'is_indeed_hosted': bool,
        'button_locator': Locator or None,
        'label': str
    }
    """
    state = await apply_state_settled(page, tries=4)
    if state == 'closed':
        return {'action': 'closed', 'is_indeed_hosted': False, 'button_locator': None, 'label': 'Closed'}
    if state == 'applied':
        return {'action': 'applied', 'is_indeed_hosted': False, 'button_locator': None, 'label': 'Already applied'}
        
    # Check for Indeed-hosted apply buttons
    indeed_locators = [
        page.locator('[data-testid="indeedApplyButton"]:visible, [id*="indeedApplyButton"]:visible').first,
        page.locator('#jobsearch-ViewjobPaneWrapper button:visible, #jobsearch-ViewjobPaneWrapper a:visible, #jobsearch-ViewjobPaneWrapper [role="button"]:visible').filter(has_text=re.compile(r'^\s*(?:Apply now|Easily apply)\s*$', re.I)).first,
        page.locator('button:visible, a:visible, [role="button"]:visible').filter(has_text=re.compile(r'^\s*(?:Apply now|Easily apply)\s*$', re.I)).first,
        page.locator('button:visible, a:visible').filter(has_text=re.compile(r'apply now|easily apply', re.I)).first
    ]
    for loc in indeed_locators:
        if await loc.count():
            lbl = (await loc.inner_text()).strip()
            return {
                'action': 'apply_now' if 'apply now' in lbl.lower() else 'easily_apply',
                'is_indeed_hosted': True,
                'button_locator': loc,
                'label': lbl
            }

    # Check for external employer apply buttons
    external_locators = [
        page.locator('button:visible, a:visible, [role="button"]:visible').filter(has_text=re.compile(r'apply on (?:company|employer) site|apply on website', re.I)).first,
        page.locator('button:visible, a:visible').filter(has_text=re.compile(r'^apply\b', re.I)).first,
    ]
    for loc in external_locators:
        if await loc.count():
            lbl = (await loc.inner_text()).strip()
            return {
                'action': 'external',
                'is_indeed_hosted': False,
                'button_locator': loc,
                'label': lbl
            }

    return {'action': state if state in ('applied', 'closed') else 'unknown', 'is_indeed_hosted': False, 'button_locator': None, 'label': ''}

async def detect_auth_checkpoint(page):
    """Dynamically detects Indeed authentication / verification checkpoint on the current page:
    Returns 'challenge' | 'otp' | 'email' | 'password' | 'phone' | 'user_verification' | 'none'
    """
    from .human_gate import challenge_shown
    if await challenge_shown(page):
        return 'challenge'
        
    url = (page.url or '').lower()
    is_auth_url = 'secure.indeed.com' in url or '/account/' in url or '/auth/' in url
    
    # 1. OTP / Verification code detection
    otp_selectors = [
        'input[autocomplete="one-time-code"]',
        'input[name*="verification" i]',
        'input[name*="code" i]',
        'input[id*="verification" i]',
        'input[id*="code" i]',
        'input[data-testid*="verification" i]',
        'input[data-testid*="otp" i]',
        'input[aria-label*="verification code" i]',
        'input[aria-label*="code" i]',
    ]
    for sel in otp_selectors:
        loc = page.locator(sel)
        if await loc.count() and await loc.first.is_visible():
            return 'otp'
            
    # Check page text for OTP verification prompt
    try:
        body = (await page.inner_text('body'))[:3000].lower()
        if any(p in body for p in ['enter verification code', 'enter the 6-digit code', 'enter the code we sent', 'we sent a code', 'verification code', 'enter code']):
            if await page.locator('input[type="text"]:visible, input[type="tel"]:visible, input[type="number"]:visible').count() > 0:
                return 'otp'
    except Exception:
        pass

    # 2. Password field detection
    pwd_loc = page.locator('input[type="password"]:visible, input[name="__password"]:visible, input[name="password"]:visible')
    if await pwd_loc.count():
        return 'password'

    # 3. Email field detection (on auth page)
    email_selectors = [
        'input[type="email"]:visible',
        '#ifl-InputFormField-3:visible',
        'input[name="__email"]:visible',
        'input[name="email"]:visible',
        'input[id*="email" i]:visible',
    ]
    for sel in email_selectors:
        loc = page.locator(sel)
        if await loc.count():
            # Verify it's on an authentication / sign-in screen, not a general job form
            if is_auth_url:
                return 'email'
            try:
                body = (await page.inner_text('body'))[:2000].lower()
                if any(k in body for k in ['sign in', 'welcome back', 'create an account', 'continue with email']):
                    return 'email'
            except Exception:
                pass

    # 4. Phone input detection on auth page
    phone_selectors = [
        'input[type="tel"]:visible',
        'input[name*="phone" i]:visible',
        'input[id*="phone" i]:visible',
    ]
    for sel in phone_selectors:
        loc = page.locator(sel)
        if await loc.count() and is_auth_url:
            return 'phone'

    return 'none'

async def submit_auth_email(page, email):
    """Enters user-provided email into Indeed's visible email field and clicks Continue."""
    for sel in ['input[type="email"]:visible', '#ifl-InputFormField-3:visible', 'input[name="__email"]:visible', 'input[name="email"]:visible', 'input[id*="email" i]:visible']:
        loc = page.locator(sel)
        if await loc.count():
            inp = loc.first
            await inp.click()
            await inp.fill('')
            await inp.fill(email)
            await page.wait_for_timeout(300)
            break
    else:
        return False
        
    btn_locators = [
        'button[type="submit"]:visible',
        'button:visible:has-text("Continue")',
        'button:visible:has-text("Next")',
        'button:visible:has-text("Sign in")',
        '[data-testid="sign-in-button"]:visible',
    ]
    for sel in btn_locators:
        loc = page.locator(sel)
        if await loc.count():
            await loc.first.click(timeout=8000)
            await page.wait_for_load_state('domcontentloaded', timeout=15000)
            return True
    await inp.press('Enter')
    await page.wait_for_load_state('domcontentloaded', timeout=15000)
    return True

async def submit_auth_password(page, password):
    """Enters user-provided password into Indeed's visible password field and clicks Sign in."""
    for sel in ['input[type="password"]:visible', 'input[name="__password"]:visible', 'input[name="password"]:visible']:
        loc = page.locator(sel)
        if await loc.count():
            inp = loc.first
            await inp.click()
            await inp.fill('')
            await inp.fill(password)
            await page.wait_for_timeout(300)
            break
    else:
        return False

    for sel in ['button[type="submit"]:visible', 'button:visible:has-text("Sign in")', 'button:visible:has-text("Log in")', 'button:visible:has-text("Continue")']:
        loc = page.locator(sel)
        if await loc.count():
            await loc.first.click(timeout=8000)
            await page.wait_for_load_state('domcontentloaded', timeout=15000)
            return True
    await inp.press('Enter')
    await page.wait_for_load_state('domcontentloaded', timeout=15000)
    return True

async def submit_auth_otp(page, code):
    """Enters user-provided OTP code into visible OTP fields and clicks Verify."""
    clean_code = re.sub(r'\D', '', str(code).strip())
    # Check for multi-digit input boxes (e.g. 6 separate inputs)
    multi_inputs = page.locator('input[data-testid*="otp"]:visible, input[aria-label*="digit" i]:visible, .otp-input:visible')
    count = await multi_inputs.count()
    if count >= 4 and len(clean_code) >= count:
        for i in range(count):
            await multi_inputs.nth(i).fill(clean_code[i])
            await page.wait_for_timeout(100)
    else:
        # Single input field
        otp_selectors = [
            'input[autocomplete="one-time-code"]:visible',
            'input[name*="verification" i]:visible',
            'input[name*="code" i]:visible',
            'input[id*="verification" i]:visible',
            'input[id*="code" i]:visible',
            'input[type="tel"]:visible',
            'input[type="number"]:visible',
            'input[type="text"]:visible',
        ]
        for sel in otp_selectors:
            loc = page.locator(sel)
            if await loc.count():
                inp = loc.first
                await inp.click()
                await inp.fill('')
                await inp.fill(clean_code or str(code).strip())
                await page.wait_for_timeout(300)
                break
        else:
            return False

    btn_locators = [
        'button[type="submit"]:visible',
        'button:visible:has-text("Verify")',
        'button:visible:has-text("Continue")',
        'button:visible:has-text("Submit")',
    ]
    for sel in btn_locators:
        loc = page.locator(sel)
        if await loc.count():
            await loc.first.click(timeout=8000)
            await page.wait_for_load_state('domcontentloaded', timeout=15000)
            return True
    return True

async def submit_auth_phone(page, phone):
    """Enters user-provided phone number into visible phone field and clicks Continue."""
    clean_phone = str(phone).strip()
    for sel in ['input[type="tel"]:visible', 'input[name*="phone" i]:visible', 'input[id*="phone" i]:visible']:
        loc = page.locator(sel)
        if await loc.count():
            inp = loc.first
            await inp.click()
            await inp.fill('')
            await inp.fill(clean_phone)
            await page.wait_for_timeout(300)
            break
    else:
        return False

    for sel in ['button[type="submit"]:visible', 'button:visible:has-text("Continue")', 'button:visible:has-text("Next")']:
        loc = page.locator(sel)
        if await loc.count():
            await loc.first.click(timeout=8000)
            await page.wait_for_load_state('domcontentloaded', timeout=15000)
            return True
    return True

async def detect_application_form_state(page):
    """Detects current step of Indeed Apply multi-step form:
    Returns 'contact' | 'resume' | 'questions' | 'review' | 'submitted' | 'unknown'
    """
    if await application_sent(page):
        return 'submitted'
        
    try:
        body = (await page.inner_text('body'))[:4000].lower()
    except Exception:
        body = ''
        
    # Check review step
    if any(k in body for k in ['review your application', 'please review your application', 'review and submit']):
        return 'review'
    # Check resume step
    if any(k in body for k in ['add a resume', 'upload resume', 'select a resume', 'resume / cv']) or await page.locator('input[type="file"]:visible').count() > 0:
        return 'resume'
    # Check questions step
    if any(k in body for k in ['screening questions', 'questions from the employer', 'work authorization', 'additional questions']):
        return 'questions'
    # Check contact step
    if any(k in body for k in ['contact information', 'enter your contact info', 'first name', 'phone number']):
        return 'contact'
        
    # Check for submit button on screen
    if await page.locator('button:visible:has-text("Submit your application"), button:visible:has-text("Submit application")').count() > 0:
        return 'review'
        
    return 'questions' if await page.locator('input, textarea, select').count() > 0 else 'unknown'

async def click_form_continue(page):
    """Clicks the next / continue button in Indeed Apply."""
    btn_locators = [
        page.locator('button:visible, [role="button"]:visible').filter(has_text=re.compile(r'^\s*(?:Continue|Next|Save and continue|Review your application)\s*$', re.I)).first,
        page.locator('button[type="submit"]:visible').first,
        page.locator('button:visible').filter(has_text=re.compile(r'continue|next|review', re.I)).first,
    ]
    for loc in btn_locators:
        if await loc.count():
            try:
                await loc.click(timeout=8000)
                await page.wait_for_timeout(1000)
                return True
            except Exception:
                pass
    return False

async def click_final_submit(page):
    """Clicks the final submission button in Indeed Apply."""
    btn_locators = [
        page.locator('button:visible, [role="button"]:visible').filter(has_text=re.compile(r'^\s*(?:Submit your application|Submit application|Send application)\s*$', re.I)).first,
        page.locator('button[type="submit"]:visible').filter(has_text=re.compile(r'submit', re.I)).first,
        page.locator('button:visible').filter(has_text=re.compile(r'submit your application|submit application', re.I)).first,
    ]
    for loc in btn_locators:
        if await loc.count():
            try:
                await loc.click(timeout=10000)
                await page.wait_for_timeout(1500)
                return True
            except Exception:
                pass
    return False

