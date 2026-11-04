"""Unit and integration tests for the Find Jobs discovery engine, scoring, SSRF validation, and API routes."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

TEST_DIR = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(TEST_DIR.name) / 'test_find_jobs.db').replace('\\', '/')
os.environ['ALLOW_DEMO'] = 'true'

from fastapi.testclient import TestClient
from .main import app
from .db import Session, Job, DiscoveryRun, engine, now
from .domain import DEMO_PROFILE
from .discovery.url_validator import validate_url, canonicalize_url
from .discovery.query_generator import generate_targeted_queries
from .discovery.matching import calculate_match

def tearDownModule():
    engine.dispose()

class FindJobsUnitTests(unittest.TestCase):
    def test_ssrf_url_validation(self):
        """Verify strict SSRF prevention for private IPs and dangerous schemes."""
        dangerous_urls = [
            "http://127.0.0.1/admin",
            "http://localhost:8000/api",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/internal",
            "http://192.168.1.1/router",
            "http://172.16.0.1/private",
            "file:///etc/passwd",
            "ftp://ftp.example.com/file",
            "javascript:alert(1)",
            "data:text/html,<html></html>",
            "http://[::1]/secret",
            "",
            None,
        ]
        for url in dangerous_urls:
            is_safe, reason = validate_url(url)
            self.assertFalse(is_safe, f"Expected {url} to be unsafe, but got safe. Reason: {reason}")

        safe_urls = [
            "https://boards.greenhouse.io/stripe/jobs/12345",
            "https://jobs.lever.co/postings/abc-123",
            "https://jobs.ashbyhq.com/openai/xyz",
            "https://careers.google.com/jobs/results/987654",
        ]
        for url in safe_urls:
            is_safe, reason = validate_url(url)
            self.assertTrue(is_safe, f"Expected {url} to be safe, but got unsafe: {reason}")

    def test_canonicalize_job_url(self):
        """Verify query param stripping, lowercase domain, and clean URL representation."""
        dirty = "https://Boards.Greenhouse.io/Company/jobs/12345?utm_source=linkedin&utm_medium=job_board&ref=tracker"
        clean = canonicalize_url(dirty)
        self.assertEqual(clean, "https://boards.greenhouse.io/Company/jobs/12345")

    def test_query_generation(self):
        """Verify queries reflect profile preferences without hardcoded values."""
        profile = {
            "roles": "Python Developer, Backend Engineer",
            "skills": "Python, FastAPI, SQL",
            "locations": "Hyderabad, Bengaluru",
            "country": "India",
            "experience": "0",
            "work_modes": ["Remote", "Hybrid"],
        }
        queries = generate_targeted_queries(profile, {"matching": "strict"})
        self.assertTrue(len(queries) > 0)
        
        # Check that query terms include profile roles, locations, or skills
        combined_queries = " ".join(queries).lower()
        self.assertIn("python", combined_queries)
        self.assertTrue("india" in combined_queries or "hyderabad" in combined_queries or "bengaluru" in combined_queries)
        self.assertTrue(any("greenhouse.io" in q or "lever.co" in q or "ashbyhq.com" in q for q in queries))

    def test_multi_factor_scoring(self):
        """Verify 0-100 score breakdown across roles, skills, and work mode."""
        candidate = {
            "roles": "Python Developer, Backend Engineer",
            "skills": "Python, FastAPI, PostgreSQL, Docker",
            "locations": "Bengaluru",
            "country": "India",
            "experience": "1",
            "work_modes": ["Remote", "Hybrid"],
            "eligibility": "Authorized to work in India",
        }

        # Strong matching listing
        job_strong = {
            "title": "Junior Python Backend Developer",
            "company": "Tech Innovations",
            "description": "We are seeking a Junior Python Backend Developer skilled in Python, FastAPI, and PostgreSQL. Hybrid role in Bengaluru, India.",
            "location": "Bengaluru, India",
            "mode": "Hybrid",
            "skills": ["Python", "FastAPI", "PostgreSQL"],
        }
        match_strong = calculate_match(candidate, job_strong, {"threshold": 60})
        self.assertGreaterEqual(match_strong["score"], 65)
        self.assertTrue(match_strong["matched"])
        self.assertIn("python", [s.lower() for s in match_strong["matched_skills"]])

        # Irrelevant listing
        job_mismatch = {
            "title": "Chief Financial Officer (CFO)",
            "company": "Finance Corp",
            "description": "Requires 15+ years of corporate accounting and SEC reporting in New York.",
            "location": "New York, NY",
            "mode": "Onsite",
            "skills": ["Accounting", "GAAP", "SEC"],
        }
        match_mismatch = calculate_match(candidate, job_mismatch, {"threshold": 60})
        self.assertLess(match_mismatch["score"], 50)
        self.assertFalse(match_mismatch["matched"])


class FindJobsApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, headers={'origin': 'http://127.0.0.1:3000'})
        self.client.__enter__()
        # Authenticate demo user
        r = self.client.post('/api/auth/demo', json={})
        self.assertEqual(r.status_code, 200)

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_find_jobs_starts_run_and_status(self):
        """Test POST /api/jobs/find starts a discovery run and GET status tracks it."""
        # Trigger discovery run
        res = self.client.post('/api/jobs/find', json={})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('run_id', data)
        self.assertEqual(data['status'], 'running')

        # Check status endpoint
        status_res = self.client.get('/api/jobs/discover/status')
        self.assertEqual(status_res.status_code, 200)
        st = status_res.json()
        self.assertEqual(st['id'], data['run_id'])
        self.assertIn(st['status'], ['running', 'completed', 'completed_with_warnings'])
        self.assertIn('progress', st)

        # Test cancel endpoint
        cancel_res = self.client.post('/api/jobs/discover/cancel')
        self.assertEqual(cancel_res.status_code, 200)
        self.assertIn(cancel_res.json()['status'], ['cancelled', 'completed', 'completed_with_warnings'])

    def test_jobs_filtering_and_sorting(self):
        """Test GET /api/jobs with query filters for min_score, source, mode, and sorting."""
        # Query all jobs
        all_jobs = self.client.get('/api/jobs').json()
        self.assertIsInstance(all_jobs, list)
        self.assertGreater(len(all_jobs), 0)

        # Filter by high score
        high_score_jobs = self.client.get('/api/jobs?min_score=80').json()
        for j in high_score_jobs:
            self.assertGreaterEqual(j['match']['score'], 80)

        # Filter by work mode
        remote_jobs = self.client.get('/api/jobs?mode=Remote').json()
        for j in remote_jobs:
            self.assertEqual(j['mode'], 'Remote')

        # Sort by title
        sorted_jobs = self.client.get('/api/jobs?sort_by=company_asc').json()
        companies = [j['company'].lower() for j in sorted_jobs]
        self.assertEqual(companies, sorted(companies))

    def test_verify_job_listing(self):
        """Test POST /api/jobs/{id}/verify returns verified status and persists verification date."""
        all_jobs = self.client.get('/api/jobs').json()
        self.assertTrue(len(all_jobs) > 0)
        target_id = all_jobs[0]['id']

        with patch('backend.discovery.freshness.verify_job_freshness') as mock_verify:
            mock_verify.return_value = {
                "status": "active",
                "http_status": 200,
                "verified_at": now().isoformat(),
                "reason": "Listing page is accessible (HTTP 200)",
                "final_url": "https://example.com/job/1"
            }
            res = self.client.post(f'/api/jobs/{target_id}/verify')
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data['status'], 'active')
            self.assertEqual(data['verification']['status'], 'open')
            self.assertIsNotNone(data['verification']['verified_at'])
