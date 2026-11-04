"""The free experience check: it must catch real 'too senior' postings and leave doubtful ones to the models."""
import unittest
from .prefilter import years_required, experience_skip_reason, posting_text

class YearsRequiredTests(unittest.TestCase):
    def test_postings_seen_in_real_runs_are_caught(self):
        for text,need in (('Requires 2+ years of professional software development experience.',2),
                          ('Minimum 2+ years of experience in Python and FastAPI',2),
                          ('Job explicitly requires 1+ years of iOS work experience',1),
                          ('You have at least 3 years of hands-on experience with React',3),
                          ('Experience: 2-4 years',2),
                          ('4 years of relevant experience in backend development',4),
                          ('Minimum 5 yrs experience',5)):
            self.assertEqual(years_required(text),need,text)
    def test_fresher_friendly_or_unclear_postings_are_left_alone(self):
        for text in ('Freshers welcome. Any graduate can apply.','0-1 years of experience','0 to 2 years experience',
                     'Experience: Fresher / 0-1 year','Strong communication skills and a Bachelor\'s degree.',
                     'You must be 18+ years of age.','', None):
            self.assertIsNone(experience_skip_reason(text,0),text)   # never skipped, whether it is unclear or asks for 0 years
        self.assertEqual(years_required('0-1 years of experience'),0)
    def test_company_boasting_and_optional_wishes_are_not_requirements(self):
        for text in ('We have 15+ years of experience delivering software to global clients.',
                     'Our team has over 10 years of experience in AI.',
                     'Founded in 2009 with 12 years of industry experience.',
                     '5+ years of experience preferred but not mandatory.',
                     'Experience with cloud is a plus (3+ years).'):
            self.assertIsNone(years_required(text),text)
    def test_the_lowest_stated_bar_wins(self):
        self.assertEqual(years_required('0-1 years experience in general.\n2+ years experience with Python.'),0)
        self.assertEqual(years_required('2+ years experience with Python.\n3+ years experience with AWS.'),2)
    def test_skip_reason_compares_with_the_candidate(self):
        self.assertIn('2+ years',experience_skip_reason('Requires 2+ years of experience.',0))
        self.assertIsNone(experience_skip_reason('Requires 2+ years of experience.',2))
        self.assertIsNone(experience_skip_reason('Requires 2+ years of experience.',5))
        self.assertIsNone(experience_skip_reason('Freshers can apply.',0))
        self.assertIn('1+',experience_skip_reason('1+ year of experience required'.replace('year ','years '),'0'))
    def test_only_the_vacancy_section_is_read(self):
        page='Similar jobs\nOther Co: 8+ years of experience\nAbout the job\nJunior role. Freshers welcome.\nAbout the company\nWe have 10 years of experience'
        self.assertIn('Freshers welcome',posting_text(page));self.assertNotIn('8+ years',posting_text(page))
        self.assertEqual(posting_text('No headings here, 2+ years experience'),'No headings here, 2+ years experience')

if __name__=='__main__':unittest.main()
