"""LinkedIn agent checks. No LinkedIn, Browserbase or OpenRouter traffic.

The browser tests drive the real platform_agent.execute_platform() and worker.run() in local Chromium against a
LinkedIn-shaped fake site whose https://www.linkedin.com/** requests are answered locally. Own temporary database.
"""
import asyncio, contextlib, os, tempfile, unittest
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(tempfile.gettempdir())/'orbit-test-linkedin-unused.db').replace('\\','/'))
from playwright.async_api import async_playwright
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from . import agent, linkedin, main, orchestrator, platform_agent, services, worker
from .db import Base, User, Job, Application, AgentRun, now
from .domain import DEMO_PROFILE, fingerprint, career_level, evaluate
from .test_worker import fake_pdf, serve

PROFILE={**DEMO_PROFILE,'phone':'+91 90000 00000','country':'India','locations':'Hyderabad','roles':'AI Engineer','authorization':'Yes','sponsorship':'No','experience':0,'no_experience':True,'confirmed':True}
# What execute_platform builds for fresher_ai matching: city and work mode are preferences only.
RELAXED_PROFILE={**PROFILE,'roles':'AI Engineer, Machine Learning Engineer, Generative AI Engineer','strict_location':False,'strict_mode':False,'work_modes':['Remote','Hybrid','Onsite']}
SETTINGS={'source_focus':'linkedin','matching':'fresher_ai','mode':'automatic','auto_enabled':True,'daily_limit':10}

class UrlAndAllowListTests(unittest.TestCase):
    def test_search_urls_follow_the_profile_and_ask_for_easy_apply(self):
        urls=linkedin.search_urls(PROFILE)
        self.assertEqual(len(urls),1)
        for expected in ['keywords=AI+Engineer','location=Hyderabad%2C+India','f_AL=true','f_E=1%2C2','sortBy=DD']:self.assertIn(expected,urls[0])
    def test_country_only_search_drops_the_city(self):
        self.assertIn('location=India&',linkedin.search_urls(PROFILE,country_only=True)[0])
    def test_any_location_drops_the_filter_entirely(self):
        url=linkedin.search_urls(PROFILE,any_location=True)[0]
        self.assertNotIn('location=',url);self.assertIn('keywords=AI+Engineer',url)
    def test_any_location_wins_even_if_country_only_is_also_set(self):
        self.assertNotIn('location=',linkedin.search_urls(PROFILE,country_only=True,any_location=True)[0])
    def test_experienced_profiles_get_experienced_levels(self):
        self.assertEqual(linkedin.experience_levels({'experience':2}),'2,3');self.assertEqual(linkedin.experience_levels({'experience':5}),'3,4')
    def test_roles_are_capped_at_five(self):
        self.assertEqual(len(linkedin.search_urls({**PROFILE,'roles':'a,b,c,d,e,f,g'})),5)
    def test_one_canonical_url_per_vacancy(self):
        for url in ['https://www.linkedin.com/jobs/view/3912345678/','https://www.linkedin.com/jobs/view/ai-engineer-at-acme-3912345678?trackingId=x&refId=y','https://in.linkedin.com/jobs/view/3912345678/?alternateChannel=search']:
            self.assertEqual(linkedin.canonical(url),'https://www.linkedin.com/jobs/view/3912345678/')
    def test_platform_hosts_are_only_allowed_for_platform_jobs(self):
        ok=services.allowed_application_url
        self.assertTrue(ok('https://www.linkedin.com/jobs/view/3912345678/','LinkedIn'))
        self.assertTrue(ok('https://in.linkedin.com/jobs/view/3912345678/','LinkedIn'))
        self.assertFalse(ok('https://www.linkedin.com/jobs/view/3912345678/'),'employer-portal jobs must still exclude aggregators')
        self.assertFalse(ok('https://www.linkedin.com/jobs/view/3912345678/','Indeed'))
        self.assertFalse(ok('https://evil.example/linkedin.com','LinkedIn'))
        self.assertFalse(ok('https://linkedin.com.evil.example/jobs','LinkedIn'))
        self.assertFalse(ok('http://www.linkedin.com/jobs/view/3912345678/','LinkedIn'))

    def test_linkedin_login_with_credentials_flow(self):
        class MockLoc:
            def __init__(self, count_val=1):
                self._c = count_val
                self.first = self
            async def count(self): return self._c
            async def wait_for(self, **kwargs): pass
            async def click(self, **kwargs): pass
            async def fill(self, text, **kwargs): pass
            async def type(self, text, **kwargs): pass
            async def press(self, key, **kwargs): pass

        class MockPage:
            def __init__(self):
                self.url = 'https://www.linkedin.com/login'
                self._signed_in = False
            async def goto(self, url, **kwargs):
                self.url = url
            async def wait_for_timeout(self, ms): pass
            async def evaluate(self, expr, *args):
                return False
            def locator(self, sel):
                if '.global-nav' in sel:
                    return MockLoc(1 if self._signed_in else 0)
                if 'button[type="submit"]' in sel or 'login-submit' in sel:
                    parent = self
                    class SubmitLoc(MockLoc):
                        async def click(self, **kwargs):
                            parent._signed_in = True
                            parent.url = 'https://www.linkedin.com/feed/'
                    return SubmitLoc(1)
                return MockLoc(1)

        p = MockPage()
        res = asyncio.run(linkedin.login_with_credentials(p, 'user@example.com', 'mypassword'))
        self.assertTrue(res)

def assessment(**over):
    row={'requirement':'Python','importance':'high','tier':'stated','jd_evidence':'Python','profile_evidence':'','match':'strong'}
    base={'is_job':True,'closed':False,'sponsorship_supported':None,'title':'AI Engineer','company':'Local Test Co','location':'Hyderabad, India','country':'India','mode':'Onsite','min_experience':None,'skills':['Python'],'salary':'','description':'Build LLM features with Python. Fresher friendly.','role_matches':True,'score':82,'matched_skills':['Python'],'missing_skills':[],'blockers':[],'unknown':[],'explanation':'Good fit.','sponsorship':None,
          'evaluation':{'A':'a','B':[row],'C':'c','D':'d','E':'e','F':'f','G':'g','H':'h'},'global_score':4.0}
    return {**base,**over}

class AssessmentTests(unittest.TestCase):
    def build(self,**over):
        return platform_agent.build_job(assessment(**over),RELAXED_PROFILE,SETTINGS,True,'https://www.linkedin.com/jobs/view/ai-engineer-3912345678?trk=x','Build LLM features with Python. Fresher friendly.')
    def test_a_fitting_fresher_job_is_matched_and_keyed_by_its_canonical_url(self):
        job=self.build();self.assertTrue(job['match']['matched'],job['match'])
        self.assertEqual((job['source'],job['url']),('LinkedIn','https://www.linkedin.com/jobs/view/3912345678/'))
    def test_a_poor_fit_is_not_applied_to(self):
        job=self.build(score=3);self.assertFalse(job['match']['matched'])
        self.assertTrue(any('below your 60% minimum' in b for b in job['match']['blockers']),job['match']['blockers'])
    def test_the_fit_floor_is_inclusive(self):
        self.assertFalse(self.build(score=59)['match']['matched']);self.assertTrue(self.build(score=60)['match']['matched'])
    def test_wrong_country_is_a_blocker(self):
        job=self.build(country='United States');self.assertFalse(job['match']['matched']);self.assertIn('Target country does not match',job['match']['blockers'])
    def test_explicit_sponsorship_exclusion_blocks_when_sponsorship_is_needed(self):
        profile={**RELAXED_PROFILE,'sponsorship':'Yes'}
        job=platform_agent.build_job(assessment(sponsorship_supported=False),profile,SETTINGS,True,'https://www.linkedin.com/jobs/view/3912345678/','Python')
        self.assertFalse(job['match']['matched'])
    def test_unstated_sponsorship_is_only_a_review_note_when_needed(self):
        profile={**RELAXED_PROFILE,'sponsorship':'Yes'}
        job=platform_agent.build_job(assessment(),profile,SETTINGS,True,'https://www.linkedin.com/jobs/view/3912345678/','Python')
        self.assertTrue(job['match']['matched']);self.assertTrue(job['match']['review_notes'])
    def test_incomplete_evidence_is_rejected(self):
        with self.assertRaises(ValueError):self.build(description='')
    def test_a_person_open_to_any_country_overrides_relaxed_matchings_default(self):
        # Relaxed (fresher) matching still enforces country by default (test_wrong_country_is_a_blocker), but
        # a person who explicitly says any country is fine is trusted over that default, not overridden by it.
        profile={**RELAXED_PROFILE,'strict_country':False}
        job=platform_agent.build_job(assessment(country='United States'),profile,SETTINGS,True,'https://www.linkedin.com/jobs/view/3912345678/','Build LLM features with Python. Fresher friendly.')
        self.assertTrue(job['match']['matched'],job['match']);self.assertNotIn('Target country does not match',job['match']['blockers'])

class LocationScopeTests(unittest.TestCase):
    """strict_location (city) and strict_country are independent: either can be relaxed without the other."""
    JOB={'title':'AI Engineer','country':'United States','location':'Austin, United States','mode':'Onsite'}
    def test_default_profile_enforces_both_city_and_country(self):
        result=evaluate(PROFILE,self.JOB)
        self.assertIn('Target country does not match',result['blockers']);self.assertIn('Preferred location does not match',result['blockers'])
    def test_any_city_still_requires_the_right_country(self):
        result=evaluate({**PROFILE,'strict_location':False},self.JOB)
        self.assertIn('Target country does not match',result['blockers']);self.assertNotIn('Preferred location does not match',result['blockers'])
    def test_any_country_also_stops_checking_the_city(self):
        # A city preference is meaningless once any country is acceptable; it is never checked on its own.
        result=evaluate({**PROFILE,'strict_country':False},self.JOB)
        self.assertNotIn('Target country does not match',result['blockers']);self.assertNotIn('Preferred location does not match',result['blockers'])
    def test_a_remote_job_is_never_blocked_on_city_regardless_of_the_toggle(self):
        result=evaluate(PROFILE,{**self.JOB,'country':'India','mode':'Remote'})
        self.assertNotIn('Preferred location does not match',result['blockers'])

SEARCH='<ul><li data-occludable-job-id="111111111">A</li><li data-occludable-job-id="222222222">B</li></ul>'
EXTERNAL_JOB='<main><h1>AI Engineer</h1><a href="#">Apply</a></main>'
PAGE_TOP='''<!DOCTYPE html><html><body>
<nav><a href="#">Home</a><a href="#">My Network</a><button>Start a post</button><button>Messaging</button></nav>
<main><h1>AI Engineer</h1><p>Local Test Co - Hyderabad, India - Entry level</p><p>Build LLM features with Python. Fresher friendly.</p>
<a id="easy" role="button" href="/jobs/view/1/apply/?openSDUIApplyFlow=true" onclick="return false"><span>Easy Apply</span></a></main>'''
MODAL_HTML='''<div id="modal" role="dialog" class="artdeco-modal jobs-easy-apply-modal" hidden>
 <button aria-label="Dismiss" id="dismiss">X</button>
 <div id="s1"><h2>Contact info</h2><label>Mobile phone number<input name="phone" required></label><button type="button" id="n1">Next</button></div>
 <div id="s2" hidden><h2>Additional questions</h2>
  <fieldset><legend>Are you legally authorized to work in India?</legend>
   <input type="radio" name="auth" id="auth-yes" value="Yes" style="position:absolute;opacity:0"><label for="auth-yes">Yes</label>
   <input type="radio" name="auth" id="auth-no" value="No" style="position:absolute;opacity:0"><label for="auth-no">No</label></fieldset>
  <label>How many years of experience do you have overall?<input name="exp" required></label>
  <button type="button" id="n2">Review</button></div>
 <div id="s3" hidden><h2>Review your application</h2><p id="summary"></p><button type="button" id="submit">Submit application</button></div>
 <div id="sent" hidden><h2>Application sent</h2><p>Your application was sent to Local Test Co</p></div>
</div>
<div id="confirm" role="dialog" hidden><button id="discard">Discard</button><button id="save">Save</button></div>'''
SCRIPT='''<script>
const root=%(root)s;
const $=id=>root.getElementById(id);
window.answers={};
document.getElementById('easy').addEventListener('click',()=>{$('modal').hidden=false});
$('n1').onclick=()=>{answers.phone=root.querySelector('[name=phone]').value;$('s1').hidden=true;$('s2').hidden=false};
$('n2').onclick=()=>{answers.auth=root.querySelector('[name=auth]:checked')?.value;answers.exp=root.querySelector('[name=exp]').value;$('summary').textContent='auth='+answers.auth+' exp='+answers.exp+' phone='+answers.phone;$('s2').hidden=true;$('s3').hidden=false};
$('submit').onclick=()=>{$('sent').querySelector('h2').textContent='Application sent - '+$('summary').textContent;$('s3').hidden=true;$('sent').hidden=false;window.applied=true};
$('dismiss').onclick=()=>{$('confirm').hidden=false};
$('discard').onclick=()=>{$('modal').hidden=true;$('confirm').hidden=true};
</script></body></html>'''

def job_page(shadow=False):
    """LinkedIn-shaped job page. shadow=True renders the application dialog inside a shadow root, as the real site does."""
    if shadow:
        return PAGE_TOP+'<div id="interop-outlet"></div><script>const shadowRoot=document.getElementById("interop-outlet").attachShadow({mode:"open"});shadowRoot.innerHTML=`'+MODAL_HTML+'`;</script>'+SCRIPT%{'root':'shadowRoot'}
    return PAGE_TOP+MODAL_HTML+SCRIPT%{'root':'document'}
JOB=job_page(False)
JOB_SHADOW=job_page(True)
PAGES=[('normal DOM',JOB),('shadow DOM',JOB_SHADOW)]

def linkedin_model(seen,unanswerable=False):
    """Stands in for DeepSeek inside the Easy Apply dialog."""
    async def plan(system,payload,max_tokens=0,**_):
        page=payload['page'];els=page['elements'];text=page['text'].lower();seen.append(page)
        def caption(e):return (e['label']+' '+e['text']).lower()
        def find(word):return next(e['id'] for e in els if word in caption(e))
        if 'contact info' in text or 'review your application' in text:raise AssertionError('routine steps must be planned by rules, not the model')
        if 'contact info' in text:
            return {'actions':[{'action':'fill','element_id':find('mobile phone'),'field_key':'phone_national'},{'action':'click','element_id':find('next')}]}
        if 'additional questions' in text:
            if unanswerable:return {'actions':[{'action':'need_human','reason':'Asks for a portfolio link the profile does not have.'}]}
            yes=next(e['id'] for e in els if e['type']=='radio' and e['label'].strip().lower()=='yes' and 'authorized' in (e.get('group') or '').lower())
            return {'actions':[{'action':'choose','element_id':yes,'field_key':'authorization'},{'action':'fill','element_id':find('years of experience'),'field_key':'experience'},{'action':'click','element_id':find('review')}]}
        return {'actions':[{'action':'submit','element_id':find('submit application')}]}
    return plan

def linkedin_site(pages,contexts,tabs_opened=None):
    """Local Chromium standing in for a Browserbase session; https://www.linkedin.com/** is answered from `pages`.
    `tabs_opened`, if given, is appended to once per tab ever opened in the session (so a test can check that
    discovery and applying really share one tab, not one each)."""
    @contextlib.asynccontextmanager
    async def fake():
        async with async_playwright() as real:
            launched=[]
            async def connect_over_cdp(url,timeout=None):
                browser=await real.chromium.launch();launched.append(browser)
                context=await browser.new_context();contexts.append(context)
                if tabs_opened is not None:context.on('page',lambda p:tabs_opened.append(p))
                async def fulfill(route):
                    for needle,html in pages:
                        if needle in route.request.url:await route.fulfill(status=200,content_type='text/html',body=html);return
                    await route.fulfill(status=404,body='not found')
                await context.route('https://www.linkedin.com/**',fulfill)
                return SimpleNamespace(contexts=[context],is_connected=lambda:True)
            try:yield SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=connect_over_cdp))
            finally:
                for browser in launched:await browser.close()
    return fake()

class Db(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.engine=create_engine('sqlite:///'+str(Path(self.dir.name)/'l.db').replace('\\','/'),connect_args={'check_same_thread':False})
        Base.metadata.create_all(self.engine);self.Session=sessionmaker(bind=self.engine,expire_on_commit=False)
    def tearDown(self):
        self.engine.dispose();self.dir.cleanup()

class WorkerOnLinkedInTests(Db):
    def apply(self,html,model,shared=False,before=None,profile=None):
        package={'resume':PROFILE['resume_text'],'cover_letter':'Synthetic cover letter.','notes':[],'answers':{}}
        seen=[];released=[];pages=[];answers={}
        with serve(html) as url:
            job={'title':'AI Engineer','company':'Local Test Co','description':'x','url':url,'source':'LinkedIn'}
            with self.Session() as db:
                for model_class in (AgentRun,Application,Job,User):db.query(model_class).delete()
                db.commit()
                db.add(User(id='u',email='l@example.invalid',password='x',profile=profile or PROFILE,settings=SETTINGS));db.flush()
                db.add(Job(id='j',user_id='u',canonical=url,payload=job));db.flush()
                db.add(Application(id='a',user_id='u',job_id='j',status='running',package=package,approved_hash=None,events=[],browser={'connect_url':'local','session_id':'s','navigated':False,'shared':shared}));db.commit()
            async def released_session(_):released.append(1)
            contexts=[]
            with patch.object(worker,'Session',self.Session),patch.object(worker,'async_playwright',partial(linkedin_site,[],contexts)),patch.object(worker,'llm',model(seen)),patch('backend.career_ops_documents.pdf_bytes',fake_pdf),patch.object(worker,'allowed_application_url',lambda u,s=None:True),patch.object(worker,'release_browser',released_session):
                asyncio.run(worker.run('a'))
        with self.Session() as db:return db.get(Application,'a'),seen,released
    # Every dialog test runs against the dialog in the normal DOM and inside a shadow root, as on the real site.
    def test_easy_apply_dialog_is_completed_and_confirmed(self):
        for name,html in PAGES:
            with self.subTest(name):
                # Automatic mode is on, so no exact-package approval is needed.
                a,seen,_=self.apply(html,lambda s:linkedin_model(s))
                self.assertEqual(a.status,'submitted',[e['text'] for e in a.events])
                self.assertTrue(any('Employer confirmation' in e['text'] and 'sent' in e['text'].lower() for e in a.events))
                self.assertEqual(len(seen),1,'the model plans only the questions step')
                self.assertIn('additional questions',seen[0]['text'].lower())
                self.assertTrue(any('by rules, no model call' in e['text'] for e in a.events),'contact and review steps are planned by rules')
    def test_the_dialog_answers_actually_land_in_the_form(self):
        for name,html in PAGES:
            with self.subTest(name):
                _,seen,_=self.apply(html,lambda s:linkedin_model(s))
                # The phone goes in without its +91, the radio is ticked, the experience answer is typed.
                a,_,_=self.apply(html,lambda s:linkedin_model(s))
                self.assertTrue(any('auth=Yes exp=0 phone=90000 00000' in e['text'] for e in a.events),[e['text'] for e in a.events])
    def test_only_the_dialog_is_offered_to_the_model(self):
        for name,html in PAGES:
            with self.subTest(name):
                _,seen,_=self.apply(html,lambda s:linkedin_model(s))
                offered=str([e['label']+' '+e['text'] for snap in seen for e in snap['elements']])
                for outside in ['Start a post','Messaging','My Network']:self.assertNotIn(outside,offered)
                self.assertTrue(seen[0]['elements'],'the dialog controls must be found, including inside a shadow root')
    def test_radio_question_and_state_are_visible_to_the_model(self):
        for name,html in PAGES:
            with self.subTest(name):
                _,seen,_=self.apply(html,lambda s:linkedin_model(s))
                radios=[e for e in seen[0]['elements'] if e['type']=='radio']
                self.assertEqual(len(radios),2);self.assertTrue(all('authorized to work in India' in e['group'] for e in radios));self.assertTrue(all(e['checked'] is False for e in radios))
    def test_unanswerable_question_skips_the_job_and_closes_the_dialog(self):
        for name,html in PAGES:
            with self.subTest(name):
                a,_,_=self.apply(html,lambda s:linkedin_model(s,unanswerable=True))
                self.assertEqual(a.status,'stopped');self.assertTrue(a.events[-1]['text'].startswith('Skipped:'),a.events[-1]['text'])
                self.assertIn('portfolio',a.events[-1]['text'])
    def test_job_without_easy_apply_is_skipped_not_paused(self):
        a,_,_=self.apply(EXTERNAL_JOB,lambda s:linkedin_model(s))
        self.assertEqual(a.status,'stopped');self.assertIn('Easy Apply',a.events[-1]['text'])
    def test_a_shared_session_is_never_released_by_the_worker(self):
        a,_,released=self.apply(JOB,lambda s:linkedin_model(s),shared=True)
        self.assertEqual(a.status,'submitted');self.assertEqual(released,[])
    def test_an_own_session_is_released_after_submission(self):
        a,_,released=self.apply(JOB,lambda s:linkedin_model(s),shared=False)
        self.assertEqual((a.status,released),('submitted',[1]))

class CareerStageTests(unittest.TestCase):
    def test_it_is_worked_out_from_experience_when_not_chosen(self):
        self.assertEqual(career_level({'no_experience':True}),'fresher');self.assertEqual(career_level({'experience':0}),'fresher')
        self.assertEqual(career_level({'experience':1}),'fresher');self.assertEqual(career_level({'experience':3}),'experienced')
    def test_the_persons_own_choice_wins(self):
        self.assertEqual(career_level({'career_level':'Intern','experience':5}),'intern')
        self.assertEqual(career_level({'career_level':'experienced','no_experience':True}),'experienced')
        self.assertEqual(career_level({'career_level':'Fresher / entry level'}),'fresher')
    def test_an_unknown_choice_falls_back_to_experience(self):
        self.assertEqual(career_level({'career_level':'astronaut','experience':6}),'experienced')
    def test_search_levels_follow_the_stage(self):
        self.assertEqual(linkedin.experience_levels({'career_level':'Intern','experience':9}),'1,2')
        self.assertEqual(linkedin.experience_levels({'career_level':'Experienced','no_experience':True,'experience':2}),'2,3')
    def test_roles_are_widened_for_juniors_only(self):
        wide=platform_agent.platform_profile(PROFILE,True);self.assertIn('Python Developer',wide['roles']);self.assertIn('Machine Learning Engineer',wide['roles'])
        narrow=platform_agent.platform_profile({**PROFILE,'career_level':'Experienced','experience':4,'no_experience':False},True)
        self.assertNotIn('Python Developer',narrow['roles']);self.assertIn('Generative AI Engineer',narrow['roles'])
        self.assertIs(platform_agent.platform_profile(PROFILE,False),PROFILE)
    def test_juniors_get_five_searches_and_others_three(self):
        self.assertEqual(len(linkedin.search_urls(platform_agent.platform_profile(PROFILE,True),country_only=True)),5)
        self.assertEqual(len(linkedin.search_urls(platform_agent.platform_profile({**PROFILE,'career_level':'Experienced','experience':4,'no_experience':False},True),country_only=True)),3)
    def test_the_prompt_widens_only_for_juniors(self):
        self.assertIn('junior software',platform_agent.relaxed_prompt(PROFILE))
        self.assertNotIn('junior software',platform_agent.relaxed_prompt({**PROFILE,'career_level':'Experienced','no_experience':False,'experience':4}))
    def test_the_profile_accepts_the_new_field(self):
        from .domain import EMPTY_PROFILE
        self.assertEqual(EMPTY_PROFILE['career_level'],'')

class SavedProfileTests(unittest.TestCase):
    def open_session(self,refuse):
        """user_browser_session with a fake Browserbase that refuses the old saved profile when `refuse`."""
        asked=[]
        async def context_id(user_id,fresh=False):
            asked.append('fresh' if fresh else 'saved');return 'new-profile' if fresh else 'old-profile'
        async def session(proxies=False,context_id=None):
            if refuse and context_id=='old-profile':raise services.HTTPException(refuse,'refused')
            return {'id':'s','connectUrl':'x','live_url':'y','profile':context_id}
        with patch.object(services,'user_context_id',context_id),patch.object(services,'browser_session',session):
            try:result=asyncio.run(services.user_browser_session('u'))
            except services.HTTPException as error:result=error
        return result,asked
    def test_a_saved_profile_that_works_is_reused(self):
        result,asked=self.open_session(refuse=None)
        self.assertEqual((result['profile'],asked),('old-profile',['saved']))
    def test_a_profile_from_another_account_is_replaced_once(self):
        result,asked=self.open_session(refuse=502)
        self.assertEqual((result['profile'],asked),('new-profile',['saved','fresh']))
    def test_a_billing_error_is_never_retried_or_hidden(self):
        result,asked=self.open_session(refuse=402)
        self.assertEqual((result.status_code,asked),(402,['saved']))

class OwnRolesTests(unittest.TestCase):
    def test_a_non_tech_goal_is_never_searched_as_ai_engineer(self):
        roles=platform_agent.platform_profile({**PROFILE,'roles':'Marketing Executive'},True)['roles']
        self.assertEqual(roles,'Marketing Executive')
    def test_the_persons_roles_come_first_and_are_kept(self):
        roles=platform_agent.platform_profile({**PROFILE,'roles':'Data Analyst'},True)['roles'].split(', ')
        self.assertEqual(roles[0],'Data Analyst');self.assertIn('Python Developer',roles);self.assertNotIn('Generative AI Engineer',roles)
    def test_no_roles_falls_back_to_ai(self):
        self.assertIn('AI Engineer',platform_agent.platform_profile({**PROFILE,'roles':''},True)['roles'])
    def test_titles_follow_the_persons_goal(self):
        profile={**PROFILE,'roles':'Marketing Executive'}
        self.assertIsNone(platform_agent.title_skip_reason('Digital Marketing Executive',profile,True))
        self.assertIn('target roles',platform_agent.title_skip_reason('Data Analyst Trainee',profile,True))

class TitleFilterTests(unittest.TestCase):
    skip=staticmethod(platform_agent.title_skip_reason)
    def test_ai_titles_pass_for_a_fresher(self):
        for title in ['Artificial Intelligence Engineer','AI/ML Engineer I','Generative AI Engineer','Machine Learning Intern','Data Scientist - NLP']:
            self.assertIsNone(self.skip(title,RELAXED_PROFILE,True),title)
    def test_a_missing_title_is_left_to_the_model(self):
        self.assertIsNone(self.skip('',RELAXED_PROFILE,True));self.assertIsNone(self.skip('   ',RELAXED_PROFILE,True))
    def test_interns_and_freshers_also_see_junior_software_roles(self):
        for title in ['Python Developer Intern','Software Engineer','Data Analyst Trainee','Software Engineering Intern - Bali','Graduate Backend Developer']:
            self.assertIsNone(self.skip(title,RELAXED_PROFILE,True),title)
    def test_experienced_people_in_fresher_mode_still_see_only_ai_titles(self):
        experienced={**RELAXED_PROFILE,'career_level':'Experienced','no_experience':False,'experience':4}
        self.assertIsNone(self.skip('Machine Learning Engineer',experienced,True));self.assertIn('not an AI/ML',self.skip('Software Engineer',experienced,True))
    def test_unrelated_titles_are_skipped_before_a_model_call(self):
        for title in ['Product Designer','Sales Executive','Accountant']:self.assertIn('not an AI/ML',self.skip(title,RELAXED_PROFILE,True))
    def test_senior_titles_are_skipped_for_a_fresher_only(self):
        self.assertIn('senior',self.skip('Senior AI Engineer',RELAXED_PROFILE,True))
        self.assertIn('senior',self.skip('Lead Machine Learning Engineer',RELAXED_PROFILE,True))
        self.assertIsNone(self.skip('Senior AI Engineer',{**RELAXED_PROFILE,'no_experience':False,'experience':8},True))
    def test_strict_matching_uses_the_profiles_own_roles(self):
        profile={**PROFILE,'roles':'Frontend Engineer'}
        self.assertIsNone(self.skip('Frontend Engineer - React',profile,False))
        self.assertIn('target roles',self.skip('Backend Engineer',profile,False))

class PopupTests(unittest.TestCase):
    def open_popup(self,target,host):
        """Click a button that opens `target` in a popup; returns (notifications, urls still open)."""
        async def go():
            async with async_playwright() as p:
                browser=await p.chromium.launch();context=await browser.new_context()
                async def fulfill(route):await route.fulfill(status=200,content_type='text/html',body='<h1>popup</h1>')
                await context.route(f'https://{host}/**',fulfill)
                notes=[];platform_agent.watch_popups(context,lambda:notes.append(1))
                page=await context.new_page()
                await page.set_content(f'<button id="b" onclick="window.open(\'{target}\')">Open</button>')
                await page.click('#b');await page.wait_for_timeout(1500)
                urls=[tab.url for tab in context.pages];await browser.close();return notes,urls
        return asyncio.run(go())
    def test_google_sign_in_popup_is_closed_and_explained(self):
        notes,urls=self.open_popup('https://accounts.google.com/signin','accounts.google.com')
        self.assertEqual(len(notes),1);self.assertFalse(any('google.com' in u for u in urls),urls)
    def test_apple_sign_in_popup_is_closed_and_explained(self):
        notes,urls=self.open_popup('https://appleid.apple.com/auth','appleid.apple.com')
        self.assertEqual(len(notes),1);self.assertFalse(any('apple.com' in u for u in urls),urls)
    def test_other_tabs_such_as_linkedin_itself_are_left_alone(self):
        notes,urls=self.open_popup('https://www.linkedin.com/legal/privacy-policy','www.linkedin.com')
        self.assertEqual(notes,[]);self.assertTrue(any('linkedin.com' in u for u in urls),urls)

class WaitTests(Db):
    def run_wait(self,app_status,run_status):
        with self.Session() as db:
            for model in (AgentRun,Application,Job,User):db.query(model).delete()
            db.add(User(id='u',email='w@example.invalid',password='x',profile=PROFILE,settings=SETTINGS));db.flush()
            db.add(Job(id='j',user_id='u',canonical='c',payload={'title':'t','company':'c'}));db.flush()
            db.add(Application(id='a',user_id='u',job_id='j',status=app_status,package={},events=[],browser={}))
            db.add(AgentRun(id='r',user_id='u',status=run_status,state={},events=[]));db.commit()
        with patch.object(platform_agent,'Session',self.Session),patch.object(agent,'Session',self.Session):
            outcome=asyncio.run(asyncio.wait_for(platform_agent.wait_for_application('r','a'),timeout=15))
        with self.Session() as db:return outcome,db.get(Application,'a')
    def test_finished_applications_end_the_wait(self):
        for status in ['submitted','stopped','failed','needs_verification']:
            with self.subTest(status):self.assertEqual(self.run_wait(status,'running')[0],status)
    def test_a_stopped_run_ends_the_wait(self):
        self.assertEqual(self.run_wait('running','stopped')[0],'running')
    def test_a_resumed_run_does_not_wait_forever_on_an_application_needing_review(self):
        outcome,app=self.run_wait('needs_input','running')
        self.assertEqual((outcome,app.status),('stopped','stopped'));self.assertIn('Skipped',app.events[-1]['text'])

class AgentEndToEndTests(Db):
    """The whole run: search -> assess -> documents -> apply on the same tab -> next job -> complete."""
    def test_search_apply_and_skip_external_jobs(self):
        with self.Session() as db:
            db.add(User(id='u',email='e@example.invalid',password='x',profile=PROFILE,settings=SETTINGS));db.flush()
            db.add(AgentRun(id='r',user_id='u',status='running',phase='searching',events=[],state={'profile_hash':fingerprint(PROFILE)}));db.commit()
        pages=[('/feed/','<main><h1>Feed</h1></main>'),('/jobs/search/',SEARCH),('/jobs/view/111111111',JOB_SHADOW),('/jobs/view/222222222',EXTERNAL_JOB)]
        contexts=[];worker_seen=[];released=[];tabs_opened=[]
        async def released_session(_):released.append(1)
        async def assess(system,payload,max_tokens=0,**_):return assessment()
        async def package(profile,job,demo=False,**_):return {'resume':PROFILE['resume_text'],'cover_letter':'Synthetic cover letter.','notes':[],'answers':{}}
        async def session(user_id,proxies=False):return {'id':'s','connectUrl':'local','live_url':'https://live.example/x'}
        async def quick_collect(page):
            await page.wait_for_timeout(300);return [linkedin.job_url(i) for i in await page.evaluate(linkedin.COLLECT_JS)]
        env={'OPENROUTER_API_KEY':'test','BROWSERBASE_API_KEY':'test'}
        patches=[patch.dict(os.environ,env),patch.object(platform_agent,'random',SimpleNamespace(uniform=lambda a,b:0.01)),patch.object(linkedin,'collect_job_urls',quick_collect),
                 patch.object(platform_agent,'async_playwright',partial(linkedin_site,pages,contexts,tabs_opened)),patch.object(worker,'async_playwright',partial(linkedin_site,pages,contexts)),
                 patch.object(platform_agent,'llm',assess),patch.object(platform_agent,'generate_package',package),patch.object(platform_agent,'user_browser_session',session),
                 patch.object(platform_agent,'release_browser',released_session),patch.object(worker,'release_browser',released_session),
                 patch.object(worker,'llm',linkedin_model(worker_seen)),patch('backend.career_ops_documents.pdf_bytes',fake_pdf),patch.object(orchestrator,'EVIDENCE_DIR',Path(self.dir.name)/'evidence')]
        patches+=[patch.object(module,'Session',self.Session) for module in (agent,platform_agent,main,worker)]
        with contextlib.ExitStack() as stack:
            for p in patches:stack.enter_context(p)
            async def go():await asyncio.wait_for(platform_agent.execute_platform('r','LinkedIn'),timeout=120)
            asyncio.run(go())
        with self.Session() as db:
            run=db.get(AgentRun,'r');apps=db.query(Application).all();jobs=db.query(Job).all()
            texts=[e['text'] for e in run.events]
            self.assertEqual(run.status,'completed',texts)
            self.assertEqual([a.status for a in apps],['submitted'],texts)
            self.assertEqual([j.payload['source'] for j in jobs],['LinkedIn'])
            self.assertEqual(jobs[0].payload['url'],'https://www.linkedin.com/jobs/view/111111111/')
            self.assertTrue(any('no Easy Apply' in t or 'applies on the employer site' in t for t in texts),texts)
            self.assertEqual(apps[0].browser.get('started_day'),now().date().isoformat())
            self.assertEqual(run.state['candidates'],['https://www.linkedin.com/jobs/view/111111111/','https://www.linkedin.com/jobs/view/222222222/'])
            # The one thing this fixes: searching and applying (including the confirmed submission) happen
            # on the single discovery tab, so Live View never watches the wrong page.
            evidence=apps[0].browser['evidence']   # proof that the application was sent: employer text, time, and both screenshots on disk
            self.assertIn('Application sent',evidence['confirmation_text']);self.assertTrue(evidence['timestamp'])
            for kind in ('review','confirmation'):self.assertTrue((Path(self.dir.name)/'evidence'/evidence['screenshots'][kind]).stat().st_size>1000,kind)
            self.assertEqual(jobs[0].payload['verification']['status'],'open');self.assertTrue(run.state['plan'] and run.state['trace'])
            self.assertEqual(len(tabs_opened),1,'search and applying must share one tab, not open a second one')
            self.assertEqual(apps[0].browser.get('live_url'),run.browser.get('live_url'),"the application's Live View must be the same tab as the run's")

if __name__=='__main__':unittest.main()
