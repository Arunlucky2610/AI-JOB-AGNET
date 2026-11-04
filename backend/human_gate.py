"""Detect visible authentication gates without reading credential values."""
LOGIN_PROBE = r"""() => {
    const visible=e => !!(e.getClientRects().length && getComputedStyle(e).visibility!=='hidden' && getComputedStyle(e).display!=='none');
    const inputs=Array.from(document.querySelectorAll('input')).filter(visible);
    if(inputs.some(e=>e.type==='password')) return true;
    // LinkedIn's own sign-in walls and security checks need the person, not the agent.
    if(/(^|\.)linkedin\.com$/.test(location.hostname) && /^\/(checkpoint|authwall|uas\/|login|signup)/.test(location.pathname)) return true;
    // Indeed's sign-in and auth pages need the person, not the agent.
    if(/(^|\.)indeed\.com$/.test(location.hostname) && (/^\/(auth|account\/login|account\/register)/.test(location.pathname) || location.hostname.startsWith('secure.indeed.'))) return true;
    // Naukri's sign-in, auth and otp pages need the person, not the agent.
    if(/(^|\.)naukri\.com$/.test(location.hostname) && (/^\/(nlogin|login|registration|otp)/.test(location.pathname) || location.hostname.startsWith('login.naukri.'))) return true;
    // Internshala sign-in, registration and login modal gates need the person, not the agent.
    if(/(^|\.)internshala\.com$/.test(location.hostname) && (/^\/(login\/user|registration\/student|login\/google|login|registration)/.test(location.pathname) || !!document.querySelector('#modal__login, #login-modal, #email, #password, form#login_form'))) return true;
    if(inputs.some(e=>e.autocomplete==='one-time-code')) return true;
    const login=/\b(sign[\s-]*in|log[\s-]*in|login|create an account|verify your email)\b/i;
    const dialogs=Array.from(document.querySelectorAll('[role="dialog"],dialog[open]')).filter(visible);
    if(dialogs.some(e=>login.test(e.querySelector('h1,h2,h3,[role="heading"]')?.innerText||'') && e.querySelector('input,button'))) return true;
    const text=document.body.innerText;
    const authPath=/(?:^|\/)(?:login\d*|signin|sign-in|log-in|auth|authenticate|register)(?:\/|$)/i.test(location.pathname);
    const emailOnly=inputs.some(e=>e.type==='email'||/email|username/i.test((e.name||'')+' '+(e.id||'')+' '+(e.getAttribute('aria-label')||''))) && !inputs.some(e=>/first.?name|last.?name|full.?name|resume|phone/i.test((e.name||'')+' '+(e.id||'')+' '+(e.getAttribute('aria-label')||'')));
    const loginButton=Array.from(document.querySelectorAll('button,input[type="submit"]')).filter(visible).some(e=>/^(sign[\s-]*in|log[\s-]*in|login|sign[\s-]*in with (google|microsoft)|send me a sign[\s-]*in link|continue with (google|microsoft|email))$/i.test((e.innerText||e.value||'').trim()));
    return (authPath && login.test(text)) || (emailOnly && loginButton);
}"""

async def login_required(page):
    return await page.evaluate(LOGIN_PROBE)

# Bot checks (Cloudflare and similar "verify you are human" pages): the person solves these in Live View.
CHALLENGE_PROBE = r"""() => {
    if(/^(just a moment|blocked|attention required|security check)/i.test(document.title)) return true;
    if(document.querySelector('iframe[src*="challenges.cloudflare.com"],#challenge-form,#cf-challenge-running,.cf-turnstile,#cf-wrapper')) return true;
    return /\b(verify you are human|additional verification required|checking your browser|verifying you are human|access denied|you have been blocked)\b/i.test((document.body&&document.body.innerText||'').slice(0,3000));
}"""

async def challenge_shown(page):
    try:return await page.evaluate(CHALLENGE_PROBE)
    except Exception:return False
