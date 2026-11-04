"""Orbit works with LinkedIn only. These checks keep employer career pages, Naukri and Indeed out."""
import asyncio, importlib.util, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(tempfile.gettempdir())/'orbit-test-scope-unused.db').replace('\\','/'))
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from . import agent, main, platform_agent, services
from .db import Base, User, Job, Application, AgentRun
from .domain import DEMO_PROFILE, fingerprint

EMPLOYER_URLS=['https://boards.greenhouse.io/acme/jobs/1','https://job-boards.greenhouse.io/acme/jobs/1','https://jobs.lever.co/acme/1',
    'https://jobs.ashbyhq.com/acme/1','https://acme.wd3.myworkdayjobs.com/en-US/careers/job/1','https://careers.smartrecruiters.com/acme/1','https://careers.acme.com/apply/1']

class AllowListTests(unittest.TestCase):
    def test_employer_career_pages_are_never_application_destinations(self):
        for url in EMPLOYER_URLS:
            for source in (None,'Greenhouse','Lever','Ashby','Workday','Company careers','LinkedIn','Indeed','Naukri','Internshala'):
                self.assertFalse(services.allowed_application_url(url,source),(url,source))
    def test_recognized_platforms(self):
        self.assertEqual(list(services.PLATFORMS),['LinkedIn','Indeed','Naukri','Internshala'])
        self.assertTrue(services.allowed_application_url('https://www.linkedin.com/jobs/view/3912345678/','LinkedIn'))
        self.assertTrue(services.allowed_application_url('https://in.indeed.com/viewjob?jk=abc123','Indeed'))
        self.assertTrue(services.allowed_application_url('https://www.naukri.com/job-listings-123','Naukri'))
        self.assertTrue(services.allowed_application_url('https://internshala.com/job/detail/123','Internshala'))
    def test_look_alike_hosts_are_refused(self):
        for url in ['https://linkedin.com.evil.example/x','https://evil.example/linkedin.com','http://www.linkedin.com/x','https://user@www.linkedin.com/x']:
            self.assertFalse(services.allowed_application_url(url,'LinkedIn'),url)
        for url in ['https://naukri.com.evil.example/x','http://www.naukri.com/x']:
            self.assertFalse(services.allowed_application_url(url,'Naukri'),url)
    def test_removed_modules_stay_removed(self):
        for name in ('ats','jobspy_discovery','portal_navigation'):
            self.assertIsNone(importlib.util.find_spec('backend.'+name),name)
    def test_board_discovery_helpers_are_gone(self):
        for name in ('discover','company_portal_url','allowed_job_url'):self.assertFalse(hasattr(services,name),name)

class Db(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.engine=create_engine('sqlite:///'+str(Path(self.dir.name)/'s.db').replace('\\','/'),connect_args={'check_same_thread':False})
        Base.metadata.create_all(self.engine);self.Session=sessionmaker(bind=self.engine,expire_on_commit=False)
    def tearDown(self):
        self.engine.dispose();self.dir.cleanup()
    def reset(self):
        with self.Session() as db:
            for model in (AgentRun,Application,Job,User):db.query(model).delete()
            db.commit()

class StartRefusalTests(Db):
    def start(self,source):
        package={'resume':'r','cover_letter':'c','notes':[],'answers':{}}
        self.reset()
        with self.Session() as db:
            user=User(id='u',email='s@example.invalid',password='x',profile=DEMO_PROFILE,settings={'mode':'each','daily_limit':10,'threshold':70,'auto_enabled':False,'source_focus':'linkedin'})
            db.add(user);db.flush()
            db.add(Job(id='j',user_id='u',canonical='c',payload={'title':'t','company':'c','source':source,'url':'https://boards.greenhouse.io/acme/jobs/1','match':{'matched':True}}));db.flush()
            db.add(Application(id='a',user_id='u',job_id='j',status='approved',package=package,approved_hash=fingerprint(package),events=[],browser={}));db.commit()
            with patch.dict(os.environ,{'OPENROUTER_API_KEY':'x','BROWSERBASE_API_KEY':'x'}):
                try:asyncio.run(main._action('a',main.Action(action='start'),user,db));return None
                except HTTPException as error:return error
    def test_a_job_from_another_source_cannot_be_started(self):
        for source in ('Greenhouse','Lever','Company careers','Monster',None):
            with self.subTest(source):
                error=self.start(source)
                self.assertIsNotNone(error);self.assertEqual(error.status_code,409);self.assertIn('supported platforms',error.detail)

class AgentSourceTests(Db):
    def run_agent(self,focus):
        self.reset()
        with self.Session() as db:
            db.add(User(id='u',email='a@example.invalid',password='x',profile=DEMO_PROFILE,settings={'source_focus':focus}));db.flush()
            db.add(AgentRun(id='r',user_id='u',status='running',phase='searching',events=[],state={}));db.commit()
        with patch.object(agent,'Session',self.Session),patch.object(platform_agent,'Session',self.Session):
            asyncio.run(agent.execute('r'))
        with self.Session() as db:
            run=db.get(AgentRun,'r');return run.status,run.events[-1]['text']
    def test_any_saved_focus_runs_on_supported_platforms(self):
        async def no_key(user_id,proxies=None):raise HTTPException(503,'Add BROWSERBASE_API_KEY to enable live browser sessions.')
        for focus in ('all','greenhouse','naukri',None,'linkedin'):
            with self.subTest(focus),patch.object(platform_agent,'user_browser_session',no_key):
                status,text=self.run_agent(focus)
                self.assertEqual(status,'failed');self.assertIn('BROWSERBASE_API_KEY',text)

if __name__=='__main__':unittest.main()
