"""LinkedIn page helpers: search URLs, job discovery, and the Easy Apply dialog.

Nothing here reads or types credentials. Signing in, verification and CAPTCHAs are left to the person
in Live View (see human_gate.login_required).
"""
import re
from urllib.parse import quote_plus
from .domain import career_level

# Snapshot scope while an application is open: only the dialog's controls are offered to the model.
MODAL='.jobs-easy-apply-modal, .artdeco-modal, [role="dialog"]'
JOB_ID=re.compile(r'/jobs/view/(?:[^/?#]*-)?(\d{6,})')
SENT=re.compile(r'application sent|your application was sent|application submitted',re.I)

def sign_in_url(profile=None):
    return 'https://www.linkedin.com/login'

async def is_signed_in(page):
    """Check if the user is currently signed in on LinkedIn."""
    try:
        url = page.url or ''
        if '/login' in url or '/checkpoint/' in url or '/authwall' in url or '/signup' in url or '/uas/' in url:
            return False
        from .human_gate import login_required
        if await login_required(page):
            return False
        if any(p in url for p in ['/feed', '/mynetwork', '/jobs', '/messaging', '/notifications', '/in/']):
            return True
        has_nav = await page.locator('.global-nav, #global-nav, nav[aria-label="Primary"], .feed-identity-module, .profile-rail-card').count() > 0
        if has_nav:
            return True
        return True
    except Exception:
        return False

async def login_with_credentials(page, email: str, password: str) -> bool:
    """Automatically fills credentials into LinkedIn login form and submits."""
    try:
        if await is_signed_in(page):
            return True

        url = page.url or ''
        if not ('/login' in url or '/uas/login' in url or '/checkpoint' in url):
            await page.goto(sign_in_url(), wait_until='domcontentloaded', timeout=30000)
        await settle(page)

        # Dismiss any cookie banner if present
        for cookie_sel in ['button:has-text("Accept")', 'button:has-text("Agree & Join")', '.artdeco-global-alert-action button', '#artdeco-global-alert-container button']:
            try:
                c_btn = page.locator(cookie_sel).first
                if await c_btn.count() > 0 and await c_btn.is_visible():
                    await c_btn.click(timeout=1500)
                    break
            except Exception:
                pass

        # Email / username field
        email_sel = '#username, input#username, input[name="session_key"], input#session_key, input[type="email"], input[autocomplete="username"]'
        email_loc = page.locator(email_sel).first
        await email_loc.wait_for(state='visible', timeout=10000)
        await email_loc.fill(email)
        await page.wait_for_timeout(300)

        # Password field
        pw_sel = '#password, input#password, input[name="session_password"], input#session_password, input[autocomplete="current-password"], input[type="password"]'
        pw_loc = page.locator(pw_sel).first
        await pw_loc.wait_for(state='visible', timeout=10000)
        await pw_loc.fill(password)
        await page.wait_for_timeout(400)

        # Click submit button
        submit_sel = 'button[type="submit"], button[data-litms-control-urn="login-submit"], button[data-id="sign-in-form__submit-btn"], button.btn__primary--large, button:has-text("Sign in")'
        submit_loc = page.locator(submit_sel).first
        if await submit_loc.count() > 0:
            await submit_loc.click(timeout=6000)
        else:
            await pw_loc.press('Enter')

        # Wait for navigation or sign-in state to settle
        for _ in range(8):
            await page.wait_for_timeout(1000)
            if await is_signed_in(page):
                return True
            from .human_gate import challenge_shown
            if await challenge_shown(page):
                return False

        return await is_signed_in(page)
    except Exception as err:
        print(f"[LinkedIn Auto-Login Error]: {err}", flush=True)
        return False

def job_url(job_id):
    return f'https://www.linkedin.com/jobs/view/{job_id}/'

def canonical(url):
    """One stable URL per vacancy, whatever tracking parameters or slug the link carried."""
    match=JOB_ID.search(url or '')
    return job_url(match.group(1)) if match else (url or '').split('?')[0].rstrip('/')

def experience_levels(profile):
    """LinkedIn's f_E codes: 1 internship, 2 entry, 3 associate, 4 mid-senior, 5 director."""
    try:years=float(profile.get('experience') or 0)
    except (TypeError,ValueError):years=0
    if career_level(profile) in ('intern','fresher'):return '1,2'
    if years<=3:return '2,3'
    if years<=6:return '3,4'
    return '4,5'

def search_urls(profile, roles=None, country_only=False, any_location=False):
    """Easy Apply job searches from the profile: one per role, newest first, past week.
    `any_location` drops the location filter entirely (any_location implies country_only); LinkedIn then
    searches its default scope for a signed-in member rather than one the person is held to."""
    roles=[r.strip() for r in (roles if roles is not None else profile.get('roles','')).split(',') if r.strip()][:5]
    city=(profile.get('locations') or '').split(',')[0].strip()
    country=(profile.get('country') or '').strip()
    place='' if any_location else country if country_only or not city else f'{city}, {country}' if country else city
    levels=experience_levels(profile).replace(',','%2C')
    location=f'&location={quote_plus(place)}' if place else ''
    return [f'https://www.linkedin.com/jobs/search/?keywords={quote_plus(role)}{location}&f_AL=true&f_E={levels}&f_TPR=r604800&sortBy=DD' for role in roles]

COLLECT_JS='''() => {
  const ids=new Set();
  document.querySelectorAll('[data-occludable-job-id],[data-job-id]').forEach(e=>{
    const v=e.getAttribute('data-occludable-job-id')||e.getAttribute('data-job-id');
    if(v&&/^\\d{6,}$/.test(v))ids.add(v);
  });
  document.querySelectorAll('a[href*="/jobs/view/"]').forEach(a=>{
    const m=a.href.match(/\\/jobs\\/view\\/(?:[^\\/?#]*-)?(\\d{6,})/);if(m)ids.add(m[1]);
  });
  return Array.from(ids);
}'''

# The results list is virtualised: scroll its container so further cards render.
SCROLL_JS='''() => {
  let el=document.querySelector('[data-occludable-job-id],[data-job-id]');
  while(el&&el.scrollHeight<=el.clientHeight+5)el=el.parentElement;
  (el||document.scrollingElement).scrollBy(0,1400);
}'''

async def collect_job_urls(page):
    """Vacancy links from the search results currently open in `page`."""
    await page.wait_for_timeout(2500)
    for _ in range(5):
        await page.evaluate(SCROLL_JS);await page.wait_for_timeout(800)
    return [job_url(i) for i in await page.evaluate(COLLECT_JS)]

TITLES_JS=r'''() => {
  const out={};
  document.querySelectorAll('[data-occludable-job-id],[data-job-id]').forEach(card=>{
    const id=card.getAttribute('data-occludable-job-id')||card.getAttribute('data-job-id');
    if(!id||!/^\d{6,}$/.test(id))return;
    const link=card.querySelector('a[href*="/jobs/view/"]');
    let title=link?((link.getAttribute('aria-label')||link.innerText||'').split('\n')[0]):'';
    title=title.replace(/\s+with verification\s*$/i,'').trim();
    const half=title.length/2;
    if(title.length>8&&title.slice(0,Math.floor(half)).trim()===title.slice(Math.ceil(half)).trim())title=title.slice(0,Math.floor(half)).trim();
    if(title)out[id]=title;
  });
  return out;
}'''

async def card_titles(page):
    """{canonical job url: title} for the result cards that show one. Cards without a readable title are simply absent."""
    try:found=await page.evaluate(TITLES_JS)
    except Exception:return {}
    return {canonical(job_url(i)):t[:140] for i,t in found.items() if isinstance(t,str) and t.strip()}

STATE_JS='''() => {
  const shown=e=>e.getClientRects().length>0;
  const caption=e=>((e.innerText||'')+' '+(e.getAttribute('aria-label')||'')).trim();
  const controls=Array.from(document.querySelectorAll('button,a')).filter(shown).map(caption);
  const text=document.body.innerText;
  return {
    closed:/no longer accepting applications/i.test(text),
    easy:controls.some(t=>/^easy apply/i.test(t)),
    applied:/(^|\\n)\\s*applied\\b/i.test(text)||/see application status/i.test(text),
    external:controls.some(t=>/^apply\\b/i.test(t)&&!/easy apply/i.test(t)),
  };
}'''

async def apply_state(page):
    """'easy' | 'applied' | 'closed' | 'external' | 'unknown' for the job page open in `page`."""
    state=await page.evaluate(STATE_JS)
    if state['closed']:return 'closed'
    if state['easy']:return 'easy'
    if state['applied']:return 'applied'
    if state['external']:return 'external'
    return 'unknown'

async def settle(page,timeout=6000):
    """LinkedIn never becomes network-idle, so a fixed idle timeout always burns its full length. Wait for the
    page's own content instead."""
    try:await page.locator('main').first.wait_for(state='visible',timeout=timeout)
    except Exception:pass
    await page.wait_for_timeout(500)

async def apply_state_settled(page,tries=4):
    """apply_state, retried briefly while the top card is still rendering ('unknown')."""
    state=await apply_state(page)
    for _ in range(tries-1):
        if state!='unknown':break
        await page.wait_for_timeout(1000);state=await apply_state(page)
    return state

# Playwright's selector engine sees into open shadow roots, where LinkedIn now renders the application dialog.
VISIBLE_MODAL=', '.join(part.strip()+':visible' for part in MODAL.split(','))

async def modal_open(page):
    return await page.locator(VISIBLE_MODAL).count()>0

async def open_easy_apply(page):
    """Click Easy Apply. Returns 'opened', or why not: 'closed' | 'applied' | 'not_easy'.

    The top card can still be rendering when the page has just loaded (slower with several tabs open), so an
    'unknown' page is given a few seconds, and a click whose dialog does not appear is tried once more."""
    if await modal_open(page):
        return 'opened'
    state=await apply_state_settled(page,tries=7)
    if state!='easy':return state if state in ('closed','applied') else 'not_easy'
    for attempt in range(2):
        try:
            await page.locator('button:visible,a:visible').filter(has_text=re.compile(r'^\s*Easy Apply',re.I)).first.click(timeout=10000)
        except Exception:
            if await modal_open(page):return 'opened'
        try:
            await page.locator(VISIBLE_MODAL).first.wait_for(state='visible',timeout=12000 if attempt else 8000)
            return 'opened'
        except Exception:
            if await modal_open(page):return 'opened'
            await page.wait_for_timeout(1500)
    return 'not_easy'

async def application_sent(page):
    return await page.get_by_text(SENT).count()>0

async def close_modal(page):
    """Best effort: dismiss the application dialog and discard the unfinished draft."""
    try:
        # Only the dialog's own close button: the page has other "Close" controls (menus, messaging).
        dismiss=page.locator(VISIBLE_MODAL).last.get_by_role('button',name=re.compile(r'dismiss|close',re.I)).first
        if await dismiss.count():
            await dismiss.click(timeout=5000)
            await page.locator(VISIBLE_MODAL).get_by_role('button',name=re.compile(r'^discard$',re.I)).first.click(timeout=5000)
    except Exception:
        pass
