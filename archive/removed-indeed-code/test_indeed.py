"""Indeed agent checks. No Indeed, Browserbase or OpenRouter traffic.

The browser tests drive the real platform_agent.execute_platform() and worker.run() in local Chromium
against an Indeed-shaped fake site whose https://www.indeed.com/** and https://smartapply.indeed.com/**
requests are answered locally. Own temporary database (via test_linkedin.Db).
"""
import asyncio, contextlib, os, tempfile, unittest
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(tempfile.gettempdir())/'orbit-test-indeed-unused.db').replace('\\','/'))
from playwright.async_api import async_playwright
from . import agent, indeed, main, platform_agent, services, worker
from .db import AgentRun, Application, Job, PlatformConnection, User, now
from .domain import fingerprint
from .test_linkedin import Db, PROFILE, assessment
from .test_worker import fake_pdf

SETTINGS={'source_focus':'indeed','matching':'fresher_ai','mode':'automatic','auto_enabled':True,'daily_limit':10,'threshold':70}

class UrlTests(unittest.TestCase):
    def test_search_urls_follow_the_profile(self):
        urls=indeed.search_urls(PROFILE)
        self.assertEqual(len(urls),1)
        for expected in ['q=AI+Engineer','l=Hyderabad%2C+India','sort=date','fromage=7']:self.assertIn(expected,urls[0])
    def test_country_only_search_drops_the_city(self):
        self.assertIn('l=India&',indeed.search_urls(PROFILE,country_only=True)[0])
    def test_any_location_drops_the_filter_entirely(self):
        self.assertNotIn('l=',indeed.search_urls(PROFILE,any_location=True)[0])
    def test_search_uses_the_profile_country_site(self):
        self.assertTrue(indeed.search_urls(PROFILE)[0].startswith('https://in.indeed.com/jobs?'))
        self.assertTrue(indeed.search_urls({**PROFILE,'country':'United States'})[0].startswith('https://www.indeed.com/jobs?'))
        self.assertEqual(indeed.canonical('https://in.indeed.com/rc/clk?jk=aaaa1111bbbb2222&x=1'),'https://in.indeed.com/viewjob?jk=aaaa1111bbbb2222')
    def test_roles_are_capped_at_five(self):
        self.assertEqual(len(indeed.search_urls({**PROFILE,'roles':'a,b,c,d,e,f,g'})),5)
    def test_one_canonical_url_per_vacancy(self):
        for url in ['https://www.indeed.com/viewjob?jk=aaaa1111bbbb2222','https://www.indeed.com/jobs?q=x&vjk=aaaa1111bbbb2222',
                    'https://www.indeed.com/rc/clk?jk=aaaa1111bbbb2222&bb=xyz&xkcb=abc']:
            self.assertEqual(indeed.canonical(url),'https://www.indeed.com/viewjob?jk=aaaa1111bbbb2222')
    def test_platform_hosts_include_the_apply_subdomain(self):
        ok=services.allowed_application_url
        self.assertTrue(ok('https://www.indeed.com/viewjob?jk=aaaa1111bbbb2222','Indeed'))
        self.assertTrue(ok('https://smartapply.indeed.com/beta/indeedapply/x','Indeed'))
        self.assertFalse(ok('https://www.indeed.com/viewjob?jk=aaaa1111bbbb2222','LinkedIn'))

JK1='aaaa1111bbbb2222';JK2='cccc3333dddd4444'
SEARCH=f'''<div id="results">
<a data-jk="{JK1}" class="jcs-JobTitle" href="/rc/clk?jk={JK1}"><span>AI Engineer</span></a>
<a data-jk="{JK2}" class="jcs-JobTitle" href="/rc/clk?jk={JK2}"><span>Machine Learning Engineer</span></a>
</div>'''
EXTERNAL_JOB='<main><h1>Machine Learning Engineer</h1><a role="button">Apply on company site</a></main>'
JOB=f'''<!DOCTYPE html><html><body>
<main><h1>AI Engineer</h1><p>Local Test Co - Hyderabad, India - $0 - $0 a year</p>
<p>Build LLM features with Python. Fresher friendly.</p>
<a role="button" id="apply">Apply now</a></main>
<script>
// A new tab, the trickier of the two real shapes "Apply now" can take (see indeed.open_easy_apply): it
// must be found, redirected onto, and closed so everything after happens back on the one shared tab.
document.getElementById('apply').onclick=e=>{{e.preventDefault();window.open('https://smartapply.indeed.com/beta/indeedapply/applybyapplyablejobid?indeedApplyableJobId={JK1}')}}
</script>
</body></html>'''
# Indeed's own apply flow: a plain full-page, multi-step form (no dialog/modal, unlike LinkedIn's Easy Apply).
APPLY_PAGE='''<!DOCTYPE html><html><body>
<div id="one"><h1>Contact info</h1>
<label>Mobile phone number<input name="phone" required></label>
<button type="button" id="n1">Continue</button></div>
<div id="two" hidden><h1>Screening questions</h1>
<fieldset><legend>Are you legally authorized to work in India?</legend>
 <input type="radio" name="auth" id="auth-yes" value="Yes"><label for="auth-yes">Yes</label>
 <input type="radio" name="auth" id="auth-no" value="No"><label for="auth-no">No</label></fieldset>
<label>How many years of experience do you have overall?<input name="exp" required></label>
<button type="button" id="submit">Submit application</button></div>
<h2 id="done" hidden>Thanks for applying!</h2>
<script>
document.getElementById('n1').onclick=()=>{one.hidden=true;two.hidden=false};
document.getElementById('submit').onclick=()=>{two.hidden=true;done.hidden=false};
</script></body></html>'''

def indeed_site(pages,contexts):
    """Local Chromium standing in for a Browserbase session; https://www.indeed.com/** and
    https://smartapply.indeed.com/** are answered from `pages`."""
    @contextlib.asynccontextmanager
    async def fake():
        async with async_playwright() as real:
            launched=[]
            async def connect_over_cdp(url,timeout=None):
                browser=await real.chromium.launch();launched.append(browser)
                context=await browser.new_context();contexts.append(context)
                async def fulfill(route):
                    for needle,html in pages:
                        if needle in route.request.url:await route.fulfill(status=200,content_type='text/html',body=html);return
                    await route.fulfill(status=404,body='not found')
                await context.route('https://www.indeed.com/**',fulfill)
                await context.route('https://in.indeed.com/**',fulfill)
                await context.route('https://smartapply.indeed.com/**',fulfill)
                return SimpleNamespace(contexts=[context],is_connected=lambda:True)
            try:yield SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=connect_over_cdp))
            finally:
                for browser in launched:await browser.close()
    return fake()

def indeed_form_model(seen):
    """Stands in for DeepSeek inside Indeed's own apply form."""
    async def plan(system,payload,max_tokens=0,**_):
        page=payload['page'];els=page['elements'];text=page['text'].lower();seen.append(page)
        def caption(e):return (e['label']+' '+e['text']).lower()
        def find(word):return next(e['id'] for e in els if word in caption(e))
        if 'contact info' in text:raise AssertionError('the contact step must be planned by rules, not the model')
        if 'screening questions' in text:
            yes=next(e['id'] for e in els if e['type']=='radio' and e['label'].strip().lower()=='yes' and 'authorized' in (e.get('group') or '').lower())
            return {'actions':[{'action':'choose','element_id':yes,'field_key':'authorization'},{'action':'fill','element_id':find('years of experience'),'field_key':'experience'},{'action':'submit','element_id':find('submit application')}]}
        raise AssertionError('unexpected step: '+text[:80])
    return plan

class AgentEndToEndTests(Db):
    """The whole run: search -> assess -> documents -> apply on the same tab -> next job -> complete."""
    def test_search_apply_and_skip_external_jobs(self):
        with self.Session() as db:
            db.add(User(id='u',email='e@example.invalid',password='x',profile=PROFILE,settings=SETTINGS));db.flush()
            db.add(AgentRun(id='r',user_id='u',status='running',phase='searching',events=[],state={'profile_hash':fingerprint(PROFILE)}));db.commit()
        # Order matters: the fake site matches the first needle found in the URL, so the specific job/apply
        # pages come before the search page (a job's canonical URL also contains "indeed.com/") and the
        # bare home page (checked for sign-in) comes last, as the least specific pattern of all.
        pages=[(f'jk={JK1}',JOB),(f'jk={JK2}',EXTERNAL_JOB),('smartapply.indeed.com',APPLY_PAGE),
               ('indeed.com/jobs?q=',SEARCH),('indeed.com/','<main><h1>Indeed</h1></main>')]
        contexts=[];worker_seen=[];released=[]
        async def released_session(_):released.append(1)
        async def assess(system,payload,max_tokens=0,**_):return assessment()
        async def package(profile,job,demo=False,**_):return {'resume':PROFILE['resume_text'],'cover_letter':'Synthetic cover letter.','notes':[],'answers':{}}
        async def session(user_id,proxies=False):return {'id':'s','connectUrl':'local','live_url':'https://live.example/x'}
        env={'OPENROUTER_API_KEY':'test','BROWSERBASE_API_KEY':'test'}
        patches=[patch.dict(os.environ,env),patch.object(platform_agent,'random',SimpleNamespace(uniform=lambda a,b:0.01)),
                 patch.object(platform_agent,'async_playwright',partial(indeed_site,pages,contexts)),patch.object(worker,'async_playwright',partial(indeed_site,pages,contexts)),
                 patch.object(platform_agent,'llm',assess),patch.object(platform_agent,'generate_package',package),patch.object(platform_agent,'user_browser_session',session),
                 patch.object(platform_agent,'release_browser',released_session),patch.object(worker,'release_browser',released_session),
                 patch.object(worker,'llm',indeed_form_model(worker_seen)),patch('backend.career_ops_documents.pdf_bytes',fake_pdf)]
        patches+=[patch.object(module,'Session',self.Session) for module in (agent,platform_agent,main,worker)]
        with contextlib.ExitStack() as stack:
            for p in patches:stack.enter_context(p)
            async def go():await asyncio.wait_for(platform_agent.execute_platform('r','Indeed'),timeout=120)
            asyncio.run(go())
        with self.Session() as db:
            run=db.get(AgentRun,'r');apps=db.query(Application).all();jobs=db.query(Job).all()
            texts=[e['text'] for e in run.events]
            self.assertEqual(run.status,'completed',texts)
            self.assertEqual([a.status for a in apps],['submitted'],texts)
            self.assertEqual([j.payload['source'] for j in jobs],['Indeed'])
            self.assertEqual(jobs[0].payload['url'],f'https://in.indeed.com/viewjob?jk={JK1}')
            self.assertTrue(any('applies on the employer site, not on Indeed' in t for t in texts),texts)
            self.assertTrue(any('Employer confirmation' in e for e in [ev['text'] for a in apps for ev in a.events]),
                             [ev['text'] for a in apps for ev in a.events])
            # One tab throughout: Indeed's apply flow (a real navigation, sometimes a new tab) must collapse
            # back onto the single discovery tab, exactly like the LinkedIn flow.
            self.assertEqual(len(contexts),1)
            # The run seeing the person past Indeed's sign-in wall also satisfies the "Connect your
            # accounts" gate, so a returning user is never asked to sign in twice.
            connection=db.query(PlatformConnection).filter_by(user_id='u',platform='Indeed').first()
            self.assertTrue(connection and connection.connected)

if __name__=='__main__':unittest.main()
