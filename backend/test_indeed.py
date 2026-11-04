import unittest
from . import indeed, services
from .test_linkedin import PROFILE

class IndeedUrlTests(unittest.TestCase):
    def test_search_urls_follow_the_profile(self):
        urls = indeed.search_urls(PROFILE)
        self.assertEqual(len(urls), 1)
        for expected in ['q=AI+Engineer', 'l=Hyderabad%2C+India', 'sort=date', 'fromage=7']:
            self.assertIn(expected, urls[0])

    def test_country_only_search_drops_the_city(self):
        self.assertIn('l=India&', indeed.search_urls(PROFILE, country_only=True)[0])

    def test_any_location_drops_the_filter_entirely(self):
        self.assertNotIn('l=', indeed.search_urls(PROFILE, any_location=True)[0])

    def test_search_uses_the_profile_country_site(self):
        self.assertTrue(indeed.search_urls(PROFILE)[0].startswith('https://in.indeed.com/jobs?'))
        self.assertTrue(indeed.search_urls({**PROFILE, 'country': 'United States'})[0].startswith('https://www.indeed.com/jobs?'))
        self.assertEqual(indeed.canonical('https://in.indeed.com/rc/clk?jk=aaaa1111bbbb2222&x=1'), 'https://in.indeed.com/viewjob?jk=aaaa1111bbbb2222')

    def test_roles_are_capped_at_five(self):
        self.assertEqual(len(indeed.search_urls({**PROFILE, 'roles': 'a,b,c,d,e,f,g'})), 5)

    def test_one_canonical_url_per_vacancy(self):
        for url in ['https://www.indeed.com/viewjob?jk=aaaa1111bbbb2222', 'https://www.indeed.com/jobs?q=x&vjk=aaaa1111bbbb2222',
                    'https://www.indeed.com/rc/clk?jk=aaaa1111bbbb2222&bb=xyz&xkcb=abc']:
            self.assertEqual(indeed.canonical(url), 'https://www.indeed.com/viewjob?jk=aaaa1111bbbb2222')

    def test_platform_hosts_include_the_apply_subdomain(self):
        ok = services.allowed_application_url
        self.assertTrue(ok('https://www.indeed.com/viewjob?jk=aaaa1111bbbb2222', 'Indeed'))
        self.assertTrue(ok('https://smartapply.indeed.com/beta/indeedapply/x', 'Indeed'))
        self.assertFalse(ok('https://www.indeed.com/viewjob?jk=aaaa1111bbbb2222', 'LinkedIn'))

    def test_sign_in_url_contains_country_host(self):
        login_url = indeed.sign_in_url(PROFILE)
        self.assertTrue(login_url.startswith('https://secure.indeed.com/account/login?'))
        self.assertIn('continue=https%3A%2F%2Fin.indeed.com%2F', login_url)

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
                self.url = 'https://secure.indeed.com/account/login'
                self._signed_in = False
            async def goto(self, url, **kwargs):
                self.url = url
            async def wait_for_timeout(self, ms): pass
            async def evaluate(self, expr, *args):
                return False
            def locator(self, sel):
                if 'ProfileMenu' in sel or 'aria-label*="Profile"' in sel:
                    return MockLoc(1 if self._signed_in else 0)
                if 'button[type="submit"]' in sel or 'Sign in' in sel:
                    parent = self
                    class SubmitLoc(MockLoc):
                        async def click(self, **kwargs):
                            parent._signed_in = True
                            parent.url = 'https://in.indeed.com/'
                    return SubmitLoc(1)
                return MockLoc(1)

        p = MockPage()
        res = asyncio.run(indeed.login_with_credentials(p, 'user@example.com', 'mypassword', PROFILE))
        self.assertTrue(res)
