"""The agent's run loop end to end in local Chromium against a LinkedIn-shaped fake site: rank, quota, re-verify, de-duplicate, retry.
No LinkedIn, Browserbase or OpenRouter traffic and no real application is ever submitted (these runs use each-one-approval mode)."""
import asyncio, contextlib, os, re, tempfile, unittest
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(tempfile.gettempdir())/'orbit-test-loop-unused.db').replace('\\','/'))
from fastapi import HTTPException
from playwright.async_api import async_playwright
from . import agent, linkedin, main, platform_agent, worker
from .db import User, Job, Application, AgentRun
from .domain import fingerprint
from .test_linkedin import Db, PROFILE, JOB_SHADOW, assessment

SEARCH3='<ul>'+''.join(f'<li data-occludable-job-id="{n}{n}{n}{n}{n}{n}{n}{n}{n}">x</li>' for n in (1,2,3))+'</ul>'
IDS=['111111111','222222222','333333333']
CLOSED='<main><h1>AI Engineer</h1><p>No longer accepting applications</p></main>'
NO_BUTTON='<main><h1>AI Engineer</h1><p>Local Test Co</p></main>'
SETTINGS={'source_focus':'linkedin','matching':'fresher_ai','mode':'each','auto_enabled':False,'daily_limit':2}

def site(handler,contexts):
    """Local Chromium standing in for Browserbase. handler(url, n) -> html for the nth request of that job URL."""
    visits={}
    @contextlib.asynccontextmanager
    async def fake():
        async with async_playwright() as real:
            launched=[]
            async def connect_over_cdp(url,timeout=None):
                browser=await real.chromium.launch();launched.append(browser)
                context=await browser.new_context();contexts.append(context)
                async def fulfill(route):
                    url=route.request.url;key=re.sub(r'[?#].*','',url);visits[key]=visits.get(key,0)+1
                    html=handler(key,visits[key])
                    if html is None:await route.fulfill(status=404,body='not found')
                    else:await route.fulfill(status=200,content_type='text/html',body=html)
                await context.route('https://www.linkedin.com/**',fulfill)
                return SimpleNamespace(contexts=[context],is_connected=lambda:True)
            try:yield SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=connect_over_cdp))
            finally:
                for browser in launched:await browser.close()
    return fake()

class LoopTests(Db):
    def run_agent(self,job_html,scores,settings=None,profile=PROFILE,package=None,identity=None,spend=None,run_id='r',first=True,modes=None):
        """Runs one agent pass. scores: {job id: fit score}. identity(id) -> (company, title, location). Returns (run, applications, jobs)."""
        settings={**SETTINGS,**(settings or {})}
        with self.Session() as db:
            if first:db.add(User(id='u',email='e@example.invalid',password='x',profile=profile,settings=settings));db.flush()
            else:db.get(User,'u').settings=settings
            db.add(AgentRun(id=run_id,user_id='u',status='running',phase='searching',events=[],state={'profile_hash':fingerprint(profile)}));db.commit()
        def handler(url,n):
            if url.endswith('/feed/'):return '<main><h1>Feed</h1></main>'
            if '/jobs/search/' in url:return SEARCH3
            found=re.search(r'/jobs/view/(\d+)',url)
            return job_html(found.group(1),n) if found else None
        async def assess(system,payload,max_tokens=0,**_):
            job_id=re.search(r'(\d{9})',payload['page_url']).group(1)
            company,title,location=(identity or (lambda i:(f'Company {i}','AI Engineer','Hyderabad, India')))(job_id)
            return assessment(score=scores[job_id],company=company,title=title,location=location,**({'mode':modes[job_id]} if modes else {}))
        async def default_package(profile,job,demo=False,**_):return {'resume':PROFILE['resume_text'],'cover_letter':'Synthetic cover letter.','notes':[],'answers':{}}
        async def session(user_id,proxies=False):return {'id':'s','connectUrl':'local','live_url':'https://live.example/x'}
        async def released(_):pass
        async def quick_collect(page):
            await page.wait_for_timeout(300);return [linkedin.job_url(i) for i in await page.evaluate(linkedin.COLLECT_JS)]
        patches=[patch.dict(os.environ,{'OPENROUTER_API_KEY':'test','BROWSERBASE_API_KEY':'test'}),patch.object(platform_agent,'random',SimpleNamespace(uniform=lambda a,b:0.01)),
                 patch.object(linkedin,'collect_job_urls',quick_collect),patch.object(platform_agent,'async_playwright',partial(site,handler,[])),
                 patch.object(platform_agent,'llm',assess),patch.object(platform_agent,'generate_package',package or default_package),patch.object(platform_agent,'user_browser_session',session),
                 patch.object(platform_agent,'release_browser',released)]
        if spend:patches.append(patch.object(platform_agent,'run_spend',spend))
        patches+=[patch.object(module,'Session',self.Session) for module in (agent,platform_agent,main,worker)]
        with contextlib.ExitStack() as stack:
            for p in patches:stack.enter_context(p)
            asyncio.run(asyncio.wait_for(platform_agent.execute_platform(run_id,'LinkedIn'),timeout=180))
        with self.Session() as db:
            run=db.get(AgentRun,run_id);apps=db.query(Application).all();jobs={j.canonical.split('/')[-2]:j for j in db.query(Job)}
            db.expunge_all()
        return run,apps,jobs
    def texts(self,run):return [e['text'] for e in run.events]

    def test_matches_are_ranked_best_first_and_only_the_quota_gets_documents(self):
        run,apps,jobs=self.run_agent(lambda i,n:JOB_SHADOW,{'111111111':65,'222222222':92,'333333333':78})
        self.assertEqual(run.status,'completed',self.texts(run))
        order=[(i['job_id'],i['status']) for i in run.state['shortlist']];ids={j.id:k for k,j in jobs.items()}
        self.assertEqual([(ids[j],s) for j,s in order],[('222222222','prepared'),('333333333','prepared'),('111111111','over_quota')])
        self.assertEqual(sorted(ids[a.job_id] for a in apps),['222222222','333333333'],'the weakest match got no documents and no application')
        self.assertTrue(any(t['decision']=='defer' for t in run.state['trace']))
    def test_the_run_records_its_plan_and_each_decision(self):
        run,apps,jobs=self.run_agent(lambda i,n:JOB_SHADOW,{'111111111':65,'222222222':92,'333333333':78})
        self.assertEqual(run.state['plan']['quota']['slots'],2);self.assertEqual(run.state['plan']['threshold'],60)
        steps={t['step'] for t in run.state['trace']};self.assertTrue({'evaluate','verify','prepare'}<=steps,steps)
        self.assertEqual(jobs['222222222'].payload['verification']['status'],'open');self.assertTrue(jobs['222222222'].payload['verification']['checked_at'])
    def test_below_the_fit_floor_is_never_shortlisted(self):
        run,apps,jobs=self.run_agent(lambda i,n:JOB_SHADOW,{'111111111':59,'222222222':45,'333333333':30})
        self.assertEqual(apps,[]);self.assertEqual(run.state.get('shortlist',[]),[])
        self.assertTrue(any(t['decision']=='reject' for t in run.state['trace']))
    def test_a_job_that_closed_after_it_was_assessed_gets_no_application(self):
        run,apps,jobs=self.run_agent(lambda i,n:CLOSED if i=='222222222' and n>=2 else JOB_SHADOW,{'111111111':65,'222222222':92,'333333333':78})
        status={i['job_id']:i['status'] for i in run.state['shortlist']};ids={j.id:k for k,j in jobs.items()}
        self.assertEqual(status[jobs['222222222'].id],'closed');self.assertEqual(jobs['222222222'].payload['verification']['status'],'closed')
        self.assertEqual(sorted(ids[a.job_id] for a in apps),['111111111','333333333'],'the next best jobs take its place')
    def test_an_unclear_page_is_not_treated_as_verified_open(self):
        run,apps,jobs=self.run_agent(lambda i,n:NO_BUTTON if i=='222222222' and n>=2 else JOB_SHADOW,{'111111111':65,'222222222':92,'333333333':78})
        self.assertEqual(jobs['222222222'].payload['verification']['status'],'uncertain')
        self.assertNotIn(jobs['222222222'].id,[a.job_id for a in apps])
    def test_the_same_vacancy_posted_twice_is_applied_to_once(self):
        same=lambda i:('Acme Inc','Python Developer','Hyderabad, India') if i in ('111111111','222222222') else ('Other Co','AI Engineer','Hyderabad, India')
        run,apps,jobs=self.run_agent(lambda i,n:JOB_SHADOW,{'111111111':70,'222222222':90,'333333333':65},identity=same,settings={'daily_limit':3})
        status={jobs[k].id:next(i['status'] for i in run.state['shortlist'] if i['job_id']==jobs[k].id) for k in jobs}
        self.assertEqual(status[jobs['222222222'].id],'prepared');self.assertEqual(status[jobs['111111111'].id],'duplicate')
        self.assertEqual(len(apps),2)
    def test_a_transient_model_failure_is_retried_a_bounded_number_of_times(self):
        calls=[]
        async def flaky(profile,job,demo=False,**_):
            calls.append(job['title'])
            if len(calls)<=2:raise HTTPException(503,'provider busy')
            return {'resume':PROFILE['resume_text'],'cover_letter':'c','notes':[],'answers':{}}
        orig=asyncio.sleep
        async def quick(s,*a):return await orig(0)
        with patch('backend.orchestrator.asyncio.sleep',quick):
            run,apps,jobs=self.run_agent(lambda i,n:JOB_SHADOW,{'111111111':20,'222222222':92,'333333333':20},package=flaky)
        self.assertEqual(len(calls),3);self.assertEqual([a.status for a in apps],['prepared'])
    def test_a_permanent_failure_skips_that_job_and_the_run_continues(self):
        async def broken(profile,job,demo=False,**_):raise HTTPException(503,'provider down')
        async def quick(s,*a):pass
        with patch('backend.orchestrator.asyncio.sleep',quick):
            run,apps,jobs=self.run_agent(lambda i,n:JOB_SHADOW,{'111111111':20,'222222222':92,'333333333':20},package=broken)
        self.assertEqual(run.status,'completed',self.texts(run));self.assertEqual(apps,[])
        self.assertEqual([i['status'] for i in run.state['shortlist']],['error'])
    def test_unsupported_claims_hold_the_application_for_the_person(self):
        async def inventive(profile,job,demo=False,**_):return {'resume':PROFILE['resume_text']+'\nIncreased revenue by 487%.','cover_letter':'c','notes':[],'answers':{}}
        run,apps,jobs=self.run_agent(lambda i,n:JOB_SHADOW,{'111111111':20,'222222222':92,'333333333':20},package=inventive)
        self.assertEqual([a.status for a in apps],['prepared']);self.assertTrue(any('487%' in n for n in apps[0].package['notes']))
        self.assertTrue(any('claims your profile does not support' in t for t in self.texts(run)))
    def test_a_match_that_missed_the_quota_is_carried_into_the_next_run(self):
        pages=lambda i,n:JOB_SHADOW;scores={'111111111':65,'222222222':92,'333333333':78}
        run,apps,jobs=self.run_agent(pages,scores,settings={'daily_limit':1})
        self.assertEqual(len(apps),1,'only the best match got documents on day one')
        with self.Session() as db:   # the person sent it, then a new day: another application is allowed
            for a in db.query(Application):a.status='stopped'
            db.commit()
        run,apps,jobs=self.run_agent(pages,scores,settings={'daily_limit':1},run_id='r2',first=False)
        ids={j.id:k for k,j in jobs.items()}
        self.assertEqual(sorted(ids[a.job_id] for a in apps if a.status=='prepared'),['333333333'],'the next best earlier match is picked up, not skipped as already reviewed')
        self.assertTrue(any(t['decision']=='carry-over' for t in run.state['trace']))
    ACCEPTED={'active':{'version':'adj-test0001','adjustments':{'mode':{'Remote':8,'Onsite':-8}},'rationale':['+8 points for work mode Remote'],'accepted_at':'2026-10-15T00:00:00+00:00'}}
    MODES={'111111111':'Onsite','222222222':'Remote','333333333':'Remote'}
    def test_without_an_accepted_ranking_the_baseline_order_is_used_and_recorded(self):
        run,apps,jobs=self.run_agent(lambda i,n:JOB_SHADOW,{'111111111':70,'222222222':66,'333333333':64},settings={'daily_limit':1},modes=self.MODES)
        ids={j.id:k for k,j in jobs.items()};self.assertEqual([ids[a.job_id] for a in apps],['111111111'])
        rank=[t for t in run.state['trace'] if t['step']=='rank'];self.assertEqual((rank[0]['decision'],run.state['ranking_version']),('baseline','baseline'))
    def test_an_accepted_ranking_changes_the_order_and_is_traced(self):
        run,apps,jobs=self.run_agent(lambda i,n:JOB_SHADOW,{'111111111':70,'222222222':66,'333333333':64},settings={'daily_limit':1,'ranking':self.ACCEPTED},modes=self.MODES)
        ids={j.id:k for k,j in jobs.items()};self.assertEqual([ids[a.job_id] for a in apps],['222222222'],'the remote job outranks the higher-scored onsite job')
        rank=[t for t in run.state['trace'] if t['step']=='rank'][0];self.assertEqual(rank['decision'],'adjusted');self.assertEqual(rank['version'],run.state['ranking_version'])
        self.assertIn('Remote',rank['reason']);self.assertGreater(rank['moved'],0)
        by={ids[i['job_id']]:i for i in run.state['shortlist']};self.assertEqual((by['222222222']['rank_adjust'],by['111111111']['rank_adjust']),(8,-8));self.assertEqual(by['222222222']['score'],66)
    def test_an_accepted_ranking_cannot_lift_a_job_over_the_fit_floor_or_past_verification(self):
        weak=lambda i,n:CLOSED if i=='222222222' and n>=2 else JOB_SHADOW
        run,apps,jobs=self.run_agent(weak,{'111111111':70,'222222222':95,'333333333':45},settings={'daily_limit':3,'ranking':self.ACCEPTED},modes=self.MODES)
        ids={j.id:k for k,j in jobs.items()};listed={ids[i['job_id']] for i in run.state['shortlist']}
        self.assertNotIn('333333333',listed,'a Remote +8 job below the 60% floor is never shortlisted')
        self.assertEqual(jobs['222222222'].payload['verification']['status'],'closed');self.assertEqual(sorted(ids[a.job_id] for a in apps),['111111111'],'top-ranked but closed: still rejected')
    def test_an_accepted_ranking_still_respects_the_daily_limit_and_duplicates(self):
        same=lambda i:('Acme Inc','Python Developer','Hyderabad, India') if i in ('222222222','333333333') else ('Other Co','AI Engineer','Hyderabad, India')
        run,apps,jobs=self.run_agent(lambda i,n:JOB_SHADOW,{'111111111':70,'222222222':66,'333333333':65},settings={'daily_limit':2,'ranking':self.ACCEPTED},modes=self.MODES,identity=same)
        status={i['job_id']:i['status'] for i in run.state['shortlist']};ids={j.id:k for k,j in jobs.items()}
        self.assertEqual(len(apps),2);self.assertEqual(status[jobs['333333333'].id],'duplicate')
    def test_the_model_budget_stops_further_preparation(self):
        def spend(run_id):   # cheap while searching and assessing, over budget once the ranking is done
            with self.Session() as db:ranked=any(e['text'].startswith('Ranked') for e in db.get(AgentRun,run_id).events)
            return {'usd':9.0 if ranked else 0.0,'calls':1}
        run,apps,jobs=self.run_agent(lambda i,n:JOB_SHADOW,{'111111111':65,'222222222':92,'333333333':78},spend=spend)
        self.assertEqual(apps,[]);self.assertEqual({i['status'] for i in run.state['shortlist']},{'over_budget'})

if __name__=='__main__':unittest.main()
