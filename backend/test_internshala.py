import asyncio
import unittest
from . import internshala, services
from .test_linkedin import PROFILE

class MockLocator:
    def __init__(self, count_val=0):
        self._count = count_val

    async def count(self):
        return self._count

    async def is_visible(self):
        return True

    async def scroll_into_view_if_needed(self):
        pass

    async def input_value(self):
        return ''

    async def is_checked(self):
        return False

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    async def wait_for(self, **kwargs):
        pass

    def filter(self, **kwargs):
        return self

    async def click(self, **kwargs):
        pass

class MockPage:
    def __init__(self, url='', eval_result=None, locators=None):
        self.url = url
        self._eval_result = eval_result
        self._locators = locators or {}

    async def goto(self, url, **kwargs):
        self.url = url

    async def wait_for_timeout(self, ms):
        pass

    async def inner_text(self, sel):
        return 'Mock page content for Internshala'

    async def evaluate(self, expr, *args):
        if callable(self._eval_result):
            return self._eval_result(expr)
        if isinstance(self._eval_result, dict):
            return self._eval_result
        if self._eval_result is not None:
            return self._eval_result
        return False

    def locator(self, sel):
        for k, v in self._locators.items():
            if k in sel:
                return MockLocator(v)
        return MockLocator(0)

    def get_by_text(self, text):
        return MockLocator(0)

class InternshalaUnitTests(unittest.TestCase):
    def test_domain_validation(self):
        self.assertTrue(internshala.is_internshala_domain('https://internshala.com/jobs'))
        self.assertTrue(internshala.is_internshala_domain('https://www.internshala.com/internships'))
        self.assertTrue(internshala.is_internshala_domain('https://sub.internshala.com/login'))
        self.assertFalse(internshala.is_internshala_domain('https://notinternshala.com'))
        self.assertFalse(internshala.is_internshala_domain('https://internshala.fake.com'))

    def test_sign_in_url(self):
        self.assertEqual(internshala.sign_in_url(), 'https://internshala.com/login/user')

    def test_canonical_url_extraction(self):
        # Job canonical
        job_url_with_params = 'https://internshala.com/job/detail/python-developer-12345?utm_source=search&search_id=987'
        self.assertEqual(internshala.canonical(job_url_with_params), 'https://internshala.com/job/detail/12345')

        # Internship canonical
        intern_url_with_params = 'https://internshala.com/internship/detail/web-development-internship-in-hyderabad-67890?src=hp'
        self.assertEqual(internshala.canonical(intern_url_with_params), 'https://internshala.com/internship/detail/67890')

        # Fallback when no ID pattern matches
        fallback_url = 'https://internshala.com/jobs/freshers?page=2'
        self.assertEqual(internshala.canonical(fallback_url), 'https://internshala.com/jobs/freshers')

    def test_platform_hosts_allow_internshala(self):
        ok = services.allowed_application_url
        self.assertTrue(ok('https://internshala.com/job/detail/12345', 'Internshala'))
        self.assertTrue(ok('https://internshala.com/internship/detail/67890', 'Internshala'))
        self.assertFalse(ok('https://internshala.com/job/detail/12345', 'LinkedIn'))
        self.assertFalse(ok('https://internshala.com/job/detail/12345', 'Indeed'))
        self.assertFalse(ok('https://internshala.com/job/detail/12345', 'Naukri'))

    def test_search_urls_for_freshers(self):
        profile = {
            **PROFILE,
            'roles': 'Software Development',
            'locations': 'Hyderabad',
            'career_level': 'fresher'
        }
        urls = internshala.search_urls(profile)
        self.assertEqual(len(urls), 1)
        self.assertEqual(urls[0], 'https://internshala.com/jobs/software-development-jobs-in-hyderabad/')

    def test_search_urls_for_interns(self):
        profile = {
            **PROFILE,
            'roles': 'Web Development',
            'locations': 'Bangalore',
            'career_level': 'intern'
        }
        urls = internshala.search_urls(profile)
        self.assertEqual(len(urls), 1)
        self.assertEqual(urls[0], 'https://internshala.com/internships/web-development-internships-in-bangalore/')

    def test_search_urls_work_from_home(self):
        profile = {
            **PROFILE,
            'roles': 'Python Django',
            'locations': 'Work From Home',
            'career_level': 'intern'
        }
        urls = internshala.search_urls(profile)
        self.assertEqual(len(urls), 1)
        self.assertEqual(urls[0], 'https://internshala.com/internships/work-from-home-python-django-internships/')

    def test_search_urls_country_only_and_any_location(self):
        profile = {
            **PROFILE,
            'roles': 'Frontend Development',
            'locations': 'Hyderabad',
            'career_level': 'fresher'
        }
        country_urls = internshala.search_urls(profile, country_only=True)
        self.assertEqual(country_urls[0], 'https://internshala.com/jobs/frontend-development-jobs/')

        any_urls = internshala.search_urls(profile, any_location=True)
        self.assertEqual(any_urls[0], 'https://internshala.com/jobs/frontend-development-jobs/')

    def test_search_urls_roles_capped_at_five(self):
        profile = {
            **PROFILE,
            'roles': 'Role1, Role2, Role3, Role4, Role5, Role6, Role7'
        }
        urls = internshala.search_urls(profile)
        self.assertEqual(len(urls), 5)

    def test_is_signed_in_simulation(self):
        # 1. On /login URL -> False
        p_login = MockPage(url='https://internshala.com/login/user')
        self.assertFalse(asyncio.run(internshala.is_signed_in(p_login)))

        # 2. On /registration URL -> False
        p_reg = MockPage(url='https://internshala.com/registration/student')
        self.assertFalse(asyncio.run(internshala.is_signed_in(p_reg)))

        # 3. DOM has profile dropdown / user menu -> True
        p_profile = MockPage(
            url='https://internshala.com/jobs',
            locators={'#user_menu': 1, '.profile_icon': 1}
        )
        self.assertTrue(asyncio.run(internshala.is_signed_in(p_profile)))

        # 4. DOM has login modal trigger -> False
        p_logged_out = MockPage(
            url='https://internshala.com/jobs',
            locators={'#login-modal': 1, 'a[href="/login/user"]': 1}
        )
        self.assertFalse(asyncio.run(internshala.is_signed_in(p_logged_out)))

    def test_apply_state_direct_vs_external_vs_closed_vs_applied(self):
        # Direct easy apply
        p_easy = MockPage(eval_result={'closed': False, 'applied': False, 'external': False, 'easy': True})
        self.assertEqual(asyncio.run(internshala.apply_state(p_easy)), 'easy')

        # External apply
        p_ext = MockPage(eval_result={'closed': False, 'applied': False, 'external': True, 'easy': False})
        self.assertEqual(asyncio.run(internshala.apply_state(p_ext)), 'external')

        # Already applied
        p_app = MockPage(eval_result={'closed': False, 'applied': True, 'external': False, 'easy': False})
        self.assertEqual(asyncio.run(internshala.apply_state(p_app)), 'applied')

        # Closed
        p_closed = MockPage(eval_result={'closed': True, 'applied': False, 'external': False, 'easy': False})
        self.assertEqual(asyncio.run(internshala.apply_state(p_closed)), 'closed')

        # Unknown
        p_unk = MockPage(eval_result={'closed': False, 'applied': False, 'external': False, 'easy': False})
        self.assertEqual(asyncio.run(internshala.apply_state(p_unk)), 'unknown')

    def test_login_with_credentials_flow(self):
        # Successful login flow simulation
        class AutoLoginPage(MockPage):
            def __init__(self):
                super().__init__(url='https://internshala.com/login/user', locators={'#email': 1, '#password': 1, '#login_submit': 1})
                self._logged = False
            async def evaluate(self, expr, *args):
                return False
            def locator(self, sel):
                if '#user_menu' in sel:
                    return MockLocator(1 if self._logged else 0)
                parent = self
                class FormLocator(MockLocator):
                    async def click(self, **kwargs):
                        if '#login_submit' in sel:
                            parent._logged = True
                            parent.url = 'https://internshala.com/student/dashboard'
                    async def type(self, text, **kwargs):
                        pass
                    async def fill(self, text, **kwargs):
                        pass
                return FormLocator(1)

        p = AutoLoginPage()
        res = asyncio.run(internshala.login_with_credentials(p, 'test@example.com', 'secretpass123'))
        self.assertTrue(res)

    def test_scroll_and_click_proceed(self):
        p = MockPage(
            url='https://internshala.com/job/detail/12345',
            locators={'#proceed_to_application': 1}
        )
        res = asyncio.run(internshala.scroll_and_click_proceed(p))
        self.assertTrue(res)

    def test_handle_internshala_application_full_flow(self):
        class ApplyFlowPage(MockPage):
            def __init__(self):
                super().__init__(
                    url='https://internshala.com/job/detail/12345',
                    locators={
                        '#easy_apply_button': 1,
                        '#proceed_to_application': 1,
                        '#submit': 1,
                    }
                )
                self._submitted = False

            async def inner_text(self, sel):
                if self._submitted:
                    return 'Your application has been submitted successfully'
                return 'Mock Internshala listing'

            def locator(self, sel):
                parent = self
                class Clickable(MockLocator):
                    async def click(self, **kwargs):
                        if '#submit' in sel:
                            parent._submitted = True
                            parent.url = 'https://internshala.com/student/applications'
                    async def fill(self, text, **kwargs):
                        pass
                return Clickable(1)

        p = ApplyFlowPage()
        res = asyncio.run(internshala.handle_internshala_application(
            p,
            'user1',
            PROFILE,
            {'title': 'Python Developer', 'company': 'Tech Corp', 'id': 'j1'},
            {'cover_letter': 'Custom cover letter', 'resume': 'Resume content'}
        ))
        self.assertEqual(res, 'submitted')

if __name__ == '__main__':
    unittest.main()
