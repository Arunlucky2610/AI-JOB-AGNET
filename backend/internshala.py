"""Internshala page helpers: search URLs, job/internship discovery, and the Internshala Apply flow.

Nothing here reads or types credentials. Signing in, verification and CAPTCHAs are left to the person
in Live View (see human_gate.login_required).
"""
import re
from urllib.parse import quote_plus
from .domain import career_level

# Modal scope selector for Internshala screening questions / apply modals
MODAL = '.modal-content, #application_modal, #apply_modal, [role="dialog"], dialog, .application-modal, #application_form, .application_form, #application_container, .application-container, #resume_modal, .resume_preview_modal, form[action*="application"]'
JOB_ID = re.compile(r'/(?:internship|job)/detail/(?:[a-zA-Z0-9_-]+-)?(\d+)', re.I)
SENT = re.compile(r'applied successfully|application submitted|already applied|you have already applied|thank you for applying|your application has been submitted', re.I)

def is_internshala_domain(url: str) -> bool:
    """Verify that a given URL belongs to internshala.com."""
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or '').lower()
        return host == 'internshala.com' or host.endswith('.internshala.com')
    except Exception:
        return False

def sign_in_url(profile=None) -> str:
    return 'https://internshala.com/login/user'

async def is_signed_in(page) -> bool:
    """Check if the user is currently signed in on Internshala."""
    try:
        url = page.url or ''
        if '/login' in url or '/registration' in url:
            return False
        # User profile dropdown / indicators mean signed in
        has_profile = await page.locator(
            '#user_menu, .profile_icon, a[href*="/user/profile"], [data-toggle="dropdown"].profile_container, .profile_container, .user-profile, .user_name'
        ).count() > 0
        if has_profile:
            return True
        # Login modal trigger / link means NOT signed in
        has_login = await page.locator(
            '#login-modal, a[href="/login/user"], a[href*="/login/user"], #modal__login, button.login-cta, .login_modal'
        ).count() > 0
        if has_login:
            return False
        from .human_gate import login_required
        return not await login_required(page)
    except Exception:
        return False

async def login_with_credentials(page, email: str, password: str) -> bool:
    """Automatically fills credentials into Internshala login form and submits."""
    try:
        url = page.url or ''
        if not url.startswith('https://internshala.com/login/user'):
            await page.goto(sign_in_url(), wait_until='domcontentloaded', timeout=45000)
        await settle(page)

        # Ensure student tab is active if tab switchers exist
        student_tab = page.locator('#student, a:has-text("Student"), button:has-text("Student"), .nav-link:has-text("Student")').first
        if await student_tab.count() > 0:
            try:
                await student_tab.click(timeout=2000)
            except Exception:
                pass

        # Email field
        email_loc = page.locator('#email, input[type="email"], input[name="email"], input[placeholder*="email" i]').first
        await email_loc.wait_for(state='visible', timeout=10000)
        await email_loc.click()
        await email_loc.fill('')
        await email_loc.type(email, delay=30)

        # Password field
        pw_loc = page.locator('#password, input[type="password"], input[name="password"]').first
        await pw_loc.wait_for(state='visible', timeout=10000)
        await pw_loc.click()
        await pw_loc.fill('')
        await pw_loc.type(password, delay=30)

        await page.wait_for_timeout(500)

        # Click submit button
        submit_loc = page.locator('#login_submit, button#login_submit, button[type="submit"]:has-text("Login"), .login_submit, button:has-text("Login"), input[type="submit"]').first
        if await submit_loc.count() > 0:
            await submit_loc.click(timeout=8000)
        else:
            await pw_loc.press('Enter')

        # Wait for navigation / response
        await page.wait_for_timeout(4000)
        return await is_signed_in(page)
    except Exception:
        return False

def job_url(job_id: str, kind: str = 'job') -> str:
    """Canonical URL pattern for job or internship."""
    kind_slug = 'internship' if 'internship' in str(kind).lower() else 'job'
    return f'https://internshala.com/{kind_slug}/detail/{job_id}'

def canonical(url: str) -> str:
    """Strips tracking query params (utm_*, search_id, etc.), preserving the clean detail URL."""
    u = url or ''
    kind = 'internship' if '/internship/detail/' in u else 'job'
    match = JOB_ID.search(u)
    if match:
        return job_url(match.group(1), kind=kind)
    return u.split('?')[0].rstrip('/')

def search_urls(profile: dict, roles=None, country_only=False, any_location=False) -> list[str]:
    """Search URLs from profile: handles both internships and fresher jobs based on career_level(profile).

    Slugifies target role and location.
    Examples:
      - https://internshala.com/jobs/{role_slug}-jobs-in-{city}/
      - https://internshala.com/internships/work-from-home-{role_slug}-internships/
    """
    roles_list = [r.strip() for r in (roles if roles is not None else profile.get('roles', '')).split(',') if r.strip()][:5]
    if not roles_list:
        roles_list = ['software-development']

    city = (profile.get('locations') or '').split(',')[0].strip()
    place = '' if (any_location or country_only) else city
    place_lower = place.lower()

    if place_lower in ('work from home', 'work-from-home', 'wfh', 'remote'):
        place_slug = 'work-from-home'
    elif place_lower and place_lower not in ('india', 'all'):
        place_slug = re.sub(r'[^a-zA-Z0-9]+', '-', place_lower).strip('-')
    else:
        place_slug = ''

    is_intern = career_level(profile) == 'intern'
    urls = []
    for role in roles_list:
        role_slug = re.sub(r'[^a-zA-Z0-9]+', '-', role.lower()).strip('-')
        if is_intern:
            if place_slug == 'work-from-home':
                url = f'https://internshala.com/internships/work-from-home-{role_slug}-internships/'
            elif place_slug:
                url = f'https://internshala.com/internships/{role_slug}-internships-in-{place_slug}/'
            else:
                url = f'https://internshala.com/internships/{role_slug}-internships/'
        else:
            if place_slug == 'work-from-home':
                url = f'https://internshala.com/jobs/work-from-home-{role_slug}-jobs/'
            elif place_slug:
                url = f'https://internshala.com/jobs/{role_slug}-jobs-in-{place_slug}/'
            else:
                url = f'https://internshala.com/jobs/{role_slug}-jobs/'
        urls.append(url)
    return urls

COLLECT_JOBS_JS = '''() => {
  const cards = Array.from(document.querySelectorAll('.individual_internship, .container-fluid.individual_internship, .internship_meta'));
  const results = [];
  const seenUrls = new Set();
  for (const card of cards) {
    const titleEl = card.querySelector('.job-internship-name, .profile, h3, h4, .heading_4_5, a[href*="/detail/"]');
    const compEl = card.querySelector('.company-name, .company_name, .link_display_like_text, .heading_6');
    const locEl = card.querySelector('.location_link, #location_names, .locations, .location');
    const salEl = card.querySelector('.stipend, .salary, .stipend_container, .salary_container');
    const linkEl = card.querySelector('a[href*="/detail/"]') || card.querySelector('a.view_detail_button') || (titleEl && titleEl.closest('a')) || card.querySelector('a');
    const descEl = card.querySelector('.internship_details, .job_description, .other_details, .meta_container');

    const url = linkEl ? linkEl.href : '';
    if (!url || seenUrls.has(url)) continue;
    seenUrls.add(url);

    const title = (titleEl ? (titleEl.innerText || titleEl.textContent || '') : '').trim();
    const company = (compEl ? (compEl.innerText || compEl.textContent || '') : '').trim();
    const location = (locEl ? (locEl.innerText || locEl.textContent || '') : '').trim();
    const salary_text = (salEl ? (salEl.innerText || salEl.textContent || '') : '').trim();
    const description = (descEl ? (descEl.innerText || descEl.textContent || '') : card.innerText || '').trim();

    if (title) {
      results.push({
        title: title,
        company: company,
        location: location,
        salary_text: salary_text,
        url: url,
        description: description,
        source: 'Internshala'
      });
    }
  }
  return results;
}'''

async def collect_jobs(page) -> list[dict]:
    """Scrapes real live postings directly from Internshala search results DOM."""
    try:
        return await page.evaluate(COLLECT_JOBS_JS)
    except Exception:
        return []

SCROLL_JS = '''() => {
  let el = document.querySelector('#internship_list_container, #list_container, .internship_list_container');
  while (el && el.scrollHeight <= el.clientHeight + 5) el = el.parentElement;
  (el || document.scrollingElement || window).scrollBy(0, 1200);
}'''

async def collect_job_urls(page):
    """Vacancy links from search results open in `page`."""
    try:
        await page.wait_for_timeout(1500)
        for _ in range(3):
            try:
                await page.evaluate(SCROLL_JS)
                await page.wait_for_timeout(700)
            except Exception:
                break
    except Exception:
        pass
    jobs = await collect_jobs(page)
    if jobs:
        return [canonical(j['url']) for j in jobs if j.get('url')]
    try:
        urls = await page.evaluate('''() => {
            const ids = new Set();
            document.querySelectorAll('a[href*="/job/detail/"], a[href*="/internship/detail/"]').forEach(a => {
                if (a.href) ids.add(a.href);
            });
            return Array.from(ids);
        }''')
        return [canonical(u) for u in urls if u]
    except Exception:
        return []

async def card_titles(page):
    """{canonical job url: title} for result cards."""
    jobs = await collect_jobs(page)
    return {canonical(j['url']): j['title'][:140] for j in jobs if j.get('url') and j.get('title')}

STATE_JS = '''() => {
  const shown = e => e.getClientRects().length > 0;
  const caption = e => ((e.innerText || '') + ' ' + (e.getAttribute('aria-label') || '') + ' ' + (e.value || '')).trim().toLowerCase();
  const controls = Array.from(document.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"]')).filter(shown).map(caption);
  const text = (document.body ? document.body.innerText : '').toLowerCase();

  const closed = /no longer accepting applications|applications (?:are )?closed|this (?:job|internship|vacancy) (?:is )?(?:closed|expired)|application deadline has passed|is no longer available/i.test(text);
  const applied = /already applied|you have already applied|applied successfully|application submitted/i.test(text);
  const hasExternal = controls.some(t => t.includes('apply on company site') || t.includes('company site') || t.includes('apply on employer site') || t.includes('external apply') || t.includes('apply externally'));
  const hasDirect = controls.some(t => /^apply now\\b/i.test(t) || t === 'apply' || t.includes('easy apply') || t.includes('apply now'));

  return {
    closed: closed,
    applied: applied,
    external: !applied && !closed && hasExternal,
    easy: !applied && !closed && !hasExternal && hasDirect
  };
}'''

async def apply_state(page) -> str:
    """Evaluates page state: 'easy' | 'external' | 'applied' | 'closed' | 'unknown'."""
    try:
        state = await page.evaluate(STATE_JS)
        if state.get('closed'): return 'closed'
        if state.get('applied'): return 'applied'
        if state.get('easy'): return 'easy'
        if state.get('external'): return 'external'
    except Exception:
        pass
    return 'unknown'

async def settle(page, timeout=6000):
    """Wait for page main content to render."""
    try:
        await page.locator(
            '.detail_view, .internship_details, .job_details, h1, main, #content, .individual_internship'
        ).first.wait_for(state='visible', timeout=timeout)
    except Exception:
        pass
    await page.wait_for_timeout(500)

async def apply_state_settled(page, tries=4):
    state = await apply_state(page)
    for _ in range(tries - 1):
        if state != 'unknown': break
        await page.wait_for_timeout(1000)
        state = await apply_state(page)
    return state

VISIBLE_MODAL = ', '.join(part.strip() + ':visible' for part in MODAL.split(','))

async def modal_open(page) -> bool:
    try:
        return await page.locator(VISIBLE_MODAL).count() > 0
    except Exception:
        return False

async def application_sent(page) -> bool:
    try:
        return await page.get_by_text(SENT).count() > 0
    except Exception:
        return False

async def dismiss_promotional_popups(page) -> bool:
    """Closes promotional subscription alerts or 'Sign up now to unlock' popups on Internshala."""
    try:
        dismissed = await page.evaluate('''() => {
            let found = false;
            const closeSelectors = [
                '.subscription_alert .close',
                '.subscription_alert [data-dismiss="modal"]',
                '.subscription_alert .ic-32-cross',
                '.subscription_alert .ic-24-cross',
                '#close_popup',
                '#close_modal',
                '#close_modal1',
                '.modal-header .close',
                'button.close[data-dismiss="modal"]'
            ];
            for (const sel of closeSelectors) {
                const btn = document.querySelector(sel);
                if (btn && btn.offsetParent !== null) {
                    btn.click();
                    found = true;
                }
            }
            document.querySelectorAll('.subscription_alert, .modal-backdrop').forEach(el => {
                el.remove();
                found = true;
            });
            document.body.classList.remove('modal-open');
            return found;
        }''')
        if dismissed:
            await page.wait_for_timeout(500)
            return True
    except Exception:
        pass
    return False

async def check_and_fill_missing_internshala_details(page, profile=None, checkpoint_fn=None):
    """Inspects Internshala resume modal:
    Checks if all details (contact number, city, education, skills, portfolio) are filled.
    If anything is empty, fills it from profile.
    If already filled, confirms and proceeds to scroll.
    """
    profile = profile or {}
    try:
        if checkpoint_fn: checkpoint_fn("Checking Internshala resume details: verifying contact info, education & skills...")
        
        # 1. Phone / Mobile field if empty
        phone_val = str(profile.get('phone') or '').strip()
        if phone_val:
            phone_inputs = page.locator('input[type="tel"]:visible, input[name*="phone" i]:visible, input[name*="mobile" i]:visible, input#phone:visible')
            for i in range(await phone_inputs.count()):
                inp = phone_inputs.nth(i)
                cur = (await inp.input_value() or '').strip()
                if not cur:
                    if checkpoint_fn: checkpoint_fn("Filling contact number from profile...")
                    await inp.fill(phone_val)
                    await page.wait_for_timeout(300)

        # 2. City / Location field if empty
        city_val = str(profile.get('city') or (profile.get('locations') or '').split(',')[0] or 'Hyderabad').strip()
        if city_val:
            city_inputs = page.locator('input[name*="city" i]:visible, input#city:visible, input[placeholder*="city" i]:visible')
            for i in range(await city_inputs.count()):
                inp = city_inputs.nth(i)
                cur = (await inp.input_value() or '').strip()
                if not cur:
                    if checkpoint_fn: checkpoint_fn(f"Filling city ({city_val}) from profile...")
                    await inp.fill(city_val)
                    await page.wait_for_timeout(300)

        # 3. College / Degree if empty
        edu_list = profile.get('education') or []
        col_val = edu_list[0].get('school') if edu_list else ''
        deg_val = edu_list[0].get('major') or edu_list[0].get('degree') if edu_list else ''
        if col_val:
            col_inputs = page.locator('input[name*="college" i]:visible, input#college:visible, input[placeholder*="college" i]:visible')
            for i in range(await col_inputs.count()):
                inp = col_inputs.nth(i)
                cur = (await inp.input_value() or '').strip()
                if not cur:
                    await inp.fill(col_val)
                    await page.wait_for_timeout(300)
        if deg_val:
            deg_inputs = page.locator('input[name*="degree" i]:visible, input#degree:visible, input[placeholder*="degree" i]:visible')
            for i in range(await deg_inputs.count()):
                inp = deg_inputs.nth(i)
                cur = (await inp.input_value() or '').strip()
                if not cur:
                    await inp.fill(deg_val)
                    await page.wait_for_timeout(300)

        # 4. GitHub / Portfolio link if empty
        portfolio_val = str(profile.get('portfolio') or 'https://github.com/').strip()
        if portfolio_val:
            port_inputs = page.locator('input[name*="portfolio" i]:visible, input[name*="github" i]:visible, input[placeholder*="portfolio" i]:visible, input[placeholder*="github" i]:visible, input[placeholder*="work sample" i]:visible')
            for i in range(await port_inputs.count()):
                inp = port_inputs.nth(i)
                cur = (await inp.input_value() or '').strip()
                if not cur:
                    if checkpoint_fn: checkpoint_fn("Adding portfolio/work sample link from profile...")
                    await inp.fill(portfolio_val)
                    await page.wait_for_timeout(300)

        if checkpoint_fn: checkpoint_fn("All Internshala resume details verified. Ready to proceed!")
    except Exception as e:
        if checkpoint_fn: checkpoint_fn(f"Details check note: {e}")

async def scroll_and_click_proceed(page, profile=None, checkpoint_fn=None) -> bool:
    """Verifies details, scrolls down through the Internshala resume preview modal/page, and clicks 'Proceed to application'."""
    await check_and_fill_missing_internshala_details(page, profile=profile, checkpoint_fn=checkpoint_fn)
    if checkpoint_fn: checkpoint_fn("Internshala details verified. Scrolling down to 'Proceed to application'...")
    
    # 1. Scroll window and all modal containers to the bottom
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    except Exception:
        pass
    try:
        await page.evaluate('''() => {
            const scrollables = document.querySelectorAll(
                '.modal, .modal-content, #application_modal, #resume_modal, [role="dialog"], ' +
                '.modal-body, .application-modal, #application_form, .application_form, ' +
                '.resume_preview_container, .content-container, dialog'
            );
            scrollables.forEach(el => {
                el.scrollTop = el.scrollHeight;
            });
        }''')
    except Exception:
        pass
    await page.wait_for_timeout(600)

    # 2. Look for the proceed button
    proceed_selectors = [
        '#proceed_to_application',
        'button#proceed_to_application',
        'a#proceed_to_application',
        '#proceed_to_application_button',
        'button#proceed',
        'a#proceed',
        '.proceed_btn',
        '.proceed-btn',
        '#proceed',
        'button:has-text("Proceed to application")',
        'a:has-text("Proceed to application")',
        'button:has-text("Proceed to apply")',
        'a:has-text("Proceed to apply")',
        'button:has-text("Proceed")',
        'a:has-text("Proceed")',
        'input[value*="Proceed" i]',
        'a.btn-primary:has-text("Proceed")',
        'button.btn-primary:has-text("Proceed")',
        '[class*="proceed"]',
    ]

    for sel in proceed_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                if checkpoint_fn: checkpoint_fn("Found 'Proceed to application' button. Clicking...")
                try:
                    await loc.scroll_into_view_if_needed()
                except Exception:
                    pass
                await loc.click(timeout=6000)
                await page.wait_for_timeout(1500)
                
                # Check if secondary confirmation popup appeared ("You will be redirected to another website...")
                try:
                    popup_btn = page.locator(
                        '.modal:visible, [role="dialog"]:visible, .popover:visible, .alert:visible'
                    ).locator(
                        'a:visible, button:visible, input[type="button"]:visible, input[type="submit"]:visible'
                    ).filter(has_text=re.compile(r'Proceed to application|Proceed to apply|Continue to apply|Apply externally|Proceed', re.I)).first
                    if await popup_btn.count() > 0:
                        if checkpoint_fn: checkpoint_fn("Found secondary 'Proceed to application ↗' popup button. Clicking...")
                        try: await popup_btn.scroll_into_view_if_needed()
                        except Exception: pass
                        try: await popup_btn.click(timeout=6000)
                        except Exception:
                            await page.evaluate('(b) => b.click()', await popup_btn.element_handle())
                        await page.wait_for_timeout(1500)
                except Exception:
                    pass
                return True
        except Exception:
            continue

    # Fallback: JavaScript scroll & click
    try:
        clicked = await page.evaluate('''() => {
            const elements = Array.from(document.querySelectorAll('button, a, input[type="button"], input[type="submit"], [role="button"]'));
            for (const el of elements) {
                const txt = (el.innerText || el.value || '').trim().toLowerCase();
                if (txt.includes('proceed to application') || txt.includes('proceed to apply') || txt === 'proceed') {
                    el.scrollIntoView({ block: 'center' });
                    el.click();
                    return true;
                }
            }
            return false;
        }''')
        if clicked:
            if checkpoint_fn: checkpoint_fn("Clicked 'Proceed to application' button via script.")
            await page.wait_for_timeout(1500)
            return True
    except Exception:
        pass

    return False

async def handle_internshala_application(page, user_id, profile, job, package, fields=None, checkpoint_fn=None) -> str:
    """Autonomously navigates and completes Internshala application:
    1. Checks if already applied or closed.
    2. Clicks 'Apply now' if visible.
    3. Scrolls down to the bottom of the resume preview modal and clicks 'Proceed to application'.
    4. Handles any screening questions or cover letter fields.
    5. Scrolls to bottom and clicks 'Submit application'.
    6. Confirms submission.
    """
    fields = fields or {}
    
    # Check if already sent
    if await application_sent(page):
        return 'submitted'

    # Check if closed
    try:
        body_text = (await page.inner_text('body')).lower()
        if re.search(r'no longer accepting applications|applications (?:are )?closed|this (?:job|internship) (?:is )?(?:closed|expired)|application deadline has passed', body_text):
            return 'closed'
    except Exception:
        pass

    # 1. Click "Apply now" if we are on the vacancy details page
    try:
        await dismiss_promotional_popups(page)
        apply_btn = page.locator(
            '#easy_apply_button:visible, button#apply_now_button:visible, a#apply_now_button:visible, '
            '.apply_now_button:visible, #apply_now_cta:visible, button:visible, a:visible'
        ).filter(has_text=re.compile(r'^\s*(?:Apply Now|Easy Apply|Apply)\s*$', re.I)).first
        if await apply_btn.count() > 0:
            if checkpoint_fn: checkpoint_fn("Clicking 'Apply now' on Internshala...")
            try:
                await apply_btn.scroll_into_view_if_needed()
            except Exception:
                pass
            try:
                await apply_btn.click(timeout=6000)
            except Exception:
                await page.evaluate('''(btn) => btn.click()''', await apply_btn.element_handle())
            await page.wait_for_timeout(1500)
    except Exception:
        pass

    if await application_sent(page):
        return 'submitted'

    # 2. Check details, scroll and click "Proceed to application" / "Proceed"
    await scroll_and_click_proceed(page, profile=profile, checkpoint_fn=checkpoint_fn)
    
    if await application_sent(page):
        return 'submitted'

    # 3. Handle screening questions / cover letter step if present
    try:
        # Check for cover letter textarea
        cl_textarea = page.locator(
            '#cover_letter:visible, textarea[name="cover_letter"]:visible, textarea.cover_letter:visible, '
            'textarea[placeholder*="cover letter" i]:visible, textarea[placeholder*="hired" i]:visible, textarea:visible'
        ).first
        if await cl_textarea.count() > 0:
            val = await cl_textarea.input_value()
            if not val.strip():
                if checkpoint_fn: checkpoint_fn("Entering tailored cover letter for Internshala...")
                cl_text = package.get('cover_letter') or f"I am very excited to apply for this {job.get('title', 'role')} at {job.get('company', 'your company')}. I have strong practical skills in {', '.join(profile.get('skills', [])[:5])} and am ready to start immediately."
                await cl_textarea.fill(cl_text[:900])
                await page.wait_for_timeout(500)

        # Check for availability radio buttons (Yes / Immediately)
        radios = page.locator('input[type="radio"]:visible')
        radio_count = await radios.count()
        for i in range(radio_count):
            r = radios.nth(i)
            lbl = await r.evaluate('''el => {
                const label = el.closest('label') || document.querySelector(`label[for="${el.id}"]`);
                return (label ? label.innerText : el.value || '').toLowerCase();
            }''')
            if any(w in lbl for w in ('yes', 'available', 'immediate', '1')):
                if not await r.is_checked():
                    await r.click()
                    await page.wait_for_timeout(300)
    except Exception as q_err:
        if checkpoint_fn: checkpoint_fn(f"Questions note: {q_err}")

    # 4. Scroll down to bottom and click "Submit application" / "Submit"
    if checkpoint_fn: checkpoint_fn("Scrolling to bottom and clicking 'Submit application'...")
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.evaluate('''() => {
            const scrollables = document.querySelectorAll('.modal, .modal-content, [role="dialog"], #application_modal, #application_form');
            scrollables.forEach(el => el.scrollTop = el.scrollHeight);
        }''')
    except Exception:
        pass
    await page.wait_for_timeout(600)

    submit_selectors = [
        '#submit:visible',
        'button#submit:visible',
        'input#submit:visible',
        'button:visible:has-text("Submit application")',
        'button:visible:has-text("Submit")',
        'input[value*="Submit" i]:visible',
        'a:visible:has-text("Submit application")',
        'a:visible:has-text("Submit")',
        'button.btn-primary:visible:has-text("Submit")',
        'a.btn-primary:visible:has-text("Submit")',
        '.submit_btn:visible',
        '.submit-btn:visible',
    ]

    for sel in submit_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                try:
                    await loc.scroll_into_view_if_needed()
                except Exception:
                    pass
                await loc.click(timeout=6000)
                await page.wait_for_timeout(2000)
                break
        except Exception:
            continue

    # 5. Check submission confirmation
    for _ in range(6):
        if await application_sent(page):
            if checkpoint_fn: checkpoint_fn("Internshala application submitted successfully!")
            return 'submitted'
        current_url = page.url or ''
        if '/student/applications' in current_url or 'application/submitted' in current_url:
            if checkpoint_fn: checkpoint_fn("Redirected to applications dashboard. Submission confirmed!")
            return 'submitted'
        await page.wait_for_timeout(1000)

    try:
        body_end = (await page.inner_text('body')).lower()
        if re.search(r'applied successfully|application submitted|already applied|thank you for applying|your application has been submitted', body_end):
            return 'submitted'
    except Exception:
        pass

    return 'opened'

async def open_easy_apply(page) -> str:
    """Clicks #easy_apply_button, button#apply_now_button, or .apply_now_button.
    Checks if application modal opens or if application completes immediately.
    Returns 'opened' | 'closed' | 'applied' | 'not_easy'.
    """
    if await modal_open(page):
        await scroll_and_click_proceed(page)
        return 'opened'
    state = await apply_state_settled(page, tries=5)
    if state != 'easy':
        return state if state in ('closed', 'applied') else 'not_easy'

    for attempt in range(2):
        try:
            await dismiss_promotional_popups(page)
            btn = page.locator(
                '#easy_apply_button:visible, button#apply_now_button:visible, .apply_now_button:visible, #apply_now_cta:visible, button:visible, a:visible'
            ).filter(has_text=re.compile(r'^\s*(?:Apply Now|Easy Apply|Apply)\s*$', re.I)).first
            try:
                await btn.click(timeout=8000)
            except Exception:
                await page.evaluate('''(b) => b.click()''', await btn.element_handle())
        except Exception:
            if await modal_open(page):
                await scroll_and_click_proceed(page)
                return 'opened'

        await page.wait_for_timeout(1500)
        if await application_sent(page):
            return 'applied'
        
        # Check if proceed button is already here or modal opened
        await scroll_and_click_proceed(page)
        if await application_sent(page):
            return 'applied'

        try:
            await page.locator(VISIBLE_MODAL).first.wait_for(state='visible', timeout=10000 if attempt else 6000)
            await scroll_and_click_proceed(page)
            return 'opened'
        except Exception:
            if await modal_open(page):
                await scroll_and_click_proceed(page)
                return 'opened'
            await page.wait_for_timeout(1000)

    if await application_sent(page):
        return 'applied'
    return 'not_easy'

async def close_modal(page) -> None:
    """Dismisses application dialogs if opened."""
    try:
        dismiss = page.locator(VISIBLE_MODAL).last.locator(
            'button, [role="button"], i, .close, [aria-label="Close"]'
        ).filter(has_text=re.compile(r'dismiss|close|cancel|discard|×|✕', re.I)).first
        if await dismiss.count():
            await dismiss.click(timeout=4000)
    except Exception:
        pass
