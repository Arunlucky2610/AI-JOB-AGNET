"""The agent's decision rules: goals, ranking, vacancy verification, grounded documents, retries and outcome evaluation."""
import asyncio, os, tempfile, unittest
from pathlib import Path

os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(tempfile.gettempdir())/'orbit-test-orch-unused.db').replace('\\','/'))
from fastapi import HTTPException
from . import orchestrator as o
from .domain import DEMO_PROFILE

FRESHER={**DEMO_PROFILE,'career_level':'Fresher','experience':0,'no_experience':True,'roles':'Data Analyst','country':'India'}
SENIOR={**DEMO_PROFILE,'career_level':'Experienced','experience':5,'no_experience':False}

class GoalTests(unittest.TestCase):
    def test_default_thresholds_follow_career_level(self):
        self.assertEqual(o.fit_threshold(FRESHER,{}),60);self.assertEqual(o.fit_threshold(SENIOR,{}),70)
    def test_a_configured_threshold_is_respected(self):
        self.assertEqual(o.fit_threshold(FRESHER,{'threshold':85}),85);self.assertEqual(o.fit_threshold(SENIOR,{'threshold':50}),50)
    def test_missing_goals_are_asked_not_assumed(self):
        self.assertEqual(len(o.blocking_questions({**FRESHER,'roles':'','country':''})),2);self.assertEqual(o.blocking_questions(FRESHER),[])
        self.assertTrue(any('sponsorship' in q for q in o.soft_questions({**FRESHER,'sponsorship':''})))
    def test_plan_keeps_the_candidates_own_goal_and_quota(self):
        plan=o.build_plan({**FRESHER,'excluded_companies':'Acme, Foo'},{'daily_limit':3},['q1'],started_today=1,waiting=1,spent=0.123456)
        self.assertEqual(plan['objective']['roles'],['Data Analyst']);self.assertEqual(plan['objective']['blacklist'],['Acme','Foo'])
        self.assertEqual((plan['quota']['slots'],plan['threshold'],plan['budget']['usd_spent']),(1,60,0.1235))
    def test_slots_never_go_negative(self):
        self.assertEqual(o.slots_left(3,3,2),0);self.assertEqual(o.slots_left(3,0,1),2)

class RankingTests(unittest.TestCase):
    JOBS=[{'canonical':'c','score':70,'global_score':4.0,'matched_skills':['a']},{'canonical':'a','score':90,'global_score':3.0,'matched_skills':[]},
          {'canonical':'b','score':90,'global_score':4.5,'matched_skills':['a','b']},{'canonical':'d','score':70,'global_score':4.0,'matched_skills':['a']}]
    def test_best_first_by_score_then_evidence(self):
        self.assertEqual([j['canonical'] for j in o.rank_jobs(self.JOBS)],['b','a','c','d'])
    def test_ranking_is_deterministic_whatever_the_input_order(self):
        self.assertEqual(o.rank_jobs(self.JOBS),o.rank_jobs(list(reversed(self.JOBS))))
    def test_reposted_vacancies_share_an_entity_key(self):
        a=o.entity_key('Acme Inc.','Senior Python Developer (Remote)','Hyderabad, India');b=o.entity_key('ACME','Python Developer','Hyderabad')
        self.assertEqual(a,b);self.assertNotEqual(a,o.entity_key('Acme','Python Developer','Pune'));self.assertNotEqual(a,o.entity_key('Acme','Java Developer','Hyderabad'))

class VacancyTests(unittest.TestCase):
    def test_only_an_active_easy_apply_page_is_verified_open(self):
        for verdict,status in (('easy','open'),('closed','closed'),('applied','closed'),('external','closed'),('unknown','uncertain'),('weird','uncertain')):
            self.assertEqual(o.classify_vacancy(verdict)['status'],status,verdict)
        v=o.classify_vacancy('easy','https://www.linkedin.com/jobs/view/1/?trk=x');self.assertTrue(o.verified_open(v));self.assertTrue(v['checked_at'] and v['evidence'])
        self.assertEqual(v['url'],'https://www.linkedin.com/jobs/view/1/')
    def test_closed_and_uncertain_cannot_be_started_and_uncertain_is_not_verified(self):
        for verdict in ('closed','unknown'):
            v=o.classify_vacancy(verdict);self.assertTrue(o.blocks_application(v));self.assertFalse(o.verified_open(v))
        self.assertFalse(o.blocks_application(None));self.assertFalse(o.blocks_application({'status':'unverified'}));self.assertFalse(o.verified_open({'status':'unverified'}))

PROFILE={**DEMO_PROFILE,'resume_text':'Built a dashboard used by 200 users. Improved test coverage by 35%. Skills: Python, SQL. AWS Certified Cloud Practitioner.'}
class GroundingTests(unittest.TestCase):
    def test_supported_claims_pass(self):
        r=o.grounding_report({'resume':'Built a dashboard used by 200 users. Improved coverage by 35%. AWS Certified Cloud Practitioner.','cover_letter':''},PROFILE)
        self.assertEqual(r['ungrounded'],[])
    def test_invented_metrics_and_certifications_are_flagged(self):
        r=o.grounding_report({'resume':'Grew revenue by 90%. Led 12+ years of work. Google Certified Professional Architect.','cover_letter':'Saved $2M.'},PROFILE)
        text=' | '.join(r['ungrounded']);self.assertIn('90%',text);self.assertIn('Certified',text);self.assertIn('$2M',text);self.assertIn('12+ years',text)
    def test_a_skill_the_candidate_lacks_cannot_be_claimed(self):
        r=o.grounding_report({'resume':'Experienced with Kubernetes and Python.','cover_letter':'I am keen to learn Kubernetes.'},PROFILE,missing_skills=['Kubernetes'])
        self.assertEqual(len(r['ungrounded']),1);self.assertIn('Kubernetes',r['ungrounded'][0])
        self.assertEqual(o.grounding_report({'resume':'Experienced with Python.','cover_letter':'I am keen to learn Kubernetes.'},PROFILE,missing_skills=['Kubernetes'])['ungrounded'],[])
    def test_the_person_can_confirm_a_claim(self):
        r=o.grounding_report({'resume':'Grew revenue by 90%.','cover_letter':''},PROFILE,confirmed=['90%'])
        self.assertEqual(r['ungrounded'],[])

class TraceAndRetryTests(unittest.TestCase):
    def test_traces_are_capped_and_redacted(self):
        state={}
        for i in range(250):state=o.trace(state,'rank',f'job {i}','keep',f'mail me at a{i}@x.com or +91 90000 00000')
        self.assertEqual(len(state['trace']),200);self.assertNotIn('@',str(state['trace']));self.assertNotIn('90000',str(state['trace']))
    def test_secrets_are_redacted(self):
        self.assertNotIn('abcdefghijklmnop',o.redact('key sk-abcdefghijklmnop leaked'))
    def run_retry(self,errors,attempts=3):
        calls=[];slept=[]
        async def sleep(s):slept.append(s)
        async def op():
            calls.append(1)
            if len(calls)<=len(errors):raise errors[len(calls)-1]
            return 'ok'
        try:result=asyncio.run(o.retry(op,attempts=attempts,sleep=sleep))
        except Exception as error:result=type(error).__name__
        return result,len(calls),slept
    def test_transient_errors_are_retried_with_backoff(self):
        self.assertEqual(self.run_retry([HTTPException(503,'x'),TimeoutError()]),('ok',3,[0.5,1.0]))
    def test_retries_are_bounded(self):
        self.assertEqual(self.run_retry([HTTPException(502,'x')]*5)[:2],('HTTPException',3))
    def test_a_person_fixable_error_is_never_retried(self):
        self.assertEqual(self.run_retry([HTTPException(409,'confirm your profile')])[:2],('HTTPException',1))

def history(n_good=12,n_bad=18):
    """Synthetic results where fit score alone ranks poorly (scores overlap) but a second signal separates the groups."""
    rows=[]
    for i in range(n_good):rows.append({'id':f'g{i}','score':62+i*2,'mode':'Remote','min_experience':0,'decided':True,'progressed':True,'junk':0})
    for i in range(n_bad):rows.append({'id':f'b{i}','score':64+i*2,'mode':'Onsite','min_experience':2,'decided':True,'progressed':i%9==0,'junk':1})
    return rows

class OutcomeTests(unittest.TestCase):
    def test_conversion_definitions(self):
        rows=[{'stage':'interview','fit_feedback':'up'},{'stage':'rejected','fit_feedback':'down'},{'stage':'waiting'},{'stage':'offer'},{'stage':'no_response'}]
        s=o.conversion_stats(rows);self.assertEqual((s['submitted'],s['progressed'],s['shortlist_rate'],s['decided_rate'],s['response_rate']),(5,2,40,67,60))
        self.assertEqual((s['fit_up'],s['fit_down']),(1,1));self.assertIn('divided by all submitted',s['definition'])
    def test_no_submissions_means_no_rate(self):
        s=o.conversion_stats([]);self.assertIsNone(s['shortlist_rate']);self.assertIsNone(s['decided_rate'])
    def test_buckets_use_decided_results_only(self):
        rep=o.bucket_report(history()+[{'score':99,'decided':False,'progressed':False}])['by_fit_score']
        self.assertNotIn('99',str(rep));self.assertEqual(sum(v['decided'] for v in rep.values()),30)
    def test_a_ranking_is_compared_with_the_baseline_on_recorded_outcomes(self):
        h=history();better=o.compare_rankings(h,candidate_key=lambda r:r['score']-30*r['junk'])
        self.assertTrue(better['enough_data']);self.assertGreater(better['candidate_ap'],better['baseline_ap']);self.assertTrue(better['better'])
        same=o.compare_rankings(h,candidate_key=lambda r:r['score']);self.assertEqual(same['delta'],0);self.assertFalse(same['better'])   # an identical ranking is not an improvement
    def test_too_little_data_proposes_nothing(self):
        r=o.compare_rankings(history(3,4),candidate_key=lambda r:r['score'])
        self.assertFalse(r['enough_data']);self.assertNotIn('better',r)
    def test_threshold_advice_is_advisory_and_needs_data(self):
        self.assertIsNone(o.suggest_threshold(history(2,3),60))
        rows=[{'score':65,'decided':True,'progressed':False} for _ in range(8)]+[{'score':85,'decided':True,'progressed':True} for _ in range(8)]
        self.assertIn('raising',o.suggest_threshold(rows,60));self.assertIsNone(o.suggest_threshold(rows,70))

def mode_history(n=20):
    """SYNTHETIC results, built only to exercise the code (not real-world evidence): remote jobs with slightly lower fit scores progress
    far more often than onsite jobs with slightly higher scores, so fit score alone ranks them in the wrong order."""
    rows=[]
    for i in range(n):
        rows.append({'id':f'o{i:03d}','score':70+i%4,'mode':'Onsite','min_experience':None,'decided':True,'progressed':i%10==0,'global_score':0})
        rows.append({'id':f'r{i:03d}','score':66+i%4,'mode':'Remote','min_experience':None,'decided':True,'progressed':i%5<3,'global_score':0})
    return rows

class RankingProposalTests(unittest.TestCase):
    """All histories here are SYNTHETIC. They prove the mechanism works; they say nothing about real interview rates."""
    def test_too_little_data_proposes_nothing(self):
        r=o.propose_ranking(mode_history(5));self.assertEqual(r['status'],'insufficient_data');self.assertNotIn('adjustments',r)
        few_hits=[{**h,'progressed':False} for h in mode_history()];self.assertEqual(o.propose_ranking(few_hits)['status'],'insufficient_data')
    def test_a_pattern_that_holds_on_held_out_results_is_proposed(self):
        r=o.propose_ranking(mode_history());self.assertEqual(r['status'],'proposed',r)
        self.assertGreater(r['adjustments']['mode']['Remote'],0);self.assertLess(r['adjustments']['mode']['Onsite'],0)
        self.assertEqual(len(r['evaluation']['folds']),2);self.assertTrue(all(f['delta']>=0 for f in r['evaluation']['folds']))
        self.assertGreaterEqual(r['evaluation']['mean_delta'],o.MIN_GAIN);self.assertTrue(r['rationale']);self.assertIn('not proof',r['caveat'])
    def test_noise_is_not_proposed(self):
        noise=[{'id':f'{m}{i:03d}','score':70+i%5,'mode':m,'min_experience':None,'decided':True,'progressed':i%4==0,'global_score':0} for i in range(20) for m in ('Remote','Onsite')]
        self.assertEqual(o.propose_ranking(noise)['status'],'no_improvement')
    def test_adjustments_are_small_and_capped(self):
        extreme=[{'id':f'{m}{i:03d}','score':70,'mode':m,'min_experience':None,'decided':True,'progressed':m=='Remote','global_score':0} for i in range(30) for m in ('Remote','Onsite')]
        table=o.learn_adjustments(extreme);self.assertTrue(all(abs(p)<=o.ADJUST_CAP for g in table.values() for p in g.values()))
    def test_small_groups_do_not_move_the_ranking(self):
        h=mode_history()+[{'id':f'x{i}','score':90,'mode':'Hybrid','min_experience':None,'decided':True,'progressed':True,'global_score':0} for i in range(o.GROUP_MIN-1)]
        self.assertNotIn('Hybrid',o.learn_adjustments(h).get('mode',{}))
    def test_proposals_are_deterministic_and_versioned_by_content(self):
        a=o.propose_ranking(mode_history());b=o.propose_ranking(list(reversed(mode_history())))
        self.assertEqual(a,b);self.assertTrue(a['version'].startswith('adj-'));self.assertEqual(o.ranking_version({}),o.BASELINE)
    def test_a_declined_version_is_not_proposed_again(self):
        version=o.propose_ranking(mode_history())['version'];self.assertEqual(o.propose_ranking(mode_history(),rejected=[version])['status'],'rejected')
    def test_the_proposal_is_judged_on_results_it_was_not_learned_from(self):
        """SYNTHETIC: the remote-is-better pattern holds in one half of the results and reverses in the other, so what is learned from
        one half fails on the other. A proposal must not be made, which a same-data check would have missed."""
        rows=[]
        for k in range(60):
            first_half=k%2==0;remote=(k%4==0) if first_half else (k%4==1)
            good=(remote if first_half else not remote)&(k//4%5<4)
            rows.append({'id':f'k{k:03d}','score':66+k%4 if remote else 70+k%4,'mode':'Remote' if remote else 'Onsite','min_experience':None,'decided':True,'progressed':good,'global_score':0})
        folds=o.evaluate_adjustments(rows);self.assertEqual(len(folds),2);self.assertTrue(any(f['delta']<0 for f in folds),folds)
        self.assertNotEqual(o.propose_ranking(rows)['status'],'proposed')
    def test_baseline_ranking_is_untouched_without_an_accepted_adjustment(self):
        jobs=[{'canonical':'a','score':70,'mode':'Onsite'},{'canonical':'b','score':66,'mode':'Remote'}]
        self.assertEqual([j['canonical'] for j in o.rank_jobs(jobs)],['a','b']);self.assertEqual(o.rank_jobs(jobs),o.rank_jobs(jobs,{}))
    def test_an_accepted_adjustment_reorders_but_never_rewrites_the_fit_score(self):
        jobs=[{'canonical':'a','score':70,'mode':'Onsite'},{'canonical':'b','score':66,'mode':'Remote'}];table={'mode':{'Remote':5,'Onsite':-5}}
        ranked=o.rank_jobs(jobs,table);self.assertEqual([j['canonical'] for j in ranked],['b','a']);self.assertEqual([j['score'] for j in ranked],[66,70])
        self.assertEqual(o.rank_jobs(jobs,table),o.rank_jobs(list(reversed(jobs)),table))
    def test_ties_still_break_by_the_raw_fit_score(self):
        jobs=[{'canonical':'a','score':72,'mode':'Hybrid'},{'canonical':'b','score':70,'mode':'Remote'}]
        self.assertEqual([j['canonical'] for j in o.rank_jobs(jobs,{'mode':{'Remote':2}})],['a','b'])

if __name__=='__main__':unittest.main()
