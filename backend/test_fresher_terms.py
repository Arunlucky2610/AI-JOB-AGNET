import os, tempfile, unittest
from pathlib import Path
os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(tempfile.gettempdir())/'orbit-test-fresher-unused.db').replace('\\','/'))
from .career_ops import enforce_evidence_constraints, fresher_accepts
from .worker import build_fields

def row(requirement,match='unknown'):
    return {'requirement':requirement,'importance':'critical','tier':'stated','jd_evidence':'x','match':match}

class FresherTermsTests(unittest.TestCase):
    def test_job_terms_are_accepted_but_not_skills_or_fees(self):
        for text in ['Available for 6 months onsite internship in Noida','OK with 2 months unpaid stipend, then 5-10k based on performance','Willing to relocate to Pune','Comfortable with night shifts']:
            self.assertTrue(fresher_accepts(text),text)
        for text in ['Proficiency in PyTorch','2+ years of Python experience','Pay a registration fee of 2000','Refundable security deposit required']:
            self.assertFalse(fresher_accepts(text),text)
    def test_fresher_is_not_blocked_by_job_terms(self):
        match={'blockers':[],'unknown':[],'evaluation':{'B':[row('Available for 6 months onsite internship in Noida'),row('OK with 2 months unpaid stipend')]}}
        enforce_evidence_constraints(match,fresher=True)
        self.assertEqual(match['unknown'],[]);self.assertEqual(len(match['review_notes']),2)
    def test_assessment_open_questions_about_terms_are_accepted_too(self):
        match={'blockers':[],'unknown':['Available for 6 months onsite internship in Noida','OK with 2 months unpaid stipend','Comfortable with mentoring students'],'eligible':False,'matched':False,'evaluation':{'B':[]}}
        enforce_evidence_constraints(match,fresher=True)
        self.assertEqual(match['unknown'],[]);self.assertTrue(match['matched'])
        match={'blockers':[],'unknown':['Pay a refundable security deposit of 5000'],'eligible':False,'matched':False}
        enforce_evidence_constraints(match,fresher=True);self.assertFalse(match['matched'])
    def test_skill_gaps_still_block_a_fresher_and_terms_still_block_others(self):
        match={'blockers':[],'unknown':[],'evaluation':{'B':[row('Proficiency in PyTorch','missing')]}}
        enforce_evidence_constraints(match,fresher=True);self.assertTrue(match['blockers']);self.assertFalse(match['matched'])
        match={'blockers':[],'unknown':[],'evaluation':{'B':[row('Available for 6 months onsite internship in Noida')]}}
        enforce_evidence_constraints(match);self.assertTrue(match['unknown'])
    def test_form_answer_only_for_freshers(self):
        base={'name':'A B','phone':'+91 99','locations':'Hyderabad'};package={'cover_letter':'c'}
        self.assertEqual(build_fields({**base,'career_level':'Fresher'},package).get('fresher_accepts_terms'),'Yes')
        self.assertNotIn('fresher_accepts_terms',build_fields({**base,'career_level':'Experienced'},package))

if __name__=='__main__':unittest.main()
