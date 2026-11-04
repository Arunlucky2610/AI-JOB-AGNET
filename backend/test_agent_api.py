"""The agent's safety gates at the API: vacancy verification, grounded documents, duplicate postings, concurrent starts, insights."""
import os, tempfile, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TEST_DIR=tempfile.TemporaryDirectory()
os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(TEST_DIR.name)/'agent.db').replace('\\','/'))
os.environ['ALLOW_DEMO']='true'
from fastapi.testclient import TestClient
from .main import app
from .db import Session, Application, Job, now
from . import orchestrator
from .test_orchestrator import mode_history

ORIGIN={'origin':'http://127.0.0.1:3000'}

class GateTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app,headers=ORIGIN);self.client.__enter__()
        self.assertEqual(self.client.post('/api/auth/demo',json={}).status_code,200)
        self.client.put('/api/settings',json={'mode':'each','daily_limit':10,'auto_enabled':False})
    def tearDown(self):self.client.__exit__(None,None,None)
    def ready(self):return next(a for a in self.client.get('/api/applications').json() if a['status']=='prepared')
    def approve_and_start(self,a):
        approved=self.client.post('/api/applications/approve',json={'ids':[a['id']]})
        return approved,self.client.post(f"/api/applications/{a['id']}/action",json={'action':'start'}) if approved.status_code==200 else None
    def set_job(self,app_id,**changes):
        with Session() as db:
            job=db.get(Job,db.get(Application,app_id).job_id);job.payload={**job.payload,**changes};db.commit()

    def test_a_closed_or_uncertain_vacancy_cannot_be_started(self):
        for verdict in ('closed','unknown'):
            a=self.ready();self.set_job(a['id'],verification=orchestrator.classify_vacancy(verdict))
            approved,started=self.approve_and_start(a)
            self.assertEqual(started.status_code,409,verdict);self.assertIn('not verified open',started.json()['detail'])
            with Session() as db:db.get(Application,a['id']).status='stopped';db.commit()
    def test_a_verified_open_vacancy_can_be_started(self):
        a=self.ready();self.set_job(a['id'],verification=orchestrator.classify_vacancy('easy'))
        self.assertEqual(self.approve_and_start(a)[1].status_code,200)
    def test_the_application_reports_its_verification_and_grounding(self):
        a=self.ready();self.assertIn('ungrounded',a['grounding']);self.assertIn('job',a)
    def test_unsupported_claims_block_approval_until_confirmed_or_removed(self):
        a=self.ready();package={**a['package'],'resume':a['package']['resume']+'\nGrew revenue by 487% at Imaginary Corp.'}
        self.assertEqual(self.client.put(f"/api/applications/{a['id']}/package",json=package).status_code,200)
        blocked=self.client.post('/api/applications/approve',json={'ids':[a['id']]})
        self.assertEqual(blocked.status_code,409);self.assertIn('487%',blocked.json()['detail'])
        shown=self.client.get('/api/applications').json();claim=next(x for x in shown if x['id']==a['id'])['grounding']['ungrounded'][0]
        self.assertEqual(self.client.put(f"/api/applications/{a['id']}/package",json={**package,'confirmed_claims':[claim]}).status_code,200)
        self.assertEqual(self.client.post('/api/applications/approve',json={'ids':[a['id']]}).status_code,200)
    def test_confirming_a_claim_changes_the_package_so_old_approval_is_void(self):
        a=self.ready();self.client.post('/api/applications/approve',json={'ids':[a['id']]})
        self.client.put(f"/api/applications/{a['id']}/package",json={**a['package'],'confirmed_claims':['x']})
        self.assertFalse(next(x for x in self.client.get('/api/applications').json() if x['id']==a['id'])['approved'])
    def test_the_same_vacancy_under_another_url_is_not_applied_to_twice(self):
        import uuid
        a=self.ready()
        with Session() as db:
            row=db.get(Application,a['id']);job=db.get(Job,row.job_id)
            twin=Job(id=str(uuid.uuid4()),user_id=row.user_id,canonical=job.canonical+'#repost',payload={**job.payload,'url':job.payload['url']+'#repost','title':'Senior '+job.payload['title']})
            db.add(twin);db.flush()
            db.add(Application(id=str(uuid.uuid4()),user_id=row.user_id,job_id=twin.id,status='submitted',package={},events=[],browser={}));db.commit()
        blocked=self.approve_and_start(a)[1]
        self.assertEqual(blocked.status_code,409);self.assertIn('already applied',blocked.json()['detail'])
    def test_two_simultaneous_starts_run_the_application_once(self):
        a=self.ready();self.client.post('/api/applications/approve',json={'ids':[a['id']]})
        def start(_):return self.client.post(f"/api/applications/{a['id']}/action",json={'action':'start'}).status_code
        with ThreadPoolExecutor(2) as pool:codes=sorted(pool.map(start,range(2)))
        self.assertEqual(codes,[200,409])
    def test_starting_without_approval_is_refused(self):
        a=self.ready();r=self.client.post(f"/api/applications/{a['id']}/action",json={'action':'start'})
        self.assertEqual(r.status_code,409);self.assertIn('Approve this exact package',r.json()['detail'])

class EvidenceTests(unittest.TestCase):
    def test_screenshots_are_served_only_to_their_owner_and_only_if_captured(self):
        from unittest.mock import patch
        client=TestClient(app,headers=ORIGIN);client.__enter__();client.post('/api/auth/demo',json={})
        try:
            app_id=next(a['id'] for a in client.get('/api/applications').json() if a['status']=='submitted')
            self.assertEqual(client.get(f'/api/applications/{app_id}/evidence/confirmation').status_code,404)
            with tempfile.TemporaryDirectory() as folder, patch.object(orchestrator,'EVIDENCE_DIR',Path(folder)):
                (Path(folder)/'shot.png').write_bytes(b'\x89PNG fake')
                with Session() as db:
                    row=db.get(Application,app_id);row.browser={**row.browser,'evidence':{'screenshots':{'confirmation':'shot.png'}}};db.commit()
                r=client.get(f'/api/applications/{app_id}/evidence/confirmation');self.assertEqual((r.status_code,r.headers['content-type']),(200,'image/png'))
                other=TestClient(app,headers=ORIGIN);other.post('/api/auth/demo',json={})
                self.assertEqual(other.get(f'/api/applications/{app_id}/evidence/confirmation').status_code,404)
                with Session() as db:
                    row=db.get(Application,app_id);row.browser={**row.browser,'evidence':{'screenshots':{'confirmation':'../../etc/passwd'}}};db.commit()
                self.assertEqual(client.get(f'/api/applications/{app_id}/evidence/confirmation').status_code,404,'a stored name can never point outside the evidence folder')
        finally:client.__exit__(None,None,None)

class InsightTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app,headers=ORIGIN);self.client.__enter__();self.client.post('/api/auth/demo',json={})
    def tearDown(self):self.client.__exit__(None,None,None)
    def test_insights_are_advisory_and_need_enough_results(self):
        r=self.client.get('/api/outcomes/insights').json()
        self.assertFalse(r['ranking_test']['enough_data']);self.assertIn('Advisory',r['note']);self.assertIn('by_fit_score',r['buckets'])
    def test_summary_states_its_denominator(self):
        s=self.client.get('/api/outcomes/summary').json()
        self.assertIn('all submitted applications',s['definition']);self.assertEqual(s['submitted'],3)
    def test_the_default_threshold_follows_career_level(self):
        me=self.client.get('/api/me').json();self.assertIsNone(me['settings']['threshold']);self.assertEqual(me['settings']['effective_threshold'],70)

class RankingApiTests(unittest.TestCase):
    """The whole proposal -> accept/reject path through the API, on SYNTHETIC recorded results (not real-world evidence)."""
    def setUp(self):
        import uuid
        from .db import Outcome
        self.client=TestClient(app,headers=ORIGIN);self.client.__enter__();self.client.post('/api/auth/demo',json={})
        with Session() as db:
            uid=db.get(Application,self.client.get('/api/applications').json()[0]['id']).user_id
            for h in mode_history():
                job=Job(id=str(uuid.uuid4()),user_id=uid,canonical='https://example.invalid/'+h['id'],payload={'title':'t','company':'c','mode':h['mode'],'min_experience':None,'match':{'score':h['score']}})
                db.add(job);db.flush();application=Application(id=str(uuid.uuid4()),user_id=uid,job_id=job.id,status='submitted',package={},events=[],browser={});db.add(application);db.flush()
                db.add(Outcome(application_id=application.id,user_id=uid,stage='interview' if h['progressed'] else 'rejected'))
            db.commit()
    def tearDown(self):self.client.__exit__(None,None,None)
    def view(self):return self.client.get('/api/outcomes/insights').json()['ranking']
    def test_a_proposal_exists_but_nothing_is_active_until_accepted(self):
        v=self.view();self.assertEqual(v['proposal']['status'],'proposed');self.assertIsNone(v['active']);self.assertEqual(v['baseline'],'baseline')
        me=self.client.get('/api/me').json();self.assertFalse(me['settings'].get('ranking'),'a proposal alone changes no setting')
    def test_accepting_activates_exactly_the_proposed_version_and_keeps_goals_and_limits(self):
        before=self.client.get('/api/me').json();version=self.view()['proposal']['version']
        r=self.client.post('/api/ranking/accept',json={'version':version});self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['active']['version'],version);self.assertTrue(r.json()['active']['accepted_at'])
        self.assertEqual(r.json()['proposal']['status'],'already_active','an accepted proposal is not offered again')
        after=self.client.get('/api/me').json()
        for key in before['settings']:self.assertEqual(before['settings'][key],after['settings'][key],key)   # every setting except the new ranking is untouched
        self.assertEqual(before['profile'],after['profile'])
    def test_a_stale_or_unseen_version_cannot_be_accepted(self):
        r=self.client.post('/api/ranking/accept',json={'version':'adj-00000000'});self.assertEqual(r.status_code,409);self.assertIsNone(self.view()['active'])
    def test_rejecting_leaves_the_ranking_unchanged_and_hides_that_proposal(self):
        version=self.view()['proposal']['version'];r=self.client.post('/api/ranking/reject',json={'version':version}).json()
        self.assertIsNone(r['active']);self.assertEqual(r['proposal']['status'],'rejected')
        self.assertEqual(self.client.post('/api/ranking/accept',json={'version':version}).status_code,409,'a declined proposal cannot be accepted by replay')
    def test_rejecting_another_proposal_does_not_disturb_an_accepted_ranking(self):
        version=self.view()['proposal']['version'];self.client.post('/api/ranking/accept',json={'version':version})
        r=self.client.post('/api/ranking/reject',json={'version':'adj-12345678'}).json();self.assertEqual(r['active']['version'],version)
    def test_saving_preferences_keeps_the_accepted_ranking(self):
        version=self.view()['proposal']['version'];self.client.post('/api/ranking/accept',json={'version':version})
        self.assertEqual(self.client.put('/api/settings',json={'mode':'each','daily_limit':5,'auto_enabled':False}).status_code,200)
        self.assertEqual(self.view()['active']['version'],version)
    def test_deactivating_returns_to_the_baseline(self):
        version=self.view()['proposal']['version'];self.client.post('/api/ranking/accept',json={'version':version})
        self.assertIsNone(self.client.post('/api/ranking/deactivate').json()['active'])
    def test_without_enough_results_there_is_nothing_to_accept(self):
        fresh=TestClient(app,headers=ORIGIN);fresh.post('/api/auth/demo',json={})
        v=fresh.get('/api/outcomes/insights').json()['ranking'];self.assertEqual(v['proposal']['status'],'insufficient_data')
        self.assertEqual(fresh.post('/api/ranking/accept',json={'version':'adj-00000000'}).status_code,409)

def tearDownModule():pass
if __name__=='__main__':unittest.main()
