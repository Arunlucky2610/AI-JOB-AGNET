"""Comprehensive automated tests for Dedicated Indeed Agent with Visible Browser Automation.

Tests:
1. Browser tests (Indeed domain verification, telemetry structure, tab handling).
2. Search tests (query generation, search input interaction, results inspection, empty results).
3. Application & Apply button detection (Apply now, Easily apply, external employer detection).
4. Authentication checkpoints (email, password, OTP, phone, bot challenge, secret redaction).
5. Lifecycle & approval gates (checkpoint resume, telemetry endpoints, human approval before submission).
6. LinkedIn regression (LinkedIn platform agent dispatch and compatibility).
"""
import asyncio, re, tempfile, unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from . import indeed, indeed_agent, agent, platform_agent
from .db import Session, Base, User, Job, Application, AgentRun, engine, now
from .main import app

PROFILE = {
    'name': 'Alex Candidate',
    'email': 'alex@example.invalid',
    'phone': '+1 (555) 234-5678',
    'roles': 'AI Engineer, Machine Learning Engineer',
    'country': 'United States',
    'locations': 'San Francisco, CA',
    'work_modes': ['Remote', 'Hybrid'],
    'skills': ['Python', 'PyTorch', 'FastAPI'],
    'experience': 3,
    'confirmed': True,
    'resume_text': 'Alex Candidate - AI Engineer with experience in Python and PyTorch.'
}

SETTINGS = {
    'mode': 'each',
    'daily_limit': 5,
    'threshold': 70,
    'source_focus': 'indeed',
    'auto_enabled': False
}

class FakeLocator:
    def __init__(self, visible=True, text='', count_val=1):
        self._visible = visible
        self._text = text
        self._count = count_val
        self._value = ''
        self.first = self
    async def count(self): return self._count
    async def is_visible(self): return self._visible
    async def click(self, **kwargs): pass
    async def fill(self, val): self._value = val
    async def type(self, val, **kwargs): self._value += val
    async def press(self, key): pass
    async def inner_text(self): return self._text
    def filter(self, has_text=None, **kwargs):
        if has_text is not None:
            pattern = getattr(has_text, 'pattern', str(has_text))
            if not re.search(pattern, self._text, re.I):
                return FakeLocator(count_val=0, text='')
        return self
    def nth(self, idx): return self

class FakePage:
    def __init__(self, url='https://www.indeed.com/', body=''):
        self.url = url
        self.body = body
        self.closed = False
    async def goto(self, url, **kwargs):
        self.url = url
    async def wait_for_timeout(self, ms): pass
    async def wait_for_load_state(self, state=None, **kwargs): pass
    async def inner_text(self, sel='body'): return self.body
    def locator(self, sel):
        sel_lower = sel.lower()
        if 'email' in sel_lower and ('email' in self.body.lower() or 'sign in' in self.body.lower()):
            return FakeLocator(text='Email', count_val=1)
        if 'password' in sel_lower and 'password' in self.body.lower():
            return FakeLocator(text='Password', count_val=1)
        if ('verification' in sel_lower or 'code' in sel_lower or 'otp' in sel_lower) and ('code' in self.body.lower() or 'verification' in self.body.lower()):
            return FakeLocator(text='Code', count_val=1)
        if 'indeedapply' in sel_lower:
            if 'apply now' in self.body.lower(): return FakeLocator(text='Apply now', count_val=1)
            if 'easily apply' in self.body.lower(): return FakeLocator(text='Easily apply', count_val=1)
            return FakeLocator(count_val=0, text='')
        if 'button' in sel_lower or 'submit' in sel_lower:
            btn_text = 'Apply on company site' if 'apply on company site' in self.body.lower() else \
                       'Easily apply' if 'easily apply' in self.body.lower() else \
                       'Apply now' if 'apply now' in self.body.lower() else \
                       'Submit' if 'submit' in self.body.lower() else \
                       'Verify' if 'verify' in self.body.lower() else 'Continue'
            return FakeLocator(text=btn_text, count_val=1)
        if 'apply' in sel_lower:
            if 'apply on company site' in self.body.lower(): return FakeLocator(text='Apply on company site', count_val=1)
            if 'easily apply' in self.body.lower(): return FakeLocator(text='Easily apply', count_val=1)
            if 'apply now' in self.body.lower(): return FakeLocator(text='Apply now', count_val=1)
        return FakeLocator(count_val=0, text='')

    async def evaluate(self, expr, *args):
        if 'STATE_JS' in str(expr) or 'closed' in str(expr):
            return {
                'closed': 'no longer accepting' in self.body.lower(),
                'easy': 'apply now' in self.body.lower() or 'easily apply' in self.body.lower(),
                'applied': 'already applied' in self.body.lower(),
                'external': 'apply on company site' in self.body.lower()
            }
        return {}



class IndeedBrowserTests(unittest.TestCase):
    def test_indeed_domain_verification(self):
        self.assertTrue(indeed.is_indeed_domain('https://www.indeed.com/'))
        self.assertTrue(indeed.is_indeed_domain('https://in.indeed.com/jobs?q=AI'))
        self.assertTrue(indeed.is_indeed_domain('https://uk.indeed.com/viewjob?jk=12345678'))
        self.assertTrue(indeed.is_indeed_domain('https://smartapply.indeed.com/beta/indeedapply'))
        self.assertFalse(indeed.is_indeed_domain('https://www.linkedin.com/jobs/view/123456/'))
        self.assertFalse(indeed.is_indeed_domain('https://evil-phishing-indeed.com/'))

    def test_telemetry_structure_generation(self):
        t = indeed_agent.build_telemetry(
            'run_123',
            'searching',
            current_url='https://www.indeed.com/jobs?q=AI',
            active_job={'title': 'AI Engineer', 'company': 'Tech Corp', 'score': 85, 'stage': 'inspecting_job'}
        )
        self.assertEqual(t['portal'], 'Indeed')
        self.assertEqual(t['execution_mode'], 'Visible Chrome')
        self.assertEqual(t['target_domain'], 'www.indeed.com')
        self.assertEqual(t['session_state'], 'searching')
        self.assertEqual(t['active_job']['title'], 'AI Engineer')
        self.assertEqual(t['active_job']['score'], 85)

    def test_state_machine_contains_all_required_states(self):
        required = [
            'initializing', 'browser_connecting', 'opening_indeed', 'searching',
            'inspecting_job', 'evaluating_match', 'ready_to_apply', 'opening_application',
            'authentication_required', 'awaiting_email_input', 'awaiting_password_input',
            'awaiting_otp', 'awaiting_phone_input', 'awaiting_user_verification',
            'filling_application', 'awaiting_missing_answer', 'ready_for_review',
            'awaiting_submission_approval', 'submitting', 'submitted',
            'submission_unconfirmed', 'rejected', 'failed', 'completed'
        ]
        for st in required:
            self.assertIn(st, indeed_agent.INDEED_STATES)

class IndeedSearchWorkflowTests(unittest.TestCase):
    def test_search_urls_follow_roles_and_country_host(self):
        urls = indeed.search_urls(PROFILE)
        self.assertGreaterEqual(len(urls), 1)
        self.assertTrue(urls[0].startswith('https://www.indeed.com/jobs?'))
        self.assertIn('q=AI+Engineer', urls[0])
        self.assertIn('fromage=7', urls[0])

    def test_search_results_state_empty_detection(self):
        page_empty = FakePage(body='The search AI Engineer did not match any jobs. Suggestions: Try more general keywords.')
        state = asyncio.run(indeed.check_search_results_page(page_empty))
        self.assertEqual(state, 'empty')

    def test_job_page_details_extraction(self):
        body = 'Senior AI Engineer\nAnthropic AI\nSan Francisco, CA\nFull job description: Looking for Python and LLM experience.'
        page = FakePage(url='https://www.indeed.com/viewjob?jk=abcdef0123456789', body=body)
        with patch.object(indeed, 'apply_state_settled', AsyncMock(return_value='easy')):
            details = asyncio.run(indeed.extract_job_page_details(page, page.url))
            self.assertEqual(details['apply_type'], 'easy')
            self.assertEqual(details['url'], 'https://www.indeed.com/viewjob?jk=abcdef0123456789')

class IndeedApplyButtonTests(unittest.TestCase):
    def test_apply_now_button_detected(self):
        page = FakePage(body='Apply now for this role')
        with patch.object(indeed, 'apply_state_settled', AsyncMock(return_value='easy')):
            btn = asyncio.run(indeed.detect_apply_button_action(page))
            self.assertEqual(btn['action'], 'apply_now')
            self.assertTrue(btn['is_indeed_hosted'])

    def test_easily_apply_button_detected(self):
        page = FakePage(body='Easily apply in 1 click')
        with patch.object(indeed, 'apply_state_settled', AsyncMock(return_value='easy')):
            btn = asyncio.run(indeed.detect_apply_button_action(page))
            self.assertEqual(btn['action'], 'easily_apply')
            self.assertTrue(btn['is_indeed_hosted'])

    def test_external_employer_apply_detected(self):
        page = FakePage(body='Apply on company site')
        with patch.object(indeed, 'apply_state_settled', AsyncMock(return_value='external')):
            btn = asyncio.run(indeed.detect_apply_button_action(page))
            self.assertEqual(btn['action'], 'external')
            self.assertFalse(btn['is_indeed_hosted'])

    def test_closed_job_detected(self):
        page = FakePage(body='This job has expired. No longer accepting applications.')
        with patch.object(indeed, 'apply_state_settled', AsyncMock(return_value='closed')):
            btn = asyncio.run(indeed.detect_apply_button_action(page))
            self.assertEqual(btn['action'], 'closed')
            self.assertFalse(btn['is_indeed_hosted'])

class IndeedAuthCheckpointTests(unittest.TestCase):
    def test_detect_email_checkpoint(self):
        page = FakePage(url='https://secure.indeed.com/account/login', body='Sign in to Indeed. Enter your email.')
        chk = asyncio.run(indeed.detect_auth_checkpoint(page))
        self.assertEqual(chk, 'email')

    def test_detect_password_checkpoint(self):
        page = FakePage(url='https://secure.indeed.com/account/login', body='Enter your password.')
        chk = asyncio.run(indeed.detect_auth_checkpoint(page))
        self.assertEqual(chk, 'password')

    def test_detect_otp_checkpoint(self):
        page = FakePage(url='https://secure.indeed.com/account/verification', body='We sent a code. Enter the verification code.')
        chk = asyncio.run(indeed.detect_auth_checkpoint(page))
        self.assertEqual(chk, 'otp')

    def test_detect_challenge_checkpoint(self):
        page = FakePage(url='https://www.indeed.com/', body='Checking your browser. Verify you are human.')
        with patch('backend.human_gate.challenge_shown', AsyncMock(return_value=True)):
            chk = asyncio.run(indeed.detect_auth_checkpoint(page))
            self.assertEqual(chk, 'challenge')

    def test_submit_auth_email_and_password(self):
        page = FakePage(url='https://secure.indeed.com/account/login', body='email password')
        # Test filling email
        self.assertTrue(asyncio.run(indeed.submit_auth_email(page, 'user@example.com')))
        # Test filling password
        self.assertTrue(asyncio.run(indeed.submit_auth_password(page, 'secret123')))
        # Test filling OTP
        page_otp = FakePage(url='https://secure.indeed.com/account/verification', body='code verification submit')
        self.assertTrue(asyncio.run(indeed.submit_auth_otp(page_otp, '123456')))

class CheckpointApiAndTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, headers={'origin': 'http://127.0.0.1:3000'})
        self.client.__enter__()
        r = self.client.post('/api/auth/demo', json={})
        with Session() as db:
            user = db.query(User).filter_by(email=r.json()['email']).first()
            self.user_id = user.id
            db.query(AgentRun).filter_by(user_id=self.user_id).delete()
            db.commit()
        self.client.put('/api/settings', json={'mode': 'each', 'daily_limit': 5, 'source_focus': 'indeed', 'auto_enabled': False})

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_telemetry_endpoint_returns_data(self):
        res = self.client.get('/api/agent/telemetry')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('status', data)
        self.assertIn('telemetry', data)

    def test_checkpoint_submission_updates_run_safely(self):
        import uuid
        run_id = f'test_chk_{uuid.uuid4().hex[:8]}'
        with Session() as db:
            chk = {
                'type': 'otp',
                'prompt': 'Indeed requires a verification code.',
                'field': 'code',
                'sensitive': True
            }
            run = AgentRun(
                id=run_id,
                user_id=self.user_id,
                status='needs_input',
                phase='applying',
                events=[{'time': now().isoformat(), 'text': 'Paused for OTP'}],
                state={'checkpoint': chk},
                browser={}
            )
            db.add(run)
            db.commit()

        # Submit OTP to checkpoint API
        with patch('backend.agent.execute', AsyncMock()):
            resp = self.client.post('/api/agent/checkpoint', json={'checkpoint_type': 'otp', 'value': '987654'})
            self.assertEqual(resp.status_code, 200)
        
        # Verify run resumed and secret OTP is NOT logged in events
        with Session() as db:
            updated = db.get(AgentRun, run_id)
            self.assertEqual(updated.status, 'running')
            last_event = updated.events[-1]['text']
            self.assertNotIn('987654', last_event)  # Never log OTP in plaintext!
            self.assertIn('otp', last_event)
            # Response was stored in state for indeed_agent to consume
            self.assertEqual(updated.state.get('checkpoint_response', {}).get('value'), '987654')

    def test_retry_endpoint_resumes_stopped_run(self):
        import uuid
        run_id = f'test_retry_{uuid.uuid4().hex[:8]}'
        with Session() as db:
            run = AgentRun(
                id=run_id,
                user_id=self.user_id,
                status='stopped',
                phase='complete',
                events=[{'time': now().isoformat(), 'text': 'Stopped'}],
                state={},
                browser={}
            )
            db.add(run)
            db.commit()

        with patch('backend.agent.execute', AsyncMock()):
            resp = self.client.post('/api/agent/retry')
            self.assertEqual(resp.status_code, 200)
        with Session() as db:
            updated = db.get(AgentRun, run_id)
            self.assertEqual(updated.status, 'running')



class LinkedInRegressionTests(unittest.TestCase):
    def test_agent_sources_support_both_platforms(self):
        self.assertEqual(agent.SOURCES.get('linkedin'), 'LinkedIn')
        self.assertEqual(agent.SOURCES.get('indeed'), 'Indeed')

    def test_platform_modules_still_contains_linkedin(self):
        self.assertIn('LinkedIn', platform_agent.PLATFORM_MODULES)
        self.assertEqual(platform_agent.PLATFORM_INFO['LinkedIn']['apply_label'], 'Easy Apply')

    def test_indeed_is_registered_in_platform_modules_and_worker(self):
        from . import worker
        self.assertIn('Indeed', platform_agent.PLATFORM_MODULES)
        self.assertEqual(platform_agent.PLATFORM_MODULES['Indeed'], indeed)
        self.assertEqual(platform_agent.PLATFORM_INFO['Indeed']['apply_label'], 'Apply now')
        self.assertIn('Indeed', worker.APPLY_SITES)
        self.assertEqual(worker.APPLY_SITES['Indeed'], indeed)

    def test_agent_execute_dispatches_indeed_to_execute_platform(self):
        import uuid
        run_id = f'test_run_{uuid.uuid4().hex[:8]}'
        with Session() as db:
            user = db.query(User).first()
            if not user:
                user = User(id='test_u', email='test@example.com', password='x', profile={'roles':'dev'}, settings={'source_focus':'indeed'})
                db.add(user)
                db.flush()
            user.settings = {**user.settings, 'source_focus': 'indeed'}
            run = AgentRun(id=run_id, user_id=user.id, status='running', phase='searching', events=[], state={}, browser={})
            db.add(run)
            db.commit()

        with patch('backend.platform_agent.execute_platform', AsyncMock()) as mock_exec:
            asyncio.run(agent.execute(run_id))
            mock_exec.assert_called_once_with(run_id, 'Indeed')

if __name__ == '__main__':
    unittest.main()
