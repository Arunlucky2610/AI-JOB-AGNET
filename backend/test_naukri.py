import unittest
from . import naukri, services
from .test_linkedin import PROFILE

class NaukriUrlTests(unittest.TestCase):
    def test_search_urls_follow_the_profile(self):
        urls = naukri.search_urls(PROFILE)
        self.assertEqual(len(urls), 1)
        for expected in ['ai-engineer-jobs', 'k=AI+Engineer', 'experience=0']:
            self.assertIn(expected, urls[0])

    def test_country_only_search_drops_the_city(self):
        urls = naukri.search_urls(PROFILE, country_only=True)
        self.assertNotIn('-in-', urls[0])
        self.assertNotIn('&l=', urls[0])

    def test_any_location_drops_the_filter_entirely(self):
        urls = naukri.search_urls(PROFILE, any_location=True)
        self.assertNotIn('-in-', urls[0])
        self.assertNotIn('&l=', urls[0])

    def test_roles_are_capped_at_five(self):
        self.assertEqual(len(naukri.search_urls({**PROFILE, 'roles': 'a,b,c,d,e,f,g'})), 5)

    def test_one_canonical_url_per_vacancy(self):
        for url in [
            'https://www.naukri.com/job-listings-python-developer-123456789012',
            'https://www.naukri.com/job-listings-ai-engineer-company-hyd-123456789012?src=search&sid=123',
            'https://www.naukri.com/job-listings?id=123456789012'
        ]:
            self.assertEqual(naukri.canonical(url), 'https://www.naukri.com/job-listings-123456789012')

    def test_platform_hosts_allow_naukri(self):
        ok = services.allowed_application_url
        self.assertTrue(ok('https://www.naukri.com/job-listings-123456789012', 'Naukri'))
        self.assertTrue(ok('https://login.naukri.com/nlogin/login', 'Naukri'))
        self.assertFalse(ok('https://www.naukri.com/job-listings-123456789012', 'LinkedIn'))
        self.assertFalse(ok('https://www.naukri.com/job-listings-123456789012', 'Indeed'))

    def test_sign_in_url(self):
        login_url = naukri.sign_in_url(PROFILE)
        self.assertEqual(login_url, 'https://www.naukri.com/nlogin/login')

    def test_experience_param_mapping(self):
        self.assertEqual(naukri.experience_param({'experience': 0}), '0')
        self.assertEqual(naukri.experience_param({'experience': 1}), '0')
        self.assertEqual(naukri.experience_param({'experience': 2, 'career_level': 'experienced'}), '0-2')
        self.assertEqual(naukri.experience_param({'experience': 4, 'career_level': 'experienced'}), '3-5')
        self.assertEqual(naukri.experience_param({'experience': 8, 'career_level': 'experienced'}), '8')

    def test_chatbot_helpers_exist(self):
        self.assertTrue(callable(naukri.is_chatbot_open))
        self.assertTrue(callable(naukri.handle_naukri_chatbot))

    def test_login_with_credentials_flow(self):
        import asyncio
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
                self.url = 'https://www.naukri.com/nlogin/login'
                self._signed_in = False
            async def goto(self, url, **kwargs):
                self.url = url
            async def wait_for_timeout(self, ms): pass
            async def evaluate(self, expr, *args):
                return False
            def locator(self, sel):
                if '.user-name' in sel or '.nI-gNb-drawer' in sel:
                    return MockLoc(1 if self._signed_in else 0)
                if '.loginButton' in sel:
                    parent = self
                    class SubmitLoc(MockLoc):
                        async def click(self, **kwargs):
                            parent._signed_in = True
                            parent.url = 'https://www.naukri.com/mnjuser/homepage'
                    return SubmitLoc(1)
                return MockLoc(1)

        p = MockPage()
        res = asyncio.run(naukri.login_with_credentials(p, 'user@example.com', 'mypassword'))
        self.assertTrue(res)

if __name__ == '__main__':
    unittest.main()
