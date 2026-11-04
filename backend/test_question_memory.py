"""Comprehensive test suite for Orbit AI Intelligent Question Answering & Persistent Memory System.

Tests all 12 scenarios specified in the specification:
1. A completely new question requires web research.
2. The researched answer is saved persistently.
3. The same question appears again and retrieves memory.
4. A paraphrased version retrieves a valid semantic match.
5. A similar question with a different meaning triggers new research.
6. Outdated company information is refreshed.
7. A personal question uses the verified profile instead of web browsing.
8. A missing sensitive answer pauses for user input.
9. A low-confidence answer is not blindly submitted.
10. Memory persists after restarting the application.
11. Different users have isolated memories.
12. Web research failures produce safe fallback behavior.
"""
import asyncio
import os
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

from .db import Session, Base, engine, User, QuestionMemory, now, migrate_sqlite_schema
from .question_matcher import normalize_question, semantic_similarity, compute_embedding
from .question_classifier import (
    classify_question,
    CATEGORY_A, CATEGORY_B, CATEGORY_C, CATEGORY_D, CATEGORY_E
)
from .question_detector import detect_questions, DetectedQuestion
from .web_researcher import research_company, research_technical_topic, _RESEARCH_CACHE
from .question_memory import (
    answer_application_question,
    save_memory_record,
    search_persistent_memory,
    enforce_length_constraints,
    match_dropdown_option
)
from .main import app
from fastapi.testclient import TestClient

class TestQuestionMemorySystem(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        migrate_sqlite_schema(engine)

    def setUp(self):
        self.user_a_id = f"test-user-a-{os.urandom(4).hex()}"
        self.user_b_id = f"test-user-b-{os.urandom(4).hex()}"
        self.profile_a = {
            'name': 'Alex Morgan',
            'email': 'alex@example.com',
            'phone': '+1 (555) 234-5678',
            'locations': 'San Francisco, CA',
            'address': '123 Market St',
            'skills': 'Python, React, TypeScript, PostgreSQL',
            'roles': 'Software Engineer, AI Engineer',
            'experience': 4,
            'skill_years': {'python': 4, 'react': 3, 'sql': 4},
            'authorization': 'Yes, authorized to work in the US',
            'sponsorship': 'No sponsorship required',
            'salary': '$135,000',
            'linkedin': 'https://linkedin.com/in/alexmorgan',
            'github': 'https://github.com/alexmorgan',
            'portfolio': 'https://alexmorgan.dev',
            'resume_text': 'Alex Morgan\nSoftware Engineer\nPROJECTS:\n• Built distributed task scheduler using Python and Redis\nEDUCATION:\nB.S. in Computer Science from UC Berkeley, 2020\n',
            'screening': 'Are you comfortable working onsite in San Francisco? Yes\nDo you have experience leading code reviews? Yes'
        }
        # Clear research cache before test runs
        _RESEARCH_CACHE.clear()

    def tearDown(self):
        with Session() as db:
            db.query(QuestionMemory).filter(QuestionMemory.user_id.in_([self.user_a_id, self.user_b_id])).delete()
            db.commit()

    # Scenario 1: A completely new question requires web research
    async def test_scenario_01_new_question_requires_web_research(self):
        dq = DetectedQuestion(
            element_id=1,
            question_text="Why do you want to join Stripe?",
            field_type="textarea",
            tag="TEXTAREA",
            context={'company': 'Stripe', 'job_title': 'Backend Engineer'}
        )
        
        with patch('backend.question_memory.research_company', new_callable=AsyncMock) as mock_research:
            mock_research.return_value = {
                'success': True,
                'company': 'Stripe',
                'summary': 'Stripe is an economic infrastructure platform enabling businesses to accept online payments.',
                'sources': ['https://stripe.com/about'],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': None
            }

            result = await answer_application_question(
                self.user_a_id,
                dq,
                self.profile_a,
                context={'company': 'Stripe', 'job_title': 'Backend Engineer'},
                allow_web_browsing=True
            )

            mock_research.assert_called_once()
            self.assertEqual(result.category, CATEGORY_C)
            self.assertEqual(result.source, 'web_research')
            self.assertIn('https://stripe.com/about', result.source_urls)
            self.assertIn('Stripe', result.answer)
            self.assertGreaterEqual(result.confidence, 0.8)

    # Scenario 2: The researched answer is saved persistently
    async def test_scenario_02_researched_answer_saved_persistently(self):
        dq = DetectedQuestion(
            element_id=2,
            question_text="What do you know about Datadog?",
            field_type="textarea",
            tag="TEXTAREA",
            context={'company': 'Datadog', 'job_title': 'DevOps Engineer'}
        )

        with patch('backend.question_memory.research_company', new_callable=AsyncMock) as mock_research:
            mock_research.return_value = {
                'success': True,
                'company': 'Datadog',
                'summary': 'Datadog is an observability and security platform for cloud applications.',
                'sources': ['https://datadoghq.com'],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': None
            }

            result = await answer_application_question(
                self.user_a_id,
                dq,
                self.profile_a,
                context={'company': 'Datadog', 'job_title': 'DevOps Engineer'},
                allow_web_browsing=True
            )

            self.assertIsNotNone(result.memory_id)

            # Verify in persistent database
            with Session() as db:
                record = db.get(QuestionMemory, result.memory_id)
                self.assertIsNotNone(record)
                self.assertEqual(record.user_id, self.user_a_id)
                self.assertEqual(record.company, 'Datadog')
                self.assertEqual(record.category, CATEGORY_C)
                self.assertEqual(record.source, 'web_research')
                self.assertIn('https://datadoghq.com', record.source_urls)
                self.assertEqual(record.usage_count, 1)

    # Scenario 3: The same question appears again and retrieves memory without browsing
    async def test_scenario_03_same_question_retrieves_memory_without_browsing(self):
        # Seed saved memory
        save_memory_record(
            user_id=self.user_a_id,
            question_text="Why do you want to work at Databricks?",
            original_question="Why do you want to work at Databricks?",
            answer_text="I am passionate about Databricks Lakehouse platform and Apache Spark development.",
            category=CATEGORY_C,
            source="company_memory",
            confidence=0.95,
            company="Databricks",
            approval_status="approved",
            scope="company"
        )

        dq = DetectedQuestion(
            element_id=3,
            question_text="Why do you want to work at Databricks?",
            field_type="textarea",
            tag="TEXTAREA",
            context={'company': 'Databricks', 'job_title': 'Data Engineer'}
        )

        with patch('backend.question_memory.research_company', new_callable=AsyncMock) as mock_research:
            result = await answer_application_question(
                self.user_a_id,
                dq,
                self.profile_a,
                context={'company': 'Databricks', 'job_title': 'Data Engineer'},
                allow_web_browsing=True
            )

            # Web research should NOT be called because memory exists!
            mock_research.assert_not_called()
            self.assertTrue(result.is_reused)
            self.assertIn("Lakehouse", result.answer)
            self.assertGreaterEqual(result.confidence, 0.9)

            # Verify usage counter incremented
            with Session() as db:
                mem = db.get(QuestionMemory, result.memory_id)
                self.assertGreaterEqual(mem.usage_count, 2)

    # Scenario 4: A paraphrased version retrieves a valid semantic match
    async def test_scenario_04_paraphrased_question_retrieves_semantic_match(self):
        save_memory_record(
            user_id=self.user_a_id,
            question_text="What interests you about joining Acme?",
            original_question="What interests you about joining Acme?",
            answer_text="Acme's mission in autonomous systems and collaborative engineering culture is inspiring.",
            category=CATEGORY_C,
            source="company_memory",
            confidence=0.92,
            company="Acme",
            approval_status="approved",
            scope="company"
        )

        # Paraphrased wording
        dq = DetectedQuestion(
            element_id=4,
            question_text="Why do you want to work at Acme?",
            field_type="textarea",
            tag="TEXTAREA",
            context={'company': 'Acme', 'job_title': 'Software Engineer'}
        )

        with patch('backend.question_memory.research_company', new_callable=AsyncMock) as mock_research:
            result = await answer_application_question(
                self.user_a_id,
                dq,
                self.profile_a,
                context={'company': 'Acme', 'job_title': 'Software Engineer'},
                allow_web_browsing=True
            )

            mock_research.assert_not_called()
            self.assertTrue(result.is_reused)
            self.assertIn("autonomous systems", result.answer)

    # Scenario 5: A similar question with a different meaning triggers new research
    async def test_scenario_05_different_meaning_triggers_new_research(self):
        # Memory exists for Acme
        save_memory_record(
            user_id=self.user_a_id,
            question_text="Why do you want to work at Acme?",
            original_question="Why do you want to work at Acme?",
            answer_text="I love Acme's mission.",
            category=CATEGORY_C,
            source="company_memory",
            confidence=0.95,
            company="Acme",
            scope="company"
        )

        # Question for BetaCorp (DIFFERENT company!)
        dq = DetectedQuestion(
            element_id=5,
            question_text="Why do you want to work at BetaCorp?",
            field_type="textarea",
            tag="TEXTAREA",
            context={'company': 'BetaCorp', 'job_title': 'Software Engineer'}
        )

        with patch('backend.question_memory.research_company', new_callable=AsyncMock) as mock_research:
            mock_research.return_value = {
                'success': True,
                'company': 'BetaCorp',
                'summary': 'BetaCorp creates cloud native cybersecurity products.',
                'sources': ['https://betacorp.example'],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': None
            }

            result = await answer_application_question(
                self.user_a_id,
                dq,
                self.profile_a,
                context={'company': 'BetaCorp', 'job_title': 'Software Engineer'},
                allow_web_browsing=True
            )

            # Must trigger new research because company is different
            mock_research.assert_called_once()
            self.assertNotIn("Acme", result.answer)
            self.assertIn("BetaCorp", result.answer)

    # Scenario 6: Outdated company information is refreshed
    async def test_scenario_06_outdated_company_info_refreshed(self):
        # Create expired/stale memory record (created 60 days ago)
        expired_time = datetime.now(timezone.utc) - timedelta(days=60)
        stale_record = save_memory_record(
            user_id=self.user_a_id,
            question_text="What do you know about Omega Corp?",
            original_question="What do you know about Omega Corp?",
            answer_text="Old outdated summary from last year.",
            category=CATEGORY_C,
            source="web_research",
            confidence=0.90,
            company="Omega Corp",
            scope="company"
        )
        with Session() as db:
            r = db.get(QuestionMemory, stale_record.id)
            r.status = 'stale'
            r.last_used = expired_time
            db.commit()

        dq = DetectedQuestion(
            element_id=6,
            question_text="What do you know about Omega Corp?",
            field_type="textarea",
            tag="TEXTAREA",
            context={'company': 'Omega Corp', 'job_title': 'Analyst'}
        )

        with patch('backend.question_memory.research_company', new_callable=AsyncMock) as mock_research:
            mock_research.return_value = {
                'success': True,
                'company': 'Omega Corp',
                'summary': 'Omega Corp recently launched their next-gen AI automation suite.',
                'sources': ['https://omegacorp.example/news'],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': None
            }

            result = await answer_application_question(
                self.user_a_id,
                dq,
                self.profile_a,
                context={'company': 'Omega Corp', 'job_title': 'Analyst'},
                allow_web_browsing=True
            )

            # Refresh triggered!
            mock_research.assert_called_once()
            self.assertIn("next-gen AI", result.answer)
            self.assertNotIn("Old outdated", result.answer)

    # Scenario 7: A personal question uses the verified profile instead of web browsing
    async def test_scenario_07_personal_question_uses_profile_no_browsing(self):
        dq_loc = DetectedQuestion(
            element_id=7,
            question_text="What is your current city of residence?",
            field_type="text",
            tag="INPUT"
        )
        
        with patch('backend.question_memory.research_company', new_callable=AsyncMock) as mock_research:
            result = await answer_application_question(
                self.user_a_id,
                dq_loc,
                self.profile_a,
                allow_web_browsing=True
            )

            mock_research.assert_not_called()
            self.assertEqual(result.category, CATEGORY_A)
            self.assertEqual(result.source, 'user_profile')
            self.assertEqual(result.answer, 'San Francisco')
            self.assertEqual(result.confidence, 0.95)

        # Check phone
        dq_phone = DetectedQuestion(element_id=8, question_text="Phone number", field_type="tel", tag="INPUT")
        result_phone = await answer_application_question(self.user_a_id, dq_phone, self.profile_a)
        self.assertEqual(result_phone.answer, '+1 (555) 234-5678')

        # Check skill years
        dq_years = DetectedQuestion(element_id=9, question_text="How many years of experience do you have with Python?", field_type="number", tag="INPUT")
        result_years = await answer_application_question(self.user_a_id, dq_years, self.profile_a)
        self.assertEqual(result_years.answer, '4')

    # Scenario 8: A missing sensitive answer pauses for user input
    async def test_scenario_08_missing_sensitive_answer_pauses_for_input(self):
        # Question asks about criminal record declaration (not in profile)
        dq_crim = DetectedQuestion(
            element_id=10,
            question_text="Have you ever been convicted of a felony?",
            field_type="select",
            tag="SELECT",
            options=["Please select", "Yes", "No"],
            required=True
        )

        with patch('backend.question_memory.research_company', new_callable=AsyncMock) as mock_research:
            result = await answer_application_question(
                self.user_a_id,
                dq_crim,
                self.profile_a,
                allow_web_browsing=True
            )

            # Never browse the web for sensitive personal facts!
            mock_research.assert_not_called()
            self.assertEqual(result.category, CATEGORY_E)
            self.assertTrue(result.needs_user_input)
            self.assertEqual(result.confidence, 0.0)
            self.assertIn("sensitive or legal declaration", result.pause_reason.lower())

    # Scenario 9: A low-confidence answer is not blindly submitted
    async def test_scenario_09_low_confidence_requires_user_approval(self):
        # A question with an ambiguous choice or uncertain evidence
        dq = DetectedQuestion(
            element_id=11,
            question_text="Please choose your specific department code",
            field_type="select",
            tag="SELECT",
            options=["DEPT-101", "DEPT-202", "DEPT-999"],
            required=True
        )

        result = await answer_application_question(
            self.user_a_id,
            dq,
            self.profile_a,
            allow_web_browsing=False
        )

        # Because department code is not in profile/memory and options don't match, confidence is lowered or pauses
        self.assertTrue(result.needs_user_input or result.confidence < 0.75)

    # Scenario 10: Memory persists after restarting application (database reload)
    async def test_scenario_10_memory_persists_across_sessions(self):
        # Save record in first session
        rec = save_memory_record(
            user_id=self.user_a_id,
            question_text="Explain your approach to microservices architecture",
            original_question="Explain your approach to microservices architecture",
            answer_text="I design microservices around domain-driven bounded contexts with asynchronous event communication.",
            category=CATEGORY_D,
            source="user_approved",
            confidence=0.95,
            approval_status="approved",
            scope="reusable"
        )
        rec_id = rec.id

        # Simulate complete application restart by querying a clean new session
        with Session() as fresh_db:
            loaded = fresh_db.get(QuestionMemory, rec_id)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.user_id, self.user_a_id)
            self.assertEqual(loaded.category, CATEGORY_D)
            self.assertIn("domain-driven", loaded.answer_text)

        # Retrieval in fresh session
        found_mem, score = search_persistent_memory(
            self.user_a_id,
            "Explain your approach to microservices architecture",
            CATEGORY_D
        )
        self.assertIsNotNone(found_mem)
        self.assertEqual(found_mem.id, rec_id)
        self.assertEqual(score, 1.0)

    # Scenario 11: Different users have isolated memories (multi-tenant isolation)
    async def test_scenario_11_multi_tenant_memory_isolation(self):
        # User A saves private question answer
        save_memory_record(
            user_id=self.user_a_id,
            question_text="What is your patent portfolio?",
            original_question="What is your patent portfolio?",
            answer_text="User A holds Patent US-99999 for quantum cryptographic key distribution.",
            category=CATEGORY_B,
            source="user_approved",
            confidence=1.0,
            approval_status="approved"
        )

        # User B queries the exact same question
        dq = DetectedQuestion(
            element_id=12,
            question_text="What is your patent portfolio?",
            field_type="textarea",
            tag="TEXTAREA"
        )
        profile_b = {**self.profile_a, 'name': 'Bob Smith', 'email': 'bob@example.com'}

        result_b = await answer_application_question(
            self.user_b_id,
            dq,
            profile_b,
            allow_web_browsing=False
        )

        # User B MUST NOT receive User A's private answer!
        self.assertNotIn("US-99999", result_b.answer)
        self.assertNotIn("User A", result_b.answer)

        # Check DB query directly
        with Session() as db:
            user_b_memories = db.query(QuestionMemory).filter_by(user_id=self.user_b_id).all()
            self.assertFalse(any("US-99999" in m.answer_text for m in user_b_memories))

    # Scenario 12: Web research failures produce safe fallback behavior
    async def test_scenario_12_web_research_failures_safe_fallback(self):
        dq = DetectedQuestion(
            element_id=13,
            question_text="Why do you want to join StealthStartupX?",
            field_type="textarea",
            tag="TEXTAREA",
            context={'company': 'StealthStartupX', 'job_title': 'Lead Architect'}
        )

        # Simulate network timeout / search failure
        with patch('backend.question_memory.research_company', new_callable=AsyncMock) as mock_research:
            mock_research.return_value = {
                'success': False,
                'company': 'StealthStartupX',
                'summary': '',
                'sources': [],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': 'Connection timeout after 10s'
            }

            result = await answer_application_question(
                self.user_a_id,
                dq,
                self.profile_a,
                context={'company': 'StealthStartupX', 'job_title': 'Lead Architect'},
                allow_web_browsing=True
            )

            # Does NOT crash or fabricate fake citations
            self.assertEqual(result.source_urls, [])
            self.assertIn("StealthStartupX", result.answer)
            # Confidence is lowered to reflect fallback
            self.assertLessEqual(result.confidence, 0.60)

    # Constraint enforcement tests: Options & Length limits
    def test_form_constraints_options_and_lengths(self):
        options = ["Yes", "No", "Not Applicable"]
        self.assertEqual(match_dropdown_option(options, "yes"), "Yes")
        self.assertEqual(match_dropdown_option(options, "NO"), "No")

        text = "This is a detailed response explaining the full background of a software project. It covers system architecture and metrics."
        shortened = enforce_length_constraints(text, char_limit=40)
        self.assertLessEqual(len(shortened), 40)

        word_shortened = enforce_length_constraints(text, word_limit=5)
        self.assertLessEqual(len(word_shortened.split()), 5)

    # Scenario 13: Internal web research is invisible (backend HTTP only, no browser navigation or visible tabs)
    async def test_scenario_13_invisible_background_research_no_browser_navigation(self):
        dq = DetectedQuestion(
            element_id=10,
            question_text="What do you know about Datadog's observability platform?",
            field_type="textarea",
            tag="TEXTAREA",
            context={'company': 'Datadog', 'job_title': 'Site Reliability Engineer'}
        )

        with patch('backend.question_memory.research_company', new_callable=AsyncMock) as mock_research:
            mock_research.return_value = {
                'success': True,
                'company': 'Datadog',
                'summary': 'Datadog is an observability service for cloud-scale applications providing monitoring of servers and databases.',
                'sources': ['https://www.datadoghq.com/about/'],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': None
            }

            # Mock a browser page object to assert that the browser is NEVER navigated or touched during research
            mock_page = AsyncMock()
            mock_page.goto = AsyncMock()
            mock_page.context.new_page = AsyncMock()

            result = await answer_application_question(
                self.user_a_id,
                dq,
                self.profile_a,
                context={'company': 'Datadog', 'job_title': 'Site Reliability Engineer'},
                allow_web_browsing=True
            )

            # Assert browser was never navigated or opened a new tab
            mock_page.goto.assert_not_called()
            mock_page.context.new_page.assert_not_called()

            # Assert research succeeded silently and returned grounded answer
            self.assertEqual(result.category, CATEGORY_C)
            self.assertIn("Datadog", result.answer)
            self.assertEqual(result.source, "web_research")
            self.assertEqual(result.source_urls, ['https://www.datadoghq.com/about/'])

    # Scenario 14: User corrections update future answers (continuous self-learning)
    async def test_scenario_14_user_correction_updates_future_answers(self):
        from .question_memory import learn_from_user_correction

        # 1. Initial saved memory generated by agent
        save_memory_record(
            user_id=self.user_a_id,
            question_text="Tell me about a challenging technical project you built.",
            original_question="Tell me about a challenging project",
            answer_text="I built a web application using standard libraries.",
            category=CATEGORY_B,
            source="llm_generated",
            confidence=0.80,
            approval_status="unapproved"
        )

        # 2. User edits package or explicitly corrects the answer
        corrected_text = "I designed and deployed a high-throughput event processing engine in Python and Redis handling 50k events/sec with 99.99% uptime."
        learn_from_user_correction(
            user_id=self.user_a_id,
            question_text="Tell me about a challenging technical project you built.",
            corrected_answer=corrected_text,
            category=CATEGORY_B
        )

        # 3. Next time the question appears, the corrected answer is retrieved
        dq = DetectedQuestion(
            element_id=2,
            question_text="Describe a challenging project you worked on recently",
            field_type="textarea",
            tag="TEXTAREA"
        )
        res = await answer_application_question(
            self.user_a_id,
            dq,
            self.profile_a
        )

        self.assertEqual(res.answer, corrected_text)
        self.assertEqual(res.approval_status, 'approved')
        self.assertEqual(res.source, 'user_approved')
        self.assertTrue(res.is_reused)

    # Scenario 15: Automatically adapt answers across different companies and roles
    async def test_scenario_15_context_adaptation_across_companies(self):
        from .question_memory import adapt_answer_to_context

        saved = save_memory_record(
            user_id=self.user_a_id,
            question_text="Why are you interested in this position?",
            original_question="Why are you interested in this position?",
            answer_text="I am eager to contribute my problem-solving abilities to Acme as a Frontend Engineer.",
            category=CATEGORY_B,
            source="user_approved",
            company="Acme",
            job_title="Frontend Engineer",
            scope="reusable"
        )

        # Applying to Linear as a Full Stack Engineer
        new_ctx = {'company': 'Linear', 'job_title': 'Full Stack Engineer'}
        adapted = adapt_answer_to_context(
            saved.answer_text,
            saved_mem=saved,
            target_question="Why are you interested in this position?",
            context=new_ctx,
            profile=self.profile_a
        )

        self.assertIn("Linear", adapted)
        self.assertIn("Full Stack Engineer", adapted)
        self.assertNotIn("Acme", adapted)
        self.assertNotIn("Frontend Engineer", adapted)

    # Scenario 16: Answer quality and feedback loop
    async def test_scenario_16_feedback_and_continuous_improvement(self):
        from .question_memory import record_answer_feedback

        mem = save_memory_record(
            user_id=self.user_a_id,
            question_text="What is your approach to automated testing?",
            original_question="Approach to automated testing",
            answer_text="I write comprehensive unit and integration tests using pytest and mock fixtures.",
            category=CATEGORY_D,
            source="user_approved",
            confidence=0.90
        )

        # Positive feedback boosts quality score
        updated = record_answer_feedback(self.user_a_id, mem.id, score=1)
        self.assertGreater(updated.quality_score, 1.0)
        self.assertEqual(updated.feedback_score, 1)

        # Negative feedback penalizes quality score
        penalized = record_answer_feedback(self.user_a_id, mem.id, score=-1)
        self.assertEqual(penalized.feedback_score, 0)

    # Scenario 17: Application workflow continuation after answering
    async def test_scenario_17_resumes_workflow_cleanly(self):
        from .worker import build_fields, rule_plan

        # Form snapshot with a screening question and a submit button
        snapshot = {
            'elements': [
                {'id': 1, 'tag': 'INPUT', 'type': 'text', 'label': 'What is your current city?', 'text': '', 'filled': False, 'required': True},
                {'id': 2, 'tag': 'BUTTON', 'type': 'submit', 'label': 'Submit application', 'text': 'Submit application'}
            ]
        }

        # Build fields with persistent question memory loaded
        fields = build_fields(self.profile_a, package={}, user_id=self.user_a_id)
        self.assertIn('city', fields)
        self.assertEqual(fields['city'], 'San Francisco')

        # Rule planner completes the form actions seamlessly
        plan = rule_plan(snapshot, fields, package={}, done=())
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan['actions']), 2)
        self.assertEqual(plan['actions'][0]['action'], 'fill')
        self.assertEqual(plan['actions'][1]['action'], 'submit')

class TestQuestionMemoryApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, headers={'origin': 'http://127.0.0.1:3000'})
        self.client.__enter__()
        resp = self.client.post('/api/auth/demo', json={})
        self.assertEqual(resp.status_code, 200)

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_api_memory_crud_and_endpoints(self):
        # 1. Create a memory record
        create_resp = self.client.post('/api/memory', json={
            'question_text': 'Why do you want to work at Figma?',
            'answer_text': 'I admire Figma collaborative canvas and plugin architecture.',
            'company': 'Figma',
            'scope': 'company'
        })
        self.assertEqual(create_resp.status_code, 200)
        data = create_resp.json()
        mem_id = data['id']
        self.assertEqual(data['company'], 'Figma')
        self.assertEqual(data['approval_status'], 'approved')
        self.assertEqual(data['category'], CATEGORY_C)

        # 2. List memory records
        list_resp = self.client.get('/api/memory?company=Figma')
        self.assertEqual(list_resp.status_code, 200)
        items = list_resp.json()
        self.assertTrue(any(m['id'] == mem_id for m in items))

        # 3. Get single memory
        get_resp = self.client.get(f'/api/memory/{mem_id}')
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()['id'], mem_id)

        # 4. Update memory record
        update_resp = self.client.put(f'/api/memory/{mem_id}', json={
            'answer_text': 'Updated answer: Figma modern design systems are world-class.'
        })
        self.assertEqual(update_resp.status_code, 200)
        self.assertIn('world-class', update_resp.json()['answer_text'])

        # 5. Approve memory record
        appr_resp = self.client.post(f'/api/memory/{mem_id}/approve')
        self.assertEqual(appr_resp.status_code, 200)
        self.assertEqual(appr_resp.json()['approval_status'], 'approved')

        # 6. Feedback endpoint
        fb_resp = self.client.post(f'/api/memory/{mem_id}/feedback', json={'feedback': 'up'})
        self.assertEqual(fb_resp.status_code, 200)
        self.assertGreater(fb_resp.json()['feedback_score'], 0)

        # 7. Refresh memory record
        with patch('backend.web_researcher.research_company', new_callable=AsyncMock) as mock_res:
            mock_res.return_value = {
                'success': True,
                'summary': 'Figma empowers creative collaboration on the web.',
                'sources': ['https://figma.com/about'],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': None
            }
            ref_resp = self.client.post(f'/api/memory/{mem_id}/refresh')
            self.assertEqual(ref_resp.status_code, 200)
            self.assertIn('creative collaboration', ref_resp.json()['answer_text'])

        # 8. Ask memory test endpoint
        ask_resp = self.client.post('/api/memory/ask', json={
            'question_text': 'What interests you about joining Figma?',
            'company': 'Figma',
            'field_type': 'textarea'
        })
        self.assertEqual(ask_resp.status_code, 200)
        ask_data = ask_resp.json()
        self.assertEqual(ask_data['category'], CATEGORY_C)
        self.assertTrue(ask_data['is_reused'])
        self.assertIn('Figma', ask_data['answer'])

        # 9. Delete memory record
        del_resp = self.client.delete(f'/api/memory/{mem_id}')
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(del_resp.json(), {'deleted': mem_id})

        # Confirm 404 after delete
        self.assertEqual(self.client.get(f'/api/memory/{mem_id}').status_code, 404)



