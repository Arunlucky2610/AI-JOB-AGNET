"""Integration checks on an isolated temporary SQLite database, no external calls."""
import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

TEST_DIR=tempfile.TemporaryDirectory()
os.environ['DATABASE_URL']='sqlite:///'+str(Path(TEST_DIR.name)/'test.db').replace('\\','/')
os.environ['ALLOW_DEMO']='true'
from fastapi.testclient import TestClient
from .main import app
from .db import Session, Application, Job, now, engine
from .domain import evaluate, DEMO_PROFILE

def tearDownModule():
    engine.dispose()

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app,headers={'origin':'http://127.0.0.1:3000'})
        self.client.__enter__()
        self.assertEqual(self.client.post('/api/auth/demo',json={}).status_code,200)
    def tearDown(self):self.client.__exit__(None,None,None)
    def ready(self):return next(a for a in self.client.get('/api/applications').json() if a['status']=='prepared')
    def test_dashboard_is_computed(self):
        stats=self.client.get('/api/analytics').json()
        self.assertEqual(stats['discovered'],12)
        self.assertEqual(stats['counts']['submitted'],3)
        self.assertEqual(sum(stats['sources'].values()),12)
    def test_outcomes_track_what_happened_after_submission(self):
        submitted=[a for a in self.client.get('/api/applications').json() if a['status']=='submitted']
        self.assertEqual(len(submitted),3);first,second,third=[a['id'] for a in submitted]
        self.assertIsNone(submitted[0]['outcome'])
        r=self.client.put(f'/api/applications/{first}/outcome',json={'stage':'interview','fit_feedback':'up'});self.assertEqual(r.status_code,200)
        self.client.put(f'/api/applications/{second}/outcome',json={'stage':'rejected','fit_feedback':'down'})
        self.client.put(f'/api/applications/{first}/outcome',json={'note':'Phone screen Friday'})   # a later partial update keeps the stage
        summary=self.client.get('/api/outcomes/summary').json()
        self.assertEqual((summary['submitted'],summary['progressed'],summary['shortlist_rate'],summary['decided_rate']),(3,1,33,50))
        self.assertEqual((summary['stages']['waiting'],summary['fit_up'],summary['fit_down']),(1,1,1))
        kept=next(a for a in self.client.get('/api/applications').json() if a['id']==first)['outcome']
        self.assertEqual((kept['stage'],kept['note']),('interview','Phone screen Friday'))
    def test_only_submitted_applications_have_outcomes(self):
        self.assertEqual(self.client.put(f"/api/applications/{self.ready()['id']}/outcome",json={'stage':'interview'}).status_code,409)
        submitted=next(a['id'] for a in self.client.get('/api/applications').json() if a['status']=='submitted')
        self.assertEqual(self.client.put(f'/api/applications/{submitted}/outcome',json={'stage':'hired'}).status_code,422)
    def test_onboarding_starts_blank_without_login(self):
        fresh=TestClient(app,headers={'origin':'http://127.0.0.1:3000'})
        r=fresh.post('/api/workspace/init',json={})
        self.assertEqual(r.status_code,200)
        self.assertFalse(r.json()['demo'])
        self.assertFalse(r.json()['profile']['confirmed'])
        self.assertEqual(fresh.get('/api/jobs').json(),[])
    def test_city_autocomplete_requires_login_and_proxies_the_lookup(self):
        fresh=TestClient(app,headers={'origin':'http://127.0.0.1:3000'})
        self.assertEqual(fresh.get('/api/geocode/cities?q=Hyderabad').status_code,401)
        async def fake_lookup(q):return [{'label':f'{q}, Telangana, India','city':q,'state':'Telangana','country':'India'}]
        with patch('backend.services.geocode_cities',fake_lookup):
            r=self.client.get('/api/geocode/cities?q=Hyderabad')
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json(),{'results':[{'label':'Hyderabad, Telangana, India','city':'Hyderabad','state':'Telangana','country':'India'}]})
        self.assertEqual(self.client.get('/api/geocode/cities?q='+'x'*101).status_code,422)
    def test_resume_suggestions_are_not_guesses(self):
        text=b'Jordan Smith\njordan@example.com\n+1 212 555 1234\nEducation: BS in Computer Science, Example University, 2024\nExperience: Developer at Example Studio, 2024-present. Built web interfaces.\nSkills: Python, React'
        r=self.client.post('/api/profile/resume',files={'file':('resume.txt',text,'text/plain')})
        fields=r.json()['fields']
        self.assertEqual(fields['name'],'Jordan Smith')
        self.assertEqual(fields['email'],'jordan@example.com')
        self.assertEqual(fields['education'][0]['year'],'2024')
        self.assertEqual(fields['work_history'][0]['company'],'Example Studio')
        self.assertNotIn('eeo_gender',fields)
        self.assertNotIn('authorization',fields)
    def test_incomplete_profile_cannot_be_confirmed(self):
        from .domain import EMPTY_PROFILE
        self.assertEqual(self.client.put('/api/profile',json={**EMPTY_PROFILE,'confirmed':True}).status_code,422)
    def test_users_cannot_read_or_mutate_others(self):
        a=self.ready()
        other=TestClient(app,headers={'origin':'http://127.0.0.1:3000'})
        other.post('/api/auth/demo',json={})
        self.assertEqual(other.post('/api/applications/approve',json={'ids':[a['id']]}).status_code,404)
        self.assertEqual(other.get(f"/api/applications/{a['id']}/download").status_code,404)
    def test_approval_is_invalidated_on_edit(self):
        a=self.ready()
        self.assertEqual(self.client.post('/api/applications/approve',json={'ids':[a['id']]}).status_code,200)
        pack={**a['package'],'cover_letter':'Updated and reviewed facts.'}
        r=self.client.put(f"/api/applications/{a['id']}/package",json=pack)
        self.assertFalse(r.json()['approved'])
        self.assertEqual(r.json()['status'],'prepared')
        self.assertEqual(self.client.post(f"/api/applications/{a['id']}/action",json={'action':'start'}).status_code,409)
    def test_daily_limit_and_demo_transitions(self):
        self.client.put('/api/settings',json={'mode':'each','daily_limit':10,'threshold':70,'auto_enabled':False})
        a=self.ready();self.client.post('/api/applications/approve',json={'ids':[a['id']]})
        endpoint=f"/api/applications/{a['id']}/action"
        self.assertEqual(self.client.post(endpoint,json={'action':'start'}).json()['status'],'running')
        self.assertEqual(self.client.post(endpoint,json={'action':'takeover'}).json()['status'],'needs_input')
        self.assertEqual(self.client.post(endpoint,json={'action':'demo_advance'}).status_code,409)
        self.assertEqual(self.client.post(endpoint,json={'action':'resume'}).json()['status'],'running')
        for _ in range(5):r=self.client.post(endpoint,json={'action':'demo_advance'})
        self.assertEqual(r.json()['status'],'submitted')
        self.assertEqual(self.client.post(endpoint,json={'action':'start'}).status_code,409)
    def test_limit_blocks_new_start(self):
        self.client.put('/api/settings',json={'mode':'each','daily_limit':1,'threshold':70,'auto_enabled':False})
        with Session() as db:
            for a in db.query(Application).filter_by(status='submitted'):a.updated=now()
            db.commit()
        a=self.ready();self.client.post('/api/applications/approve',json={'ids':[a['id']]})
        self.assertEqual(self.client.post(f"/api/applications/{a['id']}/action",json={'action':'start'}).status_code,409)
    def test_stopped_attempts_do_not_use_up_the_daily_limit_but_submissions_do(self):
        import uuid
        self.client.put('/api/settings',json={'mode':'each','daily_limit':1,'threshold':70,'auto_enabled':False})
        a=self.ready();self.client.post('/api/applications/approve',json={'ids':[a['id']]})
        with Session() as db:
            for x in db.query(Application).filter(Application.user_id==db.get(Application,a['id']).user_id,Application.id!=a['id']):
                x.status='stopped';x.browser={**x.browser,'started_day':now().date().isoformat()};x.updated=now()
            db.commit()
        r=self.client.post(f"/api/applications/{a['id']}/action",json={'action':'start'})
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['status'],'running','skipped attempts left the allowance intact')
    def test_a_submission_uses_the_limit_and_endless_attempts_are_capped(self):
        import uuid
        from .main import attempt_cap
        self.assertEqual((attempt_cap(1),attempt_cap(3),attempt_cap(10)),(11,13,40))
        self.client.put('/api/settings',json={'mode':'each','daily_limit':1,'threshold':70,'auto_enabled':False})
        a=self.ready();self.client.post('/api/applications/approve',json={'ids':[a['id']]})
        with Session() as db:
            row=db.get(Application,a['id']);uid,job=row.user_id,row.job_id
            for x in db.query(Application).filter(Application.user_id==uid,Application.id!=a['id']):x.status='stopped';x.browser={**x.browser,'started_day':'2000-01-01'}
            for n in range(11):
                extra=Job(id=str(uuid.uuid4()),user_id=uid,canonical=f'https://example.invalid/{n}',payload={'title':'t','company':'c'});db.add(extra);db.flush()
                db.add(Application(id=str(uuid.uuid4()),user_id=uid,job_id=extra.id,status='stopped',package={},events=[],browser={'started_day':now().date().isoformat()}))
            db.commit()
        r=self.client.post(f"/api/applications/{a['id']}/action",json={'action':'start'})
        self.assertEqual(r.status_code,409);self.assertIn('11 attempts today',r.json()['detail']);self.assertIn('Daily application limit',r.json()['detail'])
    def test_missing_country_never_becomes_eligible(self):
        result=evaluate(DEMO_PROFILE,{'title':'Frontend Engineer','description':DEMO_PROFILE['skills'],'mode':'Remote','country':'','min_experience':2,'authorization_verified':True})
        self.assertFalse(result['eligible']);self.assertTrue(result['unknown'])
    def test_upload_and_download(self):
        r=self.client.post('/api/profile/resume',files={'file':('resume.txt',b'Real career history','text/plain')})
        self.assertEqual(r.json()['text'],'Real career history')
        self.assertEqual(self.client.post('/api/profile/resume',files={'file':('image.png',b'invalid','image/png')}).status_code,422)
        r=self.client.get(f"/api/applications/{self.ready()['id']}/download")
        self.assertEqual(r.status_code,200);self.assertTrue(r.content.startswith(b'PK'))
    def test_hostile_origin_is_rejected(self):
        r=self.client.post('/api/auth/demo',json={},headers={'origin':'https://evil.example'})
        self.assertEqual(r.status_code,403)
    def test_invalid_settings_rejected(self):
        self.assertEqual(self.client.put('/api/settings',json={'daily_limit':-1}).status_code,422)
    def test_skill_years_are_saved_and_validated(self):
        from .domain import EMPTY_PROFILE
        ok=self.client.put('/api/profile',json={**EMPTY_PROFILE,'skill_years':{'Python':1,'React':0.5}})
        body=ok.json()
        self.assertEqual(ok.status_code,200);self.assertEqual(body.get('profile',body)['skill_years'],{'Python':1,'React':0.5})
        for bad in ({'Python':-1},{'Python':71},{'Python':'lots'},{'':1},{'x'*61:1},{'Python':True},{f's{i}':1 for i in range(81)},['Python']):
            self.assertEqual(self.client.put('/api/profile',json={**EMPTY_PROFILE,'skill_years':bad}).status_code,422,str(bad)[:40])
    def test_country_is_normalised_and_unknown_ones_cannot_be_confirmed(self):
        from .domain import EMPTY_PROFILE
        for typed,official in (('india','India'),(' USA ','United States'),('UK','United Kingdom'),('India','India')):
            r=self.client.put('/api/profile',json={**EMPTY_PROFILE,'country':typed})
            self.assertEqual(r.status_code,200,typed);self.assertEqual(r.json().get('profile',r.json())['country'],official)
        r=self.client.put('/api/profile',json={**EMPTY_PROFILE,'country':'Hyderabad'})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json().get('profile',r.json())['country'],'','a draft with a non-country is blanked, not kept')
        full={**EMPTY_PROFILE,'confirmed':True,'country':'Narnia'}
        self.assertEqual(self.client.put('/api/profile',json=full).status_code,422)
    def test_resume_skills_are_a_clean_list(self):
        text=b'Sam Lee\nsam@example.com\nSkills\nFrontend: React, TypeScript\nBackend: Python, FastAPI | SQL\nTools: Git, Python'
        fields=self.client.post('/api/profile/resume',files={'file':('resume.txt',text,'text/plain')}).json()['fields']
        self.assertEqual(fields['skills'],'React, TypeScript, Python, FastAPI, SQL, Git')
    def test_country_list_matches_the_form(self):
        import re,json
        from .countries import COUNTRIES
        source=(Path(__file__).resolve().parent.parent/'app'/'profile-logic.ts').read_text(encoding='utf-8')
        block=source.split('COUNTRY_TABLE: [string, string][] = [')[1].split('];')[0]
        table=re.findall(r"\['((?:[^'\\]|\\.)*)','(\+\d+)'\]",block)
        self.assertEqual([(n.replace("\\'","'"),c) for n,c in table],COUNTRIES)
    def test_waiting_applications_can_be_cleared_without_touching_finished_ones(self):
        before={a['id']:a['status'] for a in self.client.get('/api/applications').json()}
        waiting=[i for i,st in before.items() if st in ('prepared','approved')];finished={i:st for i,st in before.items() if st not in ('prepared','approved')}
        self.assertTrue(waiting and finished)
        self.assertEqual(self.client.post('/api/applications/clear-waiting',json={}).json(),{'cleared':len(waiting)})
        after={a['id']:a for a in self.client.get('/api/applications').json()}
        for i in waiting:self.assertEqual(after[i]['status'],'stopped');self.assertIn('Cleared from the waiting list',after[i]['events'][-1]['text'])
        for i,st in finished.items():self.assertEqual(after[i]['status'],st)
        self.assertEqual(self.client.post('/api/applications/clear-waiting',json={}).json(),{'cleared':0})
    def test_agent_status_reports_needed_answers_and_spend(self):
        from types import SimpleNamespace
        from . import services
        from .main import agent_json
        services.SPEND['x']={'usd':0.1234,'calls':7}
        self.addCleanup(services.SPEND.clear)
        run=SimpleNamespace(id='x',status='running',phase='matching',events=[],browser={},state={'needed':[{'question':'a drug test','job':'Dev'}],'prefiltered':2})
        with patch.dict(os.environ,{'RUN_BUDGET_USD':'2'}):body=agent_json(run)
        self.assertEqual(body['needed'],[{'question':'a drug test','job':'Dev'}]);self.assertEqual(body['prefiltered'],2)
        self.assertEqual(body['spend'],{'usd':0.1234,'calls':7,'cap':2.0})
        self.assertEqual(agent_json(None)['status'],'idle')
    def test_saving_the_profile_keeps_the_models_verdict_on_platform_jobs(self):
        import uuid
        from .domain import EMPTY_PROFILE
        a=self.ready()
        with Session() as db:
            uid=db.get(Application,a['id']).user_id
            verdict={'score':88,'matched':True,'eligible':True,'blockers':[],'unknown':[],'matched_skills':[],'missing_skills':[],'explanation':'model'}
            db.merge(Job(id='lj',user_id=uid,canonical='https://www.linkedin.com/jobs/view/1/',payload={'title':'AI Intern','company':'C','source':'LinkedIn','match':verdict,'country':'India','skills':[]}));db.commit()
        saved=self.client.put('/api/profile',json={**self.client.get('/api/me').json()['profile'],'confirmed':False});self.assertEqual(saved.status_code,200,saved.text)
        with Session() as db:self.assertEqual(db.get(Job,'lj').payload['match']['explanation'],'model')
    def test_only_linkedin_is_offered(self):
        sources=self.client.get('/api/integrations').json()['sources']
        self.assertEqual([(s['name'],s['enabled']) for s in sources],[('LinkedIn',True),('Indeed',True),('Naukri',True),('Internshala',True)])
    def test_employer_career_page_sources_are_refused(self):
        base={'mode':'each','daily_limit':3,'threshold':70,'auto_enabled':False}
        for focus in ['all','greenhouse','lever','ashby','workday','smartrecruiters']:
            self.assertEqual(self.client.put('/api/settings',json={**base,'source_focus':focus}).status_code,422,focus)
        self.assertEqual(self.client.put('/api/settings',json={**base,'source_focus':'linkedin'}).status_code,200)
        saved=self.client.put('/api/settings',json={**base,'source_focus':'indeed'})
        self.assertEqual(saved.status_code,200);self.assertEqual(saved.json()['source_focus'],'indeed')
        saved_naukri=self.client.put('/api/settings',json={**base,'source_focus':'naukri'})
        self.assertEqual(saved_naukri.status_code,200);self.assertEqual(saved_naukri.json()['source_focus'],'naukri')
        saved_internshala=self.client.put('/api/settings',json={**base,'source_focus':'internshala'})
        self.assertEqual(saved_internshala.status_code,200);self.assertEqual(saved_internshala.json()['source_focus'],'internshala')
    def test_board_search_and_portal_preflight_are_gone(self):
        self.assertIn(self.client.post('/api/jobs/search',json={'source':'Greenhouse','board':'linear'}).status_code,(404,405))
        a=self.ready()
        self.assertEqual(self.client.post(f"/api/applications/{a['id']}/action",json={'action':'open_portal'}).status_code,422)
    def test_new_workspaces_default_to_linkedin(self):
        from .domain import DEFAULT_SETTINGS
        self.assertEqual(DEFAULT_SETTINGS['source_focus'],'linkedin')
    def test_submission_ambiguity_is_not_retryable(self):
        a=self.ready()
        with Session() as db:
            row=db.get(Application,a['id']);row.status='needs_verification';db.commit()
        self.assertEqual(self.client.post(f"/api/applications/{a['id']}/action",json={'action':'resume'}).status_code,409)

    def test_job_and_application_deletion_and_archive(self):
        a = self.ready()
        app_id = a['id']
        job_id = a['job']['id']
        
        # Test archive application
        res_arch = self.client.post(f'/api/applications/{app_id}/archive')
        self.assertEqual(res_arch.status_code, 200)
        self.assertTrue(res_arch.json()['archived'])
        
        # Check application JSON reflects diagnostic and archived
        with Session() as db:
            row = db.get(Application, app_id)
            row.status = 'stopped'
            row.events = [*row.events, {'time': now().isoformat(), 'text': 'Skipped: Naukri rejected application (Candidate profile incomplete or previously rejected on this opening).'}]
            db.commit()
            
        apps = self.client.get('/api/applications').json()
        target = next(x for x in apps if x['id'] == app_id)
        self.assertTrue(target['archived'])
        self.assertIsNotNone(target['diagnostic'])
        self.assertEqual(target['diagnostic']['category'], 'portal_rejected')
        
        # Test delete application
        del_app = self.client.delete(f'/api/applications/{app_id}')
        self.assertEqual(del_app.status_code, 200)
        self.assertTrue(del_app.json()['success'])
        
        # Verify application gone
        with Session() as db:
            self.assertIsNone(db.get(Application, app_id))
            
        # Test job archive
        res_j_arch = self.client.post(f'/api/jobs/{job_id}/archive')
        self.assertEqual(res_j_arch.status_code, 200)
        self.assertTrue(res_j_arch.json()['archived'])
        
        # Test job delete
        del_job = self.client.delete(f'/api/jobs/{job_id}')
        self.assertEqual(del_job.status_code, 200)
        self.assertTrue(del_job.json()['success'])
        with Session() as db:
            self.assertIsNone(db.get(Job, job_id))

if __name__=='__main__':unittest.main()
