""""Connect your accounts" checks: platform_agent.check_login/cancel_login/connected_platforms and the
/api/connections routes. No LinkedIn, Browserbase or OpenRouter traffic.
"""
import asyncio, contextlib, os, tempfile, unittest
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(tempfile.gettempdir())/'orbit-test-connections-unused.db').replace('\\','/'))
from fastapi.testclient import TestClient
from . import platform_agent
from .db import PlatformConnection, User
from .main import app
from .test_linkedin import Db, PROFILE, SETTINGS, linkedin_site

LOGGED_OUT='<html><body><h1>Sign in</h1><input type="password" name="password"><button>Sign in</button></body></html>'
LOGGED_IN='<html><body><h1>Feed</h1><p>Welcome back.</p></body></html>'

class MockPage:
    def __init__(self, html):
        self.html = html
        self.url = 'https://www.linkedin.com/feed/'
    async def goto(self, url, **kwargs):
        self.url = url
    async def wait_for_timeout(self, ms):
        pass
    async def evaluate(self, expr, *args):
        if 'Feed' in self.html:
            return False
        return True
    def locator(self, sel):
        class MockLoc:
            async def count(self): return 0
        return MockLoc()

class MockContext:
    def __init__(self, html):
        self.pages = [MockPage(html)]
    async def new_page(self):
        p = MockPage('')
        self.pages.append(p)
        return p

class MockBrowser:
    def __init__(self, html):
        self.contexts = [MockContext(html)]
    def is_connected(self):
        return True

def mock_playwright(html):
    @contextlib.asynccontextmanager
    async def _pw():
        b = MockBrowser(html)
        async def _connect(*args, **kwargs):
            return b
        yield SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=_connect))
    return _pw()

class CheckLoginTests(Db):
    def setUp(self):
        super().setUp()
        with self.Session() as db:
            db.add(User(id='u',email='c@example.invalid',password='x',profile=PROFILE,settings=SETTINGS));db.commit()
        platform_agent.CONNECT_SESSIONS.clear()

    def status(self):
        with patch.object(platform_agent,'Session',self.Session):
            return platform_agent.connected_platforms('u')

    def check(self,source,page_html,session=None,released=None,contexts=None):
        contexts=contexts if contexts is not None else []
        released=released if released is not None else []
        session=session or (lambda user_id,proxies=False:{'id':'s','connectUrl':'local','live_url':'https://live.example/x'})
        async def wrapped_session(user_id,proxies=False):return session(user_id,proxies=proxies)
        async def release(session_id):released.append(session_id)
        with patch.object(platform_agent,'Session',self.Session),patch.object(platform_agent,'user_browser_session',wrapped_session),\
             patch.object(platform_agent,'release_browser',release),patch.object(platform_agent,'async_playwright',lambda: mock_playwright(page_html)):
            return asyncio.run(platform_agent.check_login('u',source))


    def test_a_signed_out_platform_stays_unconnected_and_keeps_the_session_open_for_live_view(self):
        released=[]
        result=self.check('LinkedIn',LOGGED_OUT,released=released)
        self.assertEqual(result,{'connected':False,'live_url':'https://live.example/x'})
        self.assertEqual(released,[])
        with self.Session() as db:
            self.assertIsNone(db.query(PlatformConnection).filter_by(user_id='u',platform='LinkedIn').first())

    def test_a_signed_in_platform_is_confirmed_and_the_session_released(self):
        released=[]
        result=self.check('LinkedIn',LOGGED_IN,released=released)
        self.assertEqual(result,{'connected':True,'live_url':None})
        self.assertEqual(released,['s'])
        self.assertEqual(self.status(),{'LinkedIn':True,'Indeed':False,'Naukri':False,'Internshala':False})


    def test_a_second_poll_reuses_the_open_session_instead_of_paying_for_a_new_one(self):
        opened=[]
        def session(user_id,proxies=False):
            opened.append(1);return {'id':'s','connectUrl':'local','live_url':'https://live.example/x'}
        self.check('LinkedIn',LOGGED_OUT,session=session)
        self.check('LinkedIn',LOGGED_OUT,session=session)
        self.assertEqual(len(opened),1)

    def test_cancel_releases_the_session_without_marking_anything_connected(self):
        released=[]
        self.check('LinkedIn',LOGGED_OUT,released=released)
        self.assertIn(('u','LinkedIn'),platform_agent.CONNECT_SESSIONS)
        async def release(session_id):released.append(session_id)
        with patch.object(platform_agent,'release_browser',release):
            asyncio.run(platform_agent.cancel_login('u','LinkedIn'))
        self.assertEqual(released,['s'])
        self.assertNotIn(('u','LinkedIn'),platform_agent.CONNECT_SESSIONS)
        self.assertFalse(self.status()['LinkedIn'])

    def test_an_unknown_platform_is_refused(self):
        with self.assertRaises(Exception):
            asyncio.run(platform_agent.check_login('u','Glassdoor'))

    def test_connected_platforms_defaults_to_false_for_a_brand_new_user(self):
        with patch.object(platform_agent,'Session',self.Session):
            self.assertEqual(platform_agent.connected_platforms('nobody'),{'LinkedIn':False,'Indeed':False,'Naukri':False,'Internshala':False})


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app,headers={'origin':'http://127.0.0.1:3000'})
        self.client.__enter__()
        self.assertEqual(self.client.post('/api/auth/demo',json={}).status_code,200)
    def tearDown(self):self.client.__exit__(None,None,None)

    def test_integrations_reports_connected_status_per_platform(self):
        sources={s['name']:s['connected'] for s in self.client.get('/api/integrations').json()['sources']}
        self.assertEqual(sources,{'LinkedIn':False,'Indeed':False,'Naukri':False,'Internshala':False})

    def test_check_and_cancel_dispatch_to_platform_agent_by_name(self):
        calls=[]
        async def fake_check(user_id,source):calls.append(('check',source));return {'connected':True,'live_url':None}
        async def fake_cancel(user_id,source):calls.append(('cancel',source))
        with patch.object(platform_agent,'check_login',fake_check),patch.object(platform_agent,'cancel_login',fake_cancel):
            r=self.client.post('/api/connections/linkedin/check')
            self.assertEqual((r.status_code,r.json()),(200,{'connected':True,'live_url':None}))
            self.assertEqual(self.client.post('/api/connections/linkedin/cancel').status_code,200)
            r2=self.client.post('/api/connections/indeed/check')
            self.assertEqual((r2.status_code,r2.json()),(200,{'connected':True,'live_url':None}))
            self.assertEqual(self.client.post('/api/connections/indeed/cancel').status_code,200)
            r3=self.client.post('/api/connections/naukri/check')
            self.assertEqual((r3.status_code,r3.json()),(200,{'connected':True,'live_url':None}))
            self.assertEqual(self.client.post('/api/connections/naukri/cancel').status_code,200)
            r4=self.client.post('/api/connections/internshala/check')
            self.assertEqual((r4.status_code,r4.json()),(200,{'connected':True,'live_url':None}))
            self.assertEqual(self.client.post('/api/connections/internshala/cancel').status_code,200)
        self.assertEqual(calls,[('check','LinkedIn'),('cancel','LinkedIn'),('check','Indeed'),('cancel','Indeed'),('check','Naukri'),('cancel','Naukri'),('check','Internshala'),('cancel','Internshala')])

    def test_an_unknown_platform_name_is_refused(self):
        self.assertEqual(self.client.post('/api/connections/monster/check').status_code,404)
        self.assertEqual(self.client.post('/api/connections/monster/cancel').status_code,404)

    def test_connections_routes_require_login(self):
        fresh=TestClient(app,headers={'origin':'http://127.0.0.1:3000'})
        self.assertEqual(fresh.post('/api/connections/linkedin/check').status_code,401)

if __name__=='__main__':unittest.main()
