"""Comprehensive unit and integration tests for RapidSkill enhancements:
- User profile & resume file persistence & versioning
- Modular job discovery & normalization
- Strict AI match scoring schema
- Application material generation (tailored resume, cover letter, recruiter message, diffs)
- Integration connection testing and configuration
- Orchestration engine 11-state lifecycle
"""
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

os.environ.setdefault('DATABASE_URL', 'sqlite:///' + str(Path(tempfile.gettempdir()) / 'rapidskill-test.db').replace('\\', '/'))
from backend.main import app
from backend.db import Session, User, Job, Application, Resume, ResumeVersion, IntegrationCredential, ApplicationMaterial, init
from backend.domain import EMPTY_PROFILE
from backend.ai_engine import JobMatchSchema, AIJobMatcher, DeterministicFallbackProvider
from backend.discovery.base import DiscoveredJob
from backend.orchestration_engine import ApplicationState

class RapidSkillFeatureTests(unittest.TestCase):
    def setUp(self):
        init()
        self.client = TestClient(app, headers={'origin': 'http://127.0.0.1:3000'})
        login_res = self.client.post('/api/auth/demo', json={})
        self.user_data = self.client.get('/api/me').json()
        with Session() as db:
            self.user = db.query(User).filter_by(email=self.user_data['email']).first()

    def test_resume_persistence_and_versioning(self):
        """Test uploading a resume saves the file to disk, creates version 1, and allows downloading."""
        fake_pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>startxref\n0\n%%EOF"
        
        # Test upload
        res = self.client.post(
            '/api/profile/resume',
            files={'file': ('my_resume.txt', b'Jane Doe\nSoftware Engineer\nSkills: Python, TypeScript, React\nExperience: Engineer at TechCorp 2022-2024\nEducation: BS CS 2022', 'text/plain')}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('id', data)
        self.assertEqual(data['version'], 1)
        self.assertEqual(data['filename'], 'my_resume.txt')
        self.assertIn('skills', data.get('fields', {}))

        # Verify listing
        res_list = self.client.get('/api/profile/resumes')
        self.assertEqual(res_list.status_code, 200)
        items = res_list.json()
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(items[0]['id'], data['id'])

        # Verify secure download
        download_res = self.client.get(f"/api/profile/resumes/{data['id']}/download")
        self.assertEqual(download_res.status_code, 200)
        self.assertIn(b'Jane Doe', download_res.content)

    def test_job_sources_and_discovery(self):
        """Test modular job discovery returns normalized jobs and saves them to user's database."""
        sources_res = self.client.get('/api/jobs/sources')
        self.assertEqual(sources_res.status_code, 200)
        providers = [p['name'] for p in sources_res.json()]
        self.assertIn('JobSpy', providers)
        self.assertIn('LinkedIn', providers)

        # Mock discovery search
        mock_job = DiscoveredJob(
            external_id='ext_test_101',
            source='JobSpy',
            title='Staff AI Platform Engineer',
            company='Apex Technologies',
            location='San Francisco, CA',
            country='USA',
            work_mode='Remote',
            employment_type='Full-time',
            salary='$180k – $220k',
            description='Build next-generation agentic AI infrastructure using Python and React.',
            url='https://example.com/jobs/apex-101',
            required_skills=['Python', 'React', 'AI']
        )

        with patch('backend.discovery.jobspy_provider.JobSpyProvider.search', new=AsyncMock(return_value=[mock_job])):
            discover_res = self.client.post('/api/jobs/discover', json={
                'query': 'AI Platform Engineer',
                'location': 'San Francisco',
                'is_remote': True,
                'limit': 5
            })
            self.assertEqual(discover_res.status_code, 200)
            data = discover_res.json()
            self.assertGreaterEqual(data['count'], 1)
            self.assertEqual(data['jobs'][0]['company'], 'Apex Technologies')

            # Verify saved into user's jobs list
            jobs_list = self.client.get('/api/jobs').json()
            found = [j for j in jobs_list if j.get('company') == 'Apex Technologies']
            self.assertTrue(len(found) > 0)

    def test_ai_match_scoring_schema(self):
        """Test Phase 4 AI match evaluation generates schema-compliant structured output."""
        import uuid
        jid = f"job_match_{uuid.uuid4().hex[:8]}"
        with Session() as db:
            job = Job(
                id=jid,
                user_id=self.user.id,
                canonical=f"https://example.com/test-match-{jid}",
                payload={
                    'title': 'Senior Python Engineer',
                    'company': 'QuantumScale',
                    'location': 'Remote',
                    'country': 'United States',
                    'mode': 'Remote',
                    'skills': ['Python', 'FastAPI', 'PostgreSQL'],
                    'description': 'Senior Python role requiring 3+ years experience with FastAPI.'
                }
            )
            db.add(job)
            db.commit()

        res = self.client.post(f"/api/jobs/{jid}/match")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Validate with Pydantic
        schema = JobMatchSchema(**data)
        self.assertIsInstance(schema.match_score, int)
        self.assertIsInstance(schema.matching_skills, list)
        self.assertIsInstance(schema.missing_required_skills, list)
        self.assertIsInstance(schema.experience_alignment, str)
        self.assertIsInstance(schema.location_alignment, str)
        self.assertIsInstance(schema.salary_alignment, str)
        self.assertIsInstance(schema.recommendation, str)

    def test_material_generation_and_diffs(self):
        """Test tailored resume, cover letter, recruiter message and diff generation."""
        import uuid
        jid = f"job_mat_{uuid.uuid4().hex[:8]}"
        aid = f"app_mat_{uuid.uuid4().hex[:8]}"
        with Session() as db:
            job = Job(
                id=jid,
                user_id=self.user.id,
                canonical=f"https://example.com/test-mat-{jid}",
                payload={
                    'title': 'Frontend Engineer',
                    'company': 'DesignCo',
                    'skills': ['React', 'TypeScript'],
                    'description': 'Frontend engineer with React experience.'
                }
            )
            db.add(job)
            app_rec = Application(
                id=aid,
                user_id=self.user.id,
                job_id=jid,
                status='prepared',
                package={'resume': 'Original resume text', 'cover_letter': '', 'notes': []}
            )
            db.add(app_rec)
            db.commit()

        res = self.client.post(f"/api/applications/{aid}/materials")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('tailored_resume', data)
        self.assertIn('cover_letter', data)
        self.assertIn('recruiter_message', data)
        self.assertIn('diff', data)

        # Verify materials listing
        mats = self.client.get(f"/api/applications/{aid}/materials").json()
        self.assertGreaterEqual(len(mats), 3)

    def test_integration_connection_tests_and_configuration(self):
        """Test live connection checks for OpenRouter and Browserbase."""
        # Test invalid or missing key reports clean error
        res_or = self.client.post('/api/integrations/test/openrouter', json={'api_key': 'invalid_test_key'})
        self.assertEqual(res_or.status_code, 200)
        self.assertFalse(res_or.json()['connected'])

        res_bb = self.client.post('/api/integrations/test/browserbase', json={'api_key': 'invalid_bb_key'})
        self.assertEqual(res_bb.status_code, 200)
        self.assertFalse(res_bb.json()['connected'])

        # Test configure endpoint
        conf_res = self.client.post('/api/integrations/configure', json={
            'openrouter_api_key': 'sk-or-test-mock',
            'model': 'deepseek/deepseek-v4-flash-0731'
        })
        self.assertEqual(conf_res.status_code, 200)
        self.assertTrue(conf_res.json()['configured']['openrouter'])

    def test_orchestration_state_lifecycle(self):
        """Verify the 11 Human-in-the-Loop states exist and are valid."""
        expected_states = [
            'READY', 'AUTHENTICATION_REQUIRED', 'OTP_REQUIRED', 'CAPTCHA_REQUIRED',
            'USER_REVIEW_REQUIRED', 'SUBMISSION_READY', 'SUBMISSION_PENDING',
            'SUBMITTED', 'SUBMISSION_UNCERTAIN', 'FAILED', 'CANCELLED'
        ]
        for s in expected_states:
            self.assertEqual(ApplicationState(s).value, s)
