"""Indeed page helpers: search URLs, job discovery, and the Indeed Apply flow.

Nothing here reads or types credentials. Signing in, verification and CAPTCHAs are left to the person in
Live View (see human_gate.login_required). Indeed's own one-click apply ("Apply now") opens its own page
under smartapply.indeed.com rather than an in-page dialog like LinkedIn's Easy Apply, sometimes in a new
tab: MODAL is None (worker.fill_form then reads the whole page, exactly as it already does for a plain
employer portal), and open_apply hands back whichever page the flow is actually on.
"""
import re
from urllib.parse import quote_plus

MODAL=None
JOB_ID=re.compile(r'[?&](?:jk|vjk)=([0-9a-f]{8,})',re.I)   # vjk names the same job in a search page's split view
SENT=re.compile(r'application (?:has been |was )?(?:successfully )?submitted|your application (?:has been |was )?sent|thanks for applying|application complete',re.I)

# Indeed runs one site per country and www.indeed.com only lists US jobs, so a search for another country
# has to go to that country's own site (the sign-in is shared across all of them).
COUNTRY_HOSTS={'india':'in.indeed.com','united kingdom':'uk.indeed.com','uk':'uk.indeed.com','canada':'ca.indeed.com',
               'australia':'au.indeed.com','germany':'de.indeed.com','ireland':'ie.indeed.com','singapore':'sg.indeed.com',
               'united arab emirates':'ae.indeed.com','uae':'ae.indeed.com','netherlands':'nl.indeed.com','france':'fr.indeed.com'}
JOB_HOST=re.compile(r'^https://([a-z]{2,3}\.indeed\.com)/',re.I)

def host_for(profile):
    return COUNTRY_HOSTS.get((profile.get('country') or '').strip().lower(),'www.indeed.com')

def job_url(job_id, host='www.indeed.com'):
    return f'https://{host}/viewjob?jk={job_id}'

def canonical(url):
    """One stable URL per vacancy, whatever tracking parameters or view the link carried."""
    match=JOB_ID.search(url or '')
    if not match:return (url or '').split('?')[0].rstrip('/')
    host=JOB_HOST.match(url or '')
    return job_url(match.group(1),host.group(1).lower() if host and not host.group(1).lower().startswith('smartapply') else 'www.indeed.com')

def search_urls(profile, roles=None, country_only=False, any_location=False):
    """Job searches from the profile: one per role, newest first, past week."""
    roles=[r.strip() for r in (roles if roles is not None else profile.get('roles','')).split(',') if r.strip()][:5]
    city=(profile.get('locations') or '').split(',')[0].strip()
    country=(profile.get('country') or '').strip()
    place='' if any_location else country if country_only or not city else f'{city}, {country}' if country else city
    location=f'&l={quote_plus(place)}' if place else ''
    host=host_for(profile)
    return [f'https://{host}/jobs?q={quote_plus(role)}{location}&sort=date&fromage=7' for role in roles]

COLLECT_JS='''() => {
  const ids=new Set();
  document.querySelectorAll('[data-jk]').forEach(e=>{
    const v=e.getAttribute('data-jk');if(v&&/^[0-9a-f]{8,}$/i.test(v))ids.add(v);
  });
  document.querySelectorAll('a[href*="jk="]').forEach(a=>{
    const m=a.href.match(/[?&]jk=([0-9a-f]{8,})/i);if(m)ids.add(m[1]);
  });
  return Array.from(ids);
}'''

async def collect_job_urls(page):
    """Vacancy links from the search results currently open in `page`. Indeed paginates rather than
    virtualising its list, so nothing further needs to render before reading it."""
    await page.wait_for_timeout(1500)
    host=JOB_HOST.match(page.url or '')
    host=host.group(1).lower() if host else 'www.indeed.com'
    return [job_url(i,host) for i in await page.evaluate(COLLECT_JS)]

TITLES_JS=r'''() => {
  const out={};
  document.querySelectorAll('[data-jk]').forEach(e=>{
    const id=e.getAttribute('data-jk');
    if(!id||!/^[0-9a-f]{8,}$/i.test(id))return;
    let title=(e.getAttribute('aria-label')||e.innerText||'').split('\n')[0].trim();
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
  const caption=e=>((e.innerText||'')+' '+(e.getAttribute('aria-label')||'')).trim().toLowerCase();
  const controls=Array.from(document.querySelectorAll('button,a')).filter(shown).map(caption);
  const text=document.body.innerText;
  return {
    closed:/no longer accepting applications|this (?:job|posting) has expired|job is no longer available/i.test(text),
    easy:controls.some(t=>t==='apply now'),
    applied:/you.?ve applied|you applied on|application submitted/i.test(text),
    external:controls.some(t=>t.startsWith('apply on company site')||t.startsWith('apply on employer site')),
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
    try:await page.locator('main,#jobsearch-ViewjobPaneWrapper').first.wait_for(state='visible',timeout=timeout)
    except Exception:pass
    await page.wait_for_timeout(500)

async def apply_state_settled(page,tries=4):
    """apply_state, retried briefly while the page is still rendering ('unknown')."""
    state=await apply_state(page)
    for _ in range(tries-1):
        if state!='unknown':break
        await page.wait_for_timeout(1000);state=await apply_state(page)
    return state

async def modal_open(page):
    """Whether the apply flow is currently open: on Indeed that means being on its own apply subdomain,
    not a dialog on the job page."""
    return 'smartapply.indeed.com' in page.url

async def open_easy_apply(page):
    """Click Apply now and follow it onto Indeed's own apply flow. If that opens a new tab (observed
    behaviour varies), the original tab is redirected to the same address and the new one is closed, so
    everything after this still happens on the one shared tab — same contract as linkedin.open_easy_apply.

    Returns 'opened', or why not: 'closed' | 'applied' | 'not_easy'."""
    state=await apply_state_settled(page,tries=7)
    if state!='easy':return state if state in ('closed','applied') else 'not_easy'
    context=page.context
    before=set(context.pages)
    await page.locator('button:visible,a:visible').filter(has_text=re.compile(r'^\s*Apply now\s*$',re.I)).first.click(timeout=10000)
    for _ in range(16):
        await page.wait_for_timeout(500)
        opened=[p for p in context.pages if p not in before and not p.is_closed()]
        if opened:
            new_page=opened[-1]
            try:await new_page.wait_for_load_state('domcontentloaded',timeout=8000)
            except Exception:pass
            target=new_page.url
            try:await new_page.close()
            except Exception:pass
            await page.goto(target,wait_until='domcontentloaded',timeout=20000)
            return 'opened'
        if 'smartapply.indeed.com' in page.url:return 'opened'
    return 'not_easy'

async def application_sent(page):
    return await page.get_by_text(SENT).count()>0

async def close_modal(page):
    """Best effort: leave the unfinished apply flow. There is no dialog to dismiss here (see MODAL), so
    this just steps back to the job page; a fresh snapshot next time starts the form over from there."""
    try:
        if 'smartapply.indeed.com' in page.url:await page.go_back(timeout=5000)
    except Exception:pass
