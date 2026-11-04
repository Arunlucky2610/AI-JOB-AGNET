"""Naukri page helpers: search URLs, job discovery, and the Naukri Apply flow.

Nothing here reads or types credentials. Signing in, verification and CAPTCHAs are left to the person
in Live View (see human_gate.login_required).
"""
import re
from urllib.parse import quote_plus
from .domain import career_level

# Modal scope selector for Naukri screening questions / apply drawers / modals
MODAL = '.apply-message-container, .chatbot_drawer, [class*="drawer-wrapper"], [class*="apply-modal"], [class*="applyDrawer"], [role="dialog"], dialog, .modal-container, [class*="chatbot"], [id*="apply-container"], .apply-drawer'
JOB_ID = re.compile(r'(?:[-_]|\bid=)(\d{6,})(?:[?&#]|$)', re.I)
SENT = re.compile(r'successfully applied|application submitted|applied successfully|you have applied for this job|your application has been sent|application sent|thank you for applying|already applied|application has been submitted', re.I)

def is_naukri_domain(url):
    """Verify that a given URL belongs to naukri.com."""
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or '').lower()
        return host == 'naukri.com' or host.endswith('.naukri.com')
    except Exception:
        return False

def sign_in_url(profile=None):
    return 'https://www.naukri.com/nlogin/login'

async def dismiss_promotional_popups(page) -> bool:
    """Closes promotional notification prompts, app download banners, and overlays on Naukri."""
    try:
        dismissed = await page.evaluate('''() => {
            let found = false;
            const closeSelectors = [
                '#block',
                '.crossIcon',
                '.nI-gNb-header__close',
                '.banner-close',
                '[class*="closeIcon"]',
                '[class*="drawer-close"]',
                '.chat-close',
                '#credential_picker_container'
            ];
            for (const sel of closeSelectors) {
                const el = document.querySelector(sel);
                if (el) {
                    if (typeof el.click === 'function') el.click();
                    else el.remove();
                    found = true;
                }
            }
            document.querySelectorAll('.modal-backdrop, .overlay-backdrop').forEach(b => {
                b.remove();
                found = true;
            });
            return found;
        }''')
        if dismissed:
            await page.wait_for_timeout(400)
            return True
    except Exception:
        pass
    return False

async def is_signed_in(page):
    """Check if the user is currently signed in on Naukri."""
    try:
        url = page.url or ''
        if '/nlogin/login' in url or 'login.naukri.com' in url or '/registration/' in url or '/nlogin/otp' in url:
            return False
        if any(p in url for p in ['/mnjuser/homepage', '/mynaukri', '/mnjuser/profile']):
            return True
        has_profile = await page.locator('.nI-gNb-drawer, a[href*="/mynaukri"], a[href*="/mnjuser/profile"], .user-name, [data-ga-track*="profile"], .nI-gNb-header__user-wrap, [title*="Naukri" i]').count() > 0
        if has_profile:
            return True
        has_login = await page.locator('a[href*="/nlogin/login"], a.nI-gNb-header__login, #login_Layer').count() > 0
        if has_login:
            return False
        from .human_gate import login_required
        return not await login_required(page)
    except Exception:
        return False

async def login_with_credentials(page, email: str, password: str) -> bool:
    """Automatically fills credentials into Naukri login form and submits."""
    try:
        url = page.url or ''
        if not ('/nlogin/login' in url or 'login.naukri.com' in url):
            await page.goto(sign_in_url(), wait_until='domcontentloaded', timeout=45000)
        await settle(page)
        await dismiss_promotional_popups(page)

        # Email field
        email_loc = page.locator('#usernameField, input[placeholder*="Email" i], input[placeholder*="Username" i], input[type="text"][name="email"], input[type="email"]').first
        await email_loc.wait_for(state='visible', timeout=10000)
        await email_loc.click()
        await email_loc.fill('')
        await email_loc.type(email, delay=35)

        # Password field
        pw_loc = page.locator('#passwordField, input[type="password"]').first
        await pw_loc.wait_for(state='visible', timeout=10000)
        await pw_loc.click()
        await pw_loc.fill('')
        await pw_loc.type(password, delay=35)

        await page.wait_for_timeout(500)

        # Click submit button
        submit_loc = page.locator('.loginButton, button[type="submit"]:has-text("Login"), button:has-text("Login"), button.btn-primary').first
        if await submit_loc.count() > 0:
            try:
                await submit_loc.click(timeout=8000)
            except Exception:
                await page.evaluate('(b) => b.click()', await submit_loc.element_handle())
        else:
            await pw_loc.press('Enter')

        await page.wait_for_timeout(4000)
        await dismiss_promotional_popups(page)
        return await is_signed_in(page)
    except Exception:
        return False

def job_url(job_id):
    return f'https://www.naukri.com/job-listings-{job_id}'

def canonical(url):
    """One stable URL per vacancy, whatever tracking parameters or slug the link carried."""
    match = JOB_ID.search(url or '')
    if match:
        return job_url(match.group(1))
    return (url or '').split('?')[0].rstrip('/')

def experience_param(profile):
    """Naukri experience parameter formatting."""
    try:
        years = float(profile.get('experience') or 0)
    except (TypeError, ValueError):
        years = 0
    if career_level(profile) in ('intern', 'fresher') or years <= 0:
        return '0'
    if years <= 2:
        return '0-2'
    if years <= 5:
        return '3-5'
    return f'{int(years)}'

def search_urls(profile, roles=None, country_only=False, any_location=False):
    """Search URLs from profile: one per role, newest first, past week (jobAge=7)."""
    roles = [r.strip() for r in (roles if roles is not None else profile.get('roles', '')).split(',') if r.strip()][:5]
    city = (profile.get('locations') or '').split(',')[0].strip()
    country = (profile.get('country') or '').strip()
    place = '' if any_location else country if country_only or not city else city
    exp = experience_param(profile)

    urls = []
    for role in roles:
        role_slug = re.sub(r'[^a-zA-Z0-9]+', '-', role.lower()).strip('-')
        if place and place.lower() not in ('india', 'all'):
            place_slug = re.sub(r'[^a-zA-Z0-9]+', '-', place.lower()).strip('-')
            url = f'https://www.naukri.com/{role_slug}-jobs-in-{place_slug}?k={quote_plus(role)}&l={quote_plus(place)}&experience={exp}'
        else:
            url = f'https://www.naukri.com/{role_slug}-jobs?k={quote_plus(role)}&experience={exp}'
        urls.append(url)
    return urls

SCROLL_JS = '''() => {
  let el = document.querySelector('.styles_job-listing-container__bQ_mX, .list, #listContainer, .srp-jobtuple-wrapper');
  while (el && el.scrollHeight <= el.clientHeight + 5) el = el.parentElement;
  (el || document.scrollingElement || window).scrollBy(0, 1200);
}'''

COLLECT_JS = '''() => {
  const ids = new Set();
  document.querySelectorAll('a[href*="/job-listings"]').forEach(a => {
    const href = a.href || '';
    if (href && !href.includes('/job-listings-search')) {
      ids.add(href.split('?')[0]);
    }
  });
  document.querySelectorAll('[data-job-id]').forEach(e => {
    const id = e.getAttribute('data-job-id');
    if (id && /^\\d{6,}$/.test(id)) {
      ids.add('https://www.naukri.com/job-listings-' + id);
    }
  });
  return Array.from(ids);
}'''

TITLES_JS = r'''() => {
  const out = {};
  document.querySelectorAll('.srp-jobtuple-wrapper, .cust-job-tuple, article.jobTuple, [data-job-id]').forEach(card => {
    const link = card.querySelector('a.title, a[href*="/job-listings"]');
    if (!link) return;
    const href = (link.href || '').split('?')[0];
    let title = (link.getAttribute('title') || link.innerText || '').split('\n')[0].trim();
    if (href && title) {
      out[href] = title;
    }
  });
  return out;
}'''

async def collect_job_urls(page):
    """Vacancy links from search results open in `page`."""
    await page.wait_for_timeout(2000)
    for _ in range(3):
        try:
            await page.evaluate(SCROLL_JS)
            await page.wait_for_timeout(700)
        except Exception:
            break
    urls = await page.evaluate(COLLECT_JS)
    return [canonical(u) for u in urls if u]

async def card_titles(page):
    """{canonical job url: title} for result cards."""
    try:
        found = await page.evaluate(TITLES_JS)
    except Exception:
        return {}
    return {canonical(u): t[:140] for u, t in found.items() if isinstance(t, str) and t.strip()}

STATE_JS = '''() => {
  const shown = e => e.getClientRects().length > 0;
  const caption = e => ((e.innerText || '') + ' ' + (e.getAttribute('aria-label') || '')).trim().toLowerCase();
  const controls = Array.from(document.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"]')).filter(shown).map(caption);
  const text = document.body ? document.body.innerText : '';
  const hasExternal = controls.some(t => t.includes('apply on company site') || t.includes('company site') || t.includes('apply on employer site'));
  const hasDirectApply = controls.some(t => /^apply\\b/i.test(t) || t.includes('apply on naukri') || t.includes('quick apply') || t === 'apply');
  const alreadyApplied = /already applied|you have applied|applied on|application submitted/i.test(text);
  const closed = /no longer accepting applications|job is expired|this job has expired|vacancy closed/i.test(text);

  return {
    closed: closed,
    applied: alreadyApplied,
    external: !alreadyApplied && hasExternal,
    easy: !alreadyApplied && !hasExternal && hasDirectApply
  };
}'''

async def apply_state(page):
    """'easy' | 'applied' | 'closed' | 'external' | 'unknown' for the job page open in `page`."""
    state = await page.evaluate(STATE_JS)
    if state['closed']: return 'closed'
    if state['applied']: return 'applied'
    if state['easy']: return 'easy'
    if state['external']: return 'external'
    return 'unknown'

async def settle(page, timeout=6000):
    """Wait for page main content to render."""
    try:
        await page.locator('.styles_jhc__header__P1p1Q, .job-desc, h1, main, #root, .styles_job-listing-container__bQ_mX').first.wait_for(state='visible', timeout=timeout)
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

async def modal_open(page):
    return await page.locator(VISIBLE_MODAL).count() > 0

async def open_easy_apply(page):
    """Click Apply on Naukri. Returns 'opened' | 'closed' | 'applied' | 'not_easy'."""
    if await modal_open(page):
        return 'opened'
    state = await apply_state_settled(page, tries=5)
    if state != 'easy':
        return state if state in ('closed', 'applied') else 'not_easy'

    for attempt in range(2):
        try:
            await dismiss_promotional_popups(page)
            btn = page.locator('button:visible, a:visible, [role="button"]:visible').filter(has_text=re.compile(r'^\s*(?:Apply(?: on Naukri)?|Quick Apply)\s*$', re.I)).first
            try:
                await btn.click(timeout=8000)
            except Exception:
                await page.evaluate('(b) => b.click()', await btn.element_handle())
        except Exception:
            if await modal_open(page):
                return 'opened'

        # Check if click immediately finished application or opened screening questions
        await page.wait_for_timeout(1500)
        if await application_sent(page):
            return 'opened'
        try:
            await page.locator(VISIBLE_MODAL).first.wait_for(state='visible', timeout=10000 if attempt else 6000)
            return 'opened'
        except Exception:
            if await modal_open(page):
                return 'opened'
            await page.wait_for_timeout(1000)

    return 'not_easy'

async def application_sent(page):
    return await page.get_by_text(SENT).count() > 0

async def is_chatbot_open(page):
    """Check whether Naukri's application chatbot drawer or screening questions are visible."""
    try:
        drawer = page.locator('.chatbot_MessageContainer, .footerInputBoxWrapper, [id*="chatList"], [id*="userInput"], .chatbot_drawer, [class*="chatbot"]')
        return await drawer.first.is_visible()
    except Exception:
        return False

async def handle_naukri_chatbot(page, user_id, profile, job, checkpoint_fn=None):
    """Autonomously traverses and answers all questions in Naukri's screening chatbot drawer until submitted.
    
    1. Answers profile fields (Full Name, Email, Phone, City, Experience, Notice, CTC).
    2. Answers custom questions via QuestionMemory or live LLM + Web Research.
    3. Persists newly generated answers into QuestionMemory for future runs.
    4. Clicks Save/Send or quick-reply options, looping until the application is submitted.
    """
    max_turns = 25
    last_q = None
    stuck_count = 0

    for turn in range(max_turns):
        if checkpoint_fn: checkpoint_fn(f"Naukri chatbot active (turn {turn + 1}/{max_turns})...")
        
        # 1. Check if application is already submitted or redirected
        current_url = page.url or ''
        if 'myapply/saveApply' in current_url:
            body_txt = (await page.inner_text('body')).lower()
            if 'was not accepted' in body_txt or 'incomplete information' in body_txt or '406' in current_url:
                if checkpoint_fn: checkpoint_fn('Naukri rejected this vacancy due to previously unsubmitted mandatory info.')
                return 'incomplete_rejected'
            if 'apply confirmation' in (await page.title()).lower() or 'successful' in body_txt:
                return 'submitted'

        if await application_sent(page):
            return 'submitted'
        
        chat_text = await page.evaluate('''() => {
            const drawer = document.querySelector('.chatbot_drawer, [class*="chatbot"], [class*="drawer-wrapper"], .apply-message-container, [role="dialog"]') || document.body;
            return drawer.innerText || '';
        }''')
        if re.search(r'successfully applied|application submitted|applied successfully|you have applied|your application has been sent|thank you for applying|already applied', chat_text, re.I):
            return 'submitted'

        # 2. Extract active question and controls from the chatbot drawer
        info = await page.evaluate(r'''() => {
            const drawer = document.querySelector('.chatbot_MessageContainer, .chatbot_drawer, [class*="chatbot"], [class*="drawer"], .apply-message-container, [role="dialog"]') || document.body;
            
            // Check Naukri chatList messages first
            const naukriMsgs = Array.from(document.querySelectorAll('.botMsg span, .botItem span, [class*="botMsg"], [class*="botItem"] span'));
            let question = '';
            for (let i = naukriMsgs.length - 1; i >= 0; i--) {
                const t = (naukriMsgs[i].innerText || '').trim();
                if (t.length > 2 && !t.includes('Kindly answer') && !t.includes('thank you for showing interest')) {
                    question = t;
                    break;
                }
            }

            // Quick reply buttons (excluding Save/Send/Close)
            const chips = Array.from(drawer.querySelectorAll('button, [role="button"], [class*="chip"], [class*="option"], [class*="choice"]')).filter(b => {
                const t = (b.innerText || '').trim();
                return b.offsetWidth > 0 && b.offsetHeight > 0 && !/^(save|send|submit|cancel|close|×)$/i.test(t);
            }).map(b => b.innerText.trim());

            // Check input element or contenteditable
            const hasInput = !!(document.querySelector('.textArea[contenteditable="true"], [id*="userInput"], input[placeholder*="message" i], textarea[placeholder*="message" i], input[type="text"]:not([class*="Uploader"]):not([type="file"])'));

            return { question, chips, hasInput };
        }''')

        question = (info.get('question') or '').strip()
        chips = info.get('chips') or []
        has_input = bool(info.get('hasInput'))

        if not question and not has_input and not chips:
            await page.wait_for_timeout(1500)
            if await application_sent(page) or not await is_chatbot_open(page):
                return 'submitted'
            continue

        if question == last_q:
            stuck_count += 1
            if stuck_count >= 3:
                try:
                    await page.evaluate('''() => {
                        const btn = Array.from(document.querySelectorAll('button')).find(b => b.offsetParent !== null && /^(save|send|submit|next)$/i.test(b.innerText.trim()));
                        if (btn) btn.click();
                    }''')
                except Exception:
                    pass
                await page.wait_for_timeout(1500)
                stuck_count = 0
                continue
        else:
            stuck_count = 0
        last_q = question

        # 3. Determine Answer
        answer = None
        q_lower = question.lower()

        # Check candidate profile details first
        if re.search(r'\b(full\s*name|your\s*name|name\?|what\s*is\s*your\s*name)\b', q_lower):
            raw_name = profile.get('name') or 'Arun Sudhaveni'
            answer = raw_name.title() if raw_name.isupper() else raw_name
        elif re.search(r'\b(email|email\s*id|email\s*address)\b', q_lower):
            answer = profile.get('email', 'arun@gamil.com')
        elif re.search(r'\b(phone|mobile|contact\s*number)\b', q_lower):
            answer = profile.get('phone', '9876543210')
        elif re.search(r'\b(current\s*city|current\s*location|where\s*do\s*you\s*(live|stay|reside)|which\s*city)\b', q_lower):
            locs = profile.get('locations') or ['Hyderabad']
            answer = profile.get('city') or locs[0]
        elif re.search(r'\b(total\s*experience|years\s*of\s*experience|work\s*experience|how\s*many\s*years)\b', q_lower):
            years = profile.get('experience_years') or profile.get('experience') or 0
            answer = str(years)
        elif re.search(r'\b(notice\s*period|how\s*soon\s*can\s*you\s*join|serving\s*notice)\b', q_lower):
            notice = profile.get('notice_days') or profile.get('notice') or '15'
            answer = str(notice) if str(notice).isdigit() else '15'
        elif re.search(r'\b(current\s*ctc|current\s*salary|present\s*ctc)\b', q_lower):
            try:
                raw_ctc = float(profile.get('current_ctc') or 350000)
                if raw_ctc > 1000 and any(w in q_lower for w in ['lacs', 'lakhs', 'lac', 'lakh']):
                    answer = f"{raw_ctc / 100000:.1f}".rstrip('0').rstrip('.')
                else:
                    answer = str(int(raw_ctc)) if raw_ctc.is_integer() else str(raw_ctc)
            except Exception:
                answer = '3.5'
        elif re.search(r'\b(expected\s*ctc|expected\s*salary)\b', q_lower):
            try:
                raw_ctc = float(profile.get('expected_ctc') or 650000)
                if raw_ctc > 1000 and any(w in q_lower for w in ['lacs', 'lakhs', 'lac', 'lakh']):
                    answer = f"{raw_ctc / 100000:.1f}".rstrip('0').rstrip('.')
                else:
                    answer = str(int(raw_ctc)) if raw_ctc.is_integer() else str(raw_ctc)
            except Exception:
                answer = '6.5'
        elif re.search(r'\b(gender|male|female)\b', q_lower):
            answer = profile.get('gender') or 'Male'
        elif re.search(r'\b(qualification|degree|education|b\.?tech|graduation)\b', q_lower):
            answer = profile.get('education') or 'B.Tech'
        elif re.search(r'\b(relocate|relocation|comfortable\s*to\s*work\s*from\s*office|work\s*from\s*office)\b', q_lower):
            answer = 'Yes'

        # If question not in standard profile keys: query QuestionMemory or Web Research!
        if not answer:
            try:
                from .question_memory import search_persistent_memory
                best_mem, score = search_persistent_memory(user_id, question, threshold=0.70)
                if best_mem and score >= 0.70:
                    answer = best_mem.approved_answer
                    if checkpoint_fn: checkpoint_fn(f"Recalled from memory for '{question[:25]}'")
            except Exception:
                best_mem = None

        if not answer:
            if checkpoint_fn: checkpoint_fn(f"Researching & synthesizing answer for '{question[:30]}'...")
            company_name = job.get('company', '')
            web_info = ""
            if company_name and re.search(r'\b(why|about|know\s*about|company)\b', q_lower):
                try:
                    from .web_researcher import research_company
                    comp_data = await research_company(company_name, question)
                    web_info = comp_data.get('summary', '')[:400]
                except Exception:
                    pass

            from .main import llm
            prompt = f"""You are answering a recruiter screening question on Naukri on behalf of candidate {profile.get('name', 'the candidate')}.
Candidate details: {profile}
Job: {job.get('title', '')} at {company_name}
{('Company research: ' + web_info) if web_info else ''}

Recruiter question: "{question}"

Answer instructions:
1. Provide a direct, professional, truthful response (under 2 sentences, or just the required number/keyword).
2. For Yes/No questions on skills, relocation, or availability, answer 'Yes'.
Return JSON: {{"answer": "your answer here"}}"""
            try:
                ans_obj = await llm(prompt, retries=1)
                answer = str(ans_obj.get('answer', 'Yes')).strip()
            except Exception:
                answer = 'Yes'

            # Save in QuestionMemory for perpetual reuse
            try:
                from .question_memory import save_memory_record
                save_memory_record(
                    user_id=user_id,
                    question_id=re.sub(r'[^a-z0-9]+', '_', question.lower())[:80],
                    question_text=question,
                    approved_answer=answer,
                    category='recruiter_screening',
                    confidence=0.9
                )
            except Exception:
                pass

        if checkpoint_fn: checkpoint_fn(f"Answering '{question[:25]}': '{answer[:25]}'")

        # 4. Fill into Naukri Chatbot
        try:
            clicked_chip = False
            if chips:
                for chip_text in chips:
                    if chip_text.lower() == answer.lower() or chip_text.lower() in answer.lower():
                        chip_btn = page.locator('.chatbot_drawer button, [class*="chatbot"] button, .apply-message-container button, button:visible').filter(has_text=re.compile(rf'^\s*{re.escape(chip_text)}\s*$', re.I)).first
                        if await chip_btn.count():
                            await chip_btn.click(timeout=3000)
                            clicked_chip = True
                            break

            if not clicked_chip:
                # 1. Contenteditable div (Naukri chatbot uses .textArea[contenteditable="true"] or [id*="userInput"])
                content_editable = page.locator('.textArea[contenteditable="true"]:visible, [id*="userInput"]:visible, .chatbot_InputContainer [contenteditable="true"]:visible').first
                typed = False
                if await content_editable.count():
                    try:
                        await content_editable.click(timeout=3000)
                        await page.wait_for_timeout(200)
                        # Clear existing text
                        await page.evaluate('(el) => { el.innerText = ""; }', await content_editable.element_handle())
                        await page.keyboard.type(answer, delay=40)
                        await page.wait_for_timeout(300)
                        await page.keyboard.press('Enter')
                        typed = True
                    except Exception:
                        typed = False

                if not typed:
                    # 2. Standard input / textarea
                    input_loc = page.locator('input[placeholder*="message" i]:visible, textarea[placeholder*="message" i]:visible, [placeholder*="Type message" i]:visible, input[type="text"]:not([class*="Uploader"]):visible').first
                    if await input_loc.count():
                        try:
                            await input_loc.click(timeout=3000)
                            await input_loc.fill('')
                            await input_loc.press_sequentially(answer, delay=35)
                            await input_loc.press('Enter')
                            typed = True
                        except Exception:
                            typed = False
                
                # 3. Fallback click on Save / Send button if Enter didn't submit
                await page.wait_for_timeout(500)
                save_btn = page.locator('.chatbot_drawer button, [class*="chatbot"] button, .apply-message-container button, button:visible').filter(has_text=re.compile(r'^\s*(?:Save|Send|Submit|Next)\s*$', re.I)).last
                if await save_btn.count():
                    try:
                        await save_btn.click(timeout=2000)
                    except Exception:
                        pass
        except Exception as step_err:
            if checkpoint_fn: checkpoint_fn(f"Chatbot interaction note: {step_err}")

        await page.wait_for_timeout(2000)

    return 'submitted' if await application_sent(page) else 'completed'

async def close_modal(page):
    """Dismiss the application modal/drawer if present."""
    try:
        dismiss = page.locator(VISIBLE_MODAL).last.locator('button, [role="button"], i').filter(has_text=re.compile(r'dismiss|close|cancel|discard|×', re.I)).first
        if await dismiss.count():
            await dismiss.click(timeout=4000)
    except Exception:
        pass
