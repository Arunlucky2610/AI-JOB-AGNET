"""Speed work: Jev triage (shadow/active, DeepSeek fallback), rules-first form planning, faster page waits.
No Jev, LinkedIn, Browserbase or OpenRouter traffic."""
import asyncio, contextlib, json, os, tempfile, time, unittest
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(tempfile.gettempdir())/'orbit-test-speed-unused.db').replace('\\','/'))
from playwright.async_api import async_playwright
from . import agent, jev, linkedin, main, platform_agent, worker
from .db import User, AgentRun, Application, Job, SkippedJob, now
from .domain import fingerprint
from .test_linkedin import Db, PROFILE, SETTINGS, SEARCH, JOB_SHADOW, EXTERNAL_JOB, assessment, linkedin_site, linkedin_model
from .test_worker import fake_pdf

def answers(choice='none_stated',confidence=0.95,ai=0.9,software=0.1,junior=0.1):
    return {'min_experience':{'type':'choice','choice':choice,'confidence':confidence,'probabilities':{}},
            'ai_ml_role':{'type':'noul','noul':ai},'software_role':{'type':'noul','noul':software},'junior_level':{'type':'noul','noul':junior}}

class FakeResponse:
    def __init__(self,status=200,body=None):self.status_code=status;self._body=body if body is not None else {'answers':answers()}
    def json(self):return self._body

def fake_client(responses,calls):
    class Client:
        def __init__(self,*a,**k):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):return False
        async def post(self,url,headers=None,json=None):
            calls.append((url,json));item=responses[min(len(calls)-1,len(responses)-1)]
            if isinstance(item,Exception):raise item
            return item
    return Client

class JevClientTests(unittest.TestCase):
    def call(self,responses,key='k'):
        calls=[]
        async def no_sleep(_):return None
        env={'OPENROUTER_API_KEY':key} if key else {}
        with patch.dict(os.environ,env,clear=not key),patch.object(jev.httpx,'AsyncClient',fake_client(responses,calls)),patch.object(jev.asyncio,'sleep',no_sleep):
            try:result=asyncio.run(jev.decide({'title':'t','description':'d'},jev.TRIAGE_QUESTIONS))
            except jev.JevUnavailable as error:result=error
        return result,calls
    def test_a_good_reply_is_returned(self):
        result,calls=self.call([FakeResponse()]);self.assertEqual(result['min_experience']['choice'],'none_stated');self.assertEqual(len(calls),1)
    def test_temporary_errors_are_retried(self):
        result,calls=self.call([FakeResponse(520),FakeResponse(429),FakeResponse()]);self.assertIn('min_experience',result);self.assertEqual(len(calls),3)
    def test_connection_errors_are_retried_then_reported(self):
        import httpx
        result,calls=self.call([httpx.ConnectError('x')]);self.assertIsInstance(result,jev.JevUnavailable);self.assertEqual(len(calls),3)
    def test_rejections_are_not_retried(self):
        for status in (401,402,422):
            with self.subTest(status):
                result,calls=self.call([FakeResponse(status)]);self.assertIsInstance(result,jev.JevUnavailable);self.assertEqual(len(calls),1)
    def test_no_key_means_unavailable(self):
        result,calls=self.call([FakeResponse()],key=None);self.assertIsInstance(result,jev.JevUnavailable);self.assertEqual(calls,[])
    def test_an_unreadable_reply_is_unavailable(self):
        result,_=self.call([FakeResponse(200,{'oops':1})]);self.assertIsInstance(result,jev.JevUnavailable)
    def test_only_the_public_posting_is_sent(self):
        _,calls=self.call([FakeResponse()])
        body=calls[0][1];sent=json.loads(body['state'])
        self.assertEqual(set(sent),{'title','description'});self.assertEqual(body['model'],'typesafe/jev-1.13')
    def test_mode_defaults_to_shadow_and_rejects_nonsense(self):
        for value,expected in ((None,'shadow'),('active','active'),('OFF','off'),('yolo','shadow')):
            env={'JEV_MODE':value} if value else {}
            with patch.dict(os.environ,env,clear=True):self.assertEqual(jev.mode(),expected,value)

class TriageTests(unittest.TestCase):
    def test_experience_is_compared_in_code_and_only_when_confident(self):
        t=lambda years=0,**kw:jev.triage(answers(**kw),years,True)[0]
        self.assertEqual(t(choice='two_to_three_years'),'skip_experience');self.assertEqual(t(choice='four_plus_years'),'skip_experience')
        self.assertEqual(t(choice='up_to_1_year'),'review','a 1-year job still goes to DeepSeek')
        self.assertEqual(t(choice='none_stated'),'review')
        self.assertEqual(t(years=3,choice='two_to_three_years'),'review');self.assertEqual(t(years=3,choice='four_plus_years'),'skip_experience')
        self.assertEqual(t(choice='four_plus_years',confidence=0.79),'uncertain')
    def test_roles_only_skip_when_clearly_wrong(self):
        t=lambda **kw:jev.triage(answers(**kw),0,True)[0]
        self.assertEqual(t(ai=0.9),'review');self.assertEqual(t(ai=0.1,software=0.9,junior=0.9),'review')
        self.assertEqual(t(ai=0.05,software=0.05),'skip_role')
        self.assertEqual(t(ai=0.3,software=0.9,junior=0.1),'uncertain','a senior software role is not skipped by Jev alone')
    def test_strict_matching_only_triages_experience(self):
        self.assertEqual(jev.triage(answers(ai=0.0,software=0.0),0,False)[0],'review')
    def test_bad_answers_route_to_deepseek(self):
        for broken in ({},{'min_experience':{}},{**answers(),'ai_ml_role':{'noul':'x'}},{**answers(choice='mystery')}):
            self.assertEqual(jev.triage(broken,0,True)[0],'uncertain')
    def test_outcomes_against_deepseek(self):
        c=jev.compare
        self.assertEqual((c('skip_role',True),c('skip_experience',False),c('review',True),c('uncertain',False)),('missed_match','agree_skip','agree_review','extra_review'))
    def test_only_the_about_section_is_sent(self):
        page='Home My Network Jobs\nAbout the job\nBuild LLM features.\nRequires 2 years.\nAbout the company\nAcme is big\nSimilar jobs\nX'
        d=jev.job_state('AI Engineer',page)['description'];self.assertIn('Build LLM features',d);self.assertNotIn('Acme',d);self.assertNotIn('My Network',d)
        self.assertIn('Home',jev.job_state('t','no marker here Home')['description'])
        self.assertLessEqual(len(jev.job_state('t','x '*9000)['description']),3500)

def el(id,tag='INPUT',type='text',text='',label='',**k):return {'id':id,'tag':tag,'type':type,'text':text,'label':label,'filled':False,'required':False,**k}
FIELDS={'phone_national':'90000 00000','email':'a@example.invalid','city':'Hyderabad'}
PKG={'resume':'r','cover_letter':'c'}

class RulePlanTests(unittest.TestCase):
    def plan(self,elements,fields=FIELDS,package=PKG):return worker.rule_plan({'elements':elements},fields,package)
    def kinds(self,plan):return None if plan is None else [a['action'] for a in plan['actions']]
    def test_contact_step_is_planned_without_the_model(self):
        plan=self.plan([el(0,'BUTTON','submit',label='Dismiss'),el(1,'SELECT','select-one',label='Email address',filled=True),el(2,'SELECT','select-one',label='Phone country code',filled=True),
                        el(3,label='Mobile phone number',required=True),el(4,'A','',text='Help Center'),el(5,'BUTTON','button',text='Next',label='Continue to next step')])
        self.assertEqual(self.kinds(plan),['fill','click']);self.assertEqual(plan['actions'][0]['field_key'],'phone_national')
    def test_a_city_field_is_filled_with_the_first_preferred_city(self):
        plan=self.plan([el(0,label='Location (city)',required=True),el(1,'BUTTON','button',text='Next')])
        self.assertEqual(self.kinds(plan),['fill','click']);self.assertEqual(plan['actions'][0]['field_key'],'city')
    def test_the_resume_step_is_planned_by_rules_when_a_resume_is_already_selected(self):
        plan=self.plan([el(0,'BUTTON','submit',label='Dismiss'),el(1,'BUTTON','button',label='Download resume resume.pdf'),
                        el(2,'INPUT','radio',label='Deselect resume resume.pdf',filled=True,checked=True),el(3,'BUTTON','button',label='Download resume resume.pdf'),
                        el(4,'INPUT','radio',label='Select resume resume.pdf',filled=True,checked=False),el(5,'SPAN','',text='Upload resume',label='Upload resume button. Only, DOC, DOCX, P'),
                        el(6,'INPUT','file',label='Upload resume'),el(7,'A','',text='Help Center',label='Visit help center to know more'),
                        el(8,'BUTTON','button',text='Back',label='Back to previous step'),el(9,'BUTTON','button',text='Next',label='Continue to next step')])
        self.assertIsNotNone(plan);self.assertEqual(self.kinds(plan)[-1],'click')
    def test_with_no_resume_selected_the_rules_still_ask_the_model(self):
        plan=self.plan([el(0,'INPUT','radio',label='Select resume a.pdf',checked=False),el(1,'INPUT','radio',label='Select resume b.pdf',checked=False),el(2,'BUTTON','button',text='Next')])
        self.assertIsNone(plan)
    def test_a_filled_phone_is_left_alone(self):
        self.assertEqual(self.kinds(self.plan([el(0,label='Mobile phone number',filled=True),el(1,'BUTTON','button',text='Next')])),['click'])
    def test_review_step_submits(self):
        plan=self.plan([el(0,'BUTTON','submit',label='Dismiss'),el(1,'BUTTON','button',text='Submit application'),el(2,'BUTTON','button',text='Back'),el(3,type='checkbox',label='Follow Acme',**{'checked':True})])
        self.assertEqual(self.kinds(plan),['submit'])
    def test_resume_upload_uses_the_input_and_ignores_its_trigger(self):
        plan=self.plan([el(0,type='file',label='Upload resume'),el(1,'BUTTON','button',text='Upload resume'),el(2,'BUTTON','button',text='Next')])
        self.assertEqual(self.kinds(plan),['upload_resume','click'])
    def test_input_type_submit_can_be_the_way_forward(self):
        self.assertEqual(self.kinds(self.plan([el(0,'INPUT','submit',text='Next step')])),['click'])
    def test_anything_needing_judgment_goes_to_the_model(self):
        cases={'a question':[el(0,label='Portfolio link',required=True),el(1,'BUTTON','button',text='Next')],
               'an unfilled dropdown':[el(0,'SELECT','select-one',label='Notice period'),el(1,'BUTTON','button',text='Next')],
               'an unanswered radio group':[el(0,type='radio',label='Yes',group='Authorized?',**{'checked':False}),el(1,type='radio',label='No',group='Authorized?',**{'checked':False}),el(2,'BUTTON','button',text='Review')],
               'an unticked checkbox':[el(0,type='checkbox',label='I have a disability'),el(1,'BUTTON','button',text='Next')],
               'an unknown button':[el(0,'BUTTON','button',text='Add another employer'),el(1,'BUTTON','button',text='Next')],
               'two ways forward':[el(0,'BUTTON','button',text='Next'),el(1,'BUTTON','button',text='Review')],
               'no way forward':[el(0,label='Mobile phone number',filled=True)],
               'an unlabelled submit':[el(0,'BUTTON','submit')]}
        for name,elements in cases.items():
            with self.subTest(name):self.assertIsNone(self.plan(elements))
    def test_an_answered_radio_group_needs_no_model(self):
        plan=self.plan([el(0,type='radio',label='Yes',group='Authorized?',**{'checked':True}),el(1,type='radio',label='No',group='Authorized?',**{'checked':False}),el(2,'BUTTON','button',text='Review')])
        self.assertEqual(self.kinds(plan),['click'])
    def test_missing_ingredients_fall_back_to_the_model(self):
        self.assertIsNone(self.plan([el(0,label='Mobile phone number'),el(1,'BUTTON','button',text='Next')],fields={}))
        self.assertIsNone(self.plan([el(0,type='file',label='Resume'),el(1,'BUTTON','button',text='Next')],package={}))
    def test_a_rule_plan_still_passes_the_same_safety_checks(self):
        elements=[el(0,label='Mobile phone number'),el(1,'BUTTON','button',text='Next')]
        plan=self.plan(elements);self.assertEqual(len(worker.validate_batch(plan,{'elements':elements},FIELDS)),2)

class PageWaitTests(unittest.TestCase):
    def browse(self,html,body):
        async def go():
            async with async_playwright() as p:
                browser=await p.chromium.launch();page=await browser.new_page();await page.set_content(html)
                started=time.monotonic();out=await body(page);elapsed=time.monotonic()-started;await browser.close();return out,elapsed
        return asyncio.run(go())
    def test_settle_does_not_burn_a_fixed_idle_timeout(self):
        _,elapsed=self.browse('<main>hello</main>',linkedin.settle);self.assertLess(elapsed,2.5)
    def test_a_late_easy_apply_button_is_still_found(self):
        html='<main><script>setTimeout(()=>{const a=document.createElement("a");a.textContent="Easy Apply";document.querySelector("main").appendChild(a)},1500)</script></main>'
        state,_=self.browse(html,linkedin.apply_state_settled);self.assertEqual(state,'easy')
    def test_a_page_with_no_button_settles_to_unknown(self):
        state,elapsed=self.browse('<main>nothing</main>',linkedin.apply_state_settled);self.assertEqual(state,'unknown');self.assertLess(elapsed,6)

# A contact step like LinkedIn's: the city box is a typeahead that only accepts a suggestion from its list, and
# Next does nothing until one is picked, exactly like the real form.
TYPEAHEAD='''<!DOCTYPE html><html><body>
<main><h1>Software Intern</h1><a id="easy" role="button" href="/apply" onclick="return false"><span>Easy Apply</span></a></main>
<div id="modal" role="dialog" class="artdeco-modal jobs-easy-apply-modal" hidden>
 <div id="s1"><h2>Contact info</h2>
  <label for="loc">Location (city)</label>
  <input id="loc" role="combobox" aria-autocomplete="list" autocomplete="off" required>
  <ul id="lb" role="listbox" hidden style="position:absolute;background:#fff;z-index:9;width:260px;margin:0;padding:0"><li role="option" id="opt" style="padding:20px">Hyderabad, Telangana, India</li></ul>
  <button type="button" id="next">Next</button></div>
 <div id="s2" hidden><h2>Review your application</h2><button type="button" id="submit">Submit application</button></div>
 <div id="sent" hidden><h2 id="sent-h">Application sent</h2></div>
</div>
<script>
const $=id=>document.getElementById(id);
$('easy').addEventListener('click',()=>{$('modal').hidden=false});
$('loc').oninput=()=>{$('lb').hidden=$('loc').value.trim().length<3;$('loc').dataset.picked=''};
$('opt').onclick=()=>{$('loc').value='Hyderabad, Telangana, India';$('lb').hidden=true;$('loc').dataset.picked='1'};
$('next').onclick=()=>{if(!$('loc').dataset.picked)return;$('s1').hidden=true;$('s2').hidden=false};
$('submit').onclick=()=>{$('sent-h').textContent='Application sent - '+$('loc').value;$('s2').hidden=true;$('sent').hidden=false};
</script></body></html>'''

def never_ask(seen):
    async def plan(system,payload,max_tokens=0,**_):raise AssertionError('this step must be planned by rules')
    return plan

class TypeaheadAndRobustnessTests(Db):
    def apply(self,html,model):
        from .test_linkedin import WorkerOnLinkedInTests
        return WorkerOnLinkedInTests.apply(self,html,model)
    def test_a_typeahead_city_is_filled_by_rules_and_a_suggestion_is_picked(self):
        a,_,_=self.apply(TYPEAHEAD,never_ask)
        self.assertEqual(a.status,'submitted',[e['text'] for e in a.events])
        self.assertTrue(any('Application sent - Hyderabad, Telangana, India' in e['text'] for e in a.events),[e['text'] for e in a.events])
    def test_a_form_that_cannot_be_completed_is_skipped_not_left_blocking_the_run(self):
        def broken(seen):
            async def plan(system,payload,max_tokens=0,**_):raise RuntimeError('boom')
            return plan
        from .test_linkedin import JOB_SHADOW
        a,_,_=self.apply(JOB_SHADOW,broken)
        self.assertEqual(a.status,'stopped');self.assertTrue(a.events[-1]['text'].startswith('Skipped: this form could not be completed'),a.events[-1]['text'])
    def test_out_of_credits_still_stops_for_the_person(self):
        from fastapi import HTTPException
        def broke(seen):
            async def plan(system,payload,max_tokens=0,**_):raise HTTPException(402,'OpenRouter credits are exhausted.')
            return plan
        from .test_linkedin import JOB_SHADOW
        a,_,_=self.apply(JOB_SHADOW,broke)
        self.assertEqual(a.status,'needs_input');self.assertIn('credits',a.events[-1]['text'])

YEARS_FIELDS={**FIELDS,'experience':'0','years:python':'1','years:react':'1','years:react native':'0.5','years:machine learning':'1'}

class YearsQuestionTests(unittest.TestCase):
    def ask(self,text,fields=YEARS_FIELDS):return worker.years_field(text,fields)
    def test_a_skill_the_person_listed_is_answered_from_their_table(self):
        self.assertEqual(self.ask('How many years of experience do you have with Python?'),'years:python')
        self.assertEqual(self.ask('Years of work experience in Python*'),'years:python')
        self.assertEqual(self.ask('years of professional experience using PYTHON'),'years:python')
    def test_a_skill_they_did_not_list_is_never_answered(self):
        self.assertIsNone(self.ask('How many years of experience do you have with Django?'))
        self.assertIsNone(self.ask('Years of experience with Java?'))
    def test_similar_names_do_not_borrow_each_others_years(self):
        self.assertEqual(self.ask('Years of experience with React Native?'),'years:react native')
        self.assertEqual(self.ask('Years of experience with React?'),'years:react')
        self.assertIsNone(self.ask('Years of experience with JavaScript?'),'java or react must not match javascript')
    def test_two_different_skills_in_one_question_are_left_to_a_person(self):
        self.assertIsNone(self.ask('Years of experience with Python and React?'))
    def test_general_experience_uses_the_profile_total(self):
        self.assertEqual(self.ask('How many years of experience do you have?'),'experience')
        self.assertIsNone(self.ask('How many years of experience do you have?',{'city':'x'}))
    def test_other_questions_are_not_matched(self):
        for q in ('Are you comfortable working onsite?','Expected CTC','Mobile phone number','Python'):self.assertIsNone(self.ask(q),q)
    def test_special_characters_in_skill_names_are_handled(self):
        fields={'years:c++':'2','years:c':'1','years:c#':'3'}
        self.assertEqual(self.ask('Years of experience with C++?',fields),'years:c++');self.assertEqual(self.ask('Years of experience with C#?',fields),'years:c#')
        self.assertEqual(self.ask('Years of experience with C?',fields),'years:c')
    def test_rules_fill_a_numeric_years_box_without_the_model(self):
        plan=worker.rule_plan({'elements':[el(0,type='number',label='How many years of experience do you have with Python?',required=True),el(1,'BUTTON','button',text='Next')]},YEARS_FIELDS,PKG)
        self.assertEqual([(a['action'],a.get('field_key')) for a in plan['actions']],[('fill','years:python'),('click',None)])
    def test_an_unlisted_skill_sends_the_step_to_the_model(self):
        self.assertIsNone(worker.rule_plan({'elements':[el(0,type='number',label='Years of experience with Django?'),el(1,'BUTTON','button',text='Next')]},YEARS_FIELDS,PKG))

class PlanRepairTests(unittest.TestCase):
    def acts(self,plan):return [a['action'] for a in plan['actions']]
    def test_the_way_forward_is_moved_last(self):
        plan=worker.normalize_plan({'actions':[{'action':'click','element_id':1},{'action':'fill','element_id':2,'field_key':'x'},{'action':'choose','element_id':3,'field_key':'y'}]})
        self.assertEqual(self.acts(plan),['fill','choose','click'])
    def test_two_ways_forward_keep_only_the_first(self):
        plan=worker.normalize_plan({'actions':[{'action':'click','element_id':1},{'action':'fill','element_id':2},{'action':'click','element_id':3}]})
        self.assertEqual([(a['action'],a['element_id']) for a in plan['actions']],[('fill',2),('click',1)])
    def test_a_request_for_a_person_wins_over_clicking_on(self):
        plan=worker.normalize_plan({'actions':[{'action':'need_human','reason':'?'},{'action':'fill','element_id':2},{'action':'click','element_id':3}]})
        self.assertEqual(self.acts(plan),['fill','need_human'])
    def test_plans_without_a_terminal_or_malformed_ones_pass_through(self):
        self.assertEqual(worker.normalize_plan({'actions':[{'action':'fill','element_id':1}]}),{'actions':[{'action':'fill','element_id':1}]})
        for odd in ({},{'actions':'x'},None):self.assertEqual(worker.normalize_plan(odd),odd)
    def test_a_repaired_plan_now_validates(self):
        elements=[{'id':1,'tag':'INPUT','type':'text','text':'','label':'Years'},{'id':2,'tag':'BUTTON','type':'button','text':'Next','label':''}]
        bad={'actions':[{'action':'click','element_id':2},{'action':'fill','element_id':1,'field_key':'experience'}]}
        with self.assertRaises(ValueError):worker.validate_batch(bad,{'elements':elements},{'experience':'0'})
        self.assertEqual(len(worker.validate_batch(worker.normalize_plan(bad),{'elements':elements},{'experience':'0'})),2)
    def test_a_finished_upload_is_not_planned_again(self):
        elements=[el(0,type='file',label='Upload resume'),el(1,'BUTTON','button',text='Next')]
        self.assertEqual([a['action'] for a in worker.rule_plan({'elements':elements},FIELDS,PKG)['actions']],['upload_resume','click'])
        self.assertEqual([a['action'] for a in worker.rule_plan({'elements':elements},FIELDS,PKG,{'upload_resume'})['actions']],['click'])

class LateEasyApplyTests(unittest.TestCase):
    """The top card of a job page can render seconds after the page loads; that must not read as 'no Easy Apply'."""
    LATE='''<main><h1>AI Engineer</h1></main><script>
setTimeout(()=>{
  const a=document.createElement('a');a.setAttribute('role','button');a.href='#';a.innerHTML='<span>Easy Apply</span>';
  a.onclick=()=>{const d=document.createElement('div');d.setAttribute('role','dialog');d.className='artdeco-modal jobs-easy-apply-modal';d.innerHTML='<h2>Contact info</h2>';document.body.append(d);return false};
  document.querySelector('main').append(a);
},2500);</script>'''
    def run_page(self,html):
        async def go():
            async with async_playwright() as p:
                browser=await p.chromium.launch();page=await browser.new_page();await page.set_content(html)
                try:return await linkedin.open_easy_apply(page)
                finally:await browser.close()
        return asyncio.run(go())
    def test_a_button_that_renders_late_is_still_found(self):
        self.assertEqual(self.run_page(self.LATE),'opened')
    def test_a_page_that_never_shows_the_button_is_not_easy(self):
        self.assertEqual(self.run_page('<main><h1>AI Engineer</h1><a href="#">Apply</a></main>'),'not_easy')

class OptionPickingTests(unittest.TestCase):
    def test_a_lone_contained_match_is_accepted_and_ambiguity_is_not(self):
        pick=worker.pick_option
        self.assertEqual(pick(['Yes','No'],'yes'),'Yes');self.assertEqual(pick(['Hyderabad, Telangana','Pune'],'Hyderabad'),'Hyderabad, Telangana')
        self.assertEqual(pick(['Greater Hyderabad Area','Pune','Chennai'],'Hyderabad'),'Greater Hyderabad Area')
        self.assertIsNone(pick(['North Hyderabad Area','South Hyderabad Area'],'Hyderabad'),'two candidates: no guess')
        self.assertIsNone(pick(['Pune','Chennai'],'Hyderabad'));self.assertIsNone(pick(['Pune'],''))

class FormPlanningCallTests(unittest.TestCase):
    def test_the_form_planner_runs_without_hidden_reasoning(self):
        """Hidden reasoning made the planner slow (20-30 s a step) and it sometimes ran the reply into its token cap, skipping the job."""
        import inspect
        self.assertIn('reasoning=NO_THINKING',inspect.getsource(worker.fill_form))

class ScreeningFieldTests(unittest.TestCase):
    def test_approved_answers_become_fields_keyed_by_their_question(self):
        text=chr(10).join(['yes','Are you willing to undergo a drug test? Yes',"Have you completed your Bachelor's degree?   No ",'A note with no question mark','Do you have a laptop? '])
        got=worker.screening_fields({'screening':text})
        self.assertEqual(got,{'answer:Are you willing to undergo a drug test?':'Yes',"answer:Have you completed your Bachelor's degree?":'No'})
    def test_nothing_in_nothing_out(self):
        for value in ('',None,'   '):self.assertEqual(worker.screening_fields({'screening':value}),{})
        self.assertEqual(worker.screening_fields({}),{})

class NumericFromTextTests(unittest.TestCase):
    """The safety net that keeps a free-text value like 'Immediately' out of a days-only field."""
    def test_already_numeric_values_pass_through(self):
        self.assertEqual(worker.numeric_from_text('0'),'0');self.assertEqual(worker.numeric_from_text('5.5'),'5.5')
    def test_common_immediate_phrasings_mean_zero_days(self):
        for word in ('Immediately','immediate','ASAP','Now','Right Away'):self.assertEqual(worker.numeric_from_text(word),'0',word)
    def test_a_duration_is_converted_to_days(self):
        self.assertEqual(worker.numeric_from_text('10 days'),'10.0');self.assertEqual(worker.numeric_from_text('2 weeks'),'14.0');self.assertEqual(worker.numeric_from_text('1 month'),'30.0')
    def test_text_with_no_safe_number_is_left_to_a_person(self):
        for value in ('Negotiable','Depends on employer','',None):self.assertIsNone(worker.numeric_from_text(value),value)

class BuildFieldsTests(unittest.TestCase):
    def test_a_free_text_notice_gets_a_numeric_twin_for_days_only_fields(self):
        fields=worker.build_fields({**PROFILE,'notice':'Immediately'},{'cover_letter':'c'})
        self.assertEqual(fields['notice_days'],'0');self.assertEqual(fields['notice'],'Immediately')
    def test_an_unparseable_notice_gets_no_numeric_twin(self):
        fields=worker.build_fields({**PROFILE,'notice':'Negotiable'},{'cover_letter':'c'})
        self.assertNotIn('notice_days',fields)
    def test_truthful_location_match_answers_are_always_available(self):
        fields=worker.build_fields(PROFILE,{'cover_letter':'c'})
        self.assertEqual((fields['location_match:yes'],fields['location_match:no']),('Yes','No'))

NUMBER_FORM='''<!DOCTYPE html><html><body>
<div id="one"><h1>Application</h1><label>How soon can you join? (days)<input name="notice" type="number" required></label>
<button type="submit" id="go">Submit application</button></div>
<h2 id="done" hidden>Thank you for applying</h2>
<script>
document.getElementById('one').addEventListener('click',e=>{const b=e.target.closest('[type=submit]');if(b){
  if(!document.querySelector('[name=notice]').checkValidity())return;
  one.hidden=true;done.hidden=false;
}});
</script></body></html>'''

class NumericFieldExecutionTests(Db):
    """The executor itself corrects a text value for a number-only control, whichever field key was chosen."""
    def run_form(self,notice,field_key):
        profile={**PROFILE,'notice':notice};package={'resume':PROFILE['resume_text'],'cover_letter':'c','notes':[],'answers':{}}
        fields=worker.build_fields(profile,package)
        with self.Session() as db:
            for model in (AgentRun,Application,Job,User):db.query(model).delete()
            db.add(User(id='u',email='n@example.invalid',password='x',profile=profile,settings=SETTINGS));db.flush()
            db.add(Job(id='j',user_id='u',canonical='c',payload={'title':'t','company':'c'}));db.flush()
            db.add(Application(id='a',user_id='u',job_id='j',status='running',package=package,approved_hash=fingerprint(package),events=[],browser={}));db.commit()
        async def model(system,payload,max_tokens=0,**_):
            els=payload['page']['elements']
            field=next(e for e in els if e['type']=='number');submit=next(e for e in els if e['type']=='submit')
            return {'actions':[{'action':'fill','element_id':field['id'],'field_key':field_key},{'action':'submit','element_id':submit['id']}]}
        async def go():
            async with async_playwright() as p:
                browser=await p.chromium.launch();page=await browser.new_page();await page.set_content(NUMBER_FORM)
                with patch.object(worker,'Session',self.Session),patch.object(worker,'llm',model),patch.object(worker,'allowed_application_url',lambda u,s=None:True):
                    await worker.fill_form('a',page,None,None,fields,package,{'title':'t','company':'c'},profile,{'navigated':True},False)
                await browser.close()
        asyncio.run(go())
        with self.Session() as db:return db.get(Application,'a')
    def test_a_free_text_answer_is_converted_before_it_reaches_a_number_field(self):
        a=self.run_form('Immediately','notice')   # the model used the text field, not notice_days
        self.assertEqual(a.status,'submitted',[e['text'] for e in a.events])
    def test_an_unconvertible_answer_asks_a_person_instead_of_typing_garbage(self):
        a=self.run_form('Negotiable','notice')
        self.assertEqual(a.status,'needs_input',[e['text'] for e in a.events])
        self.assertIn('is not a number',a.events[-1]['text'])

class KeyRepairTests(unittest.TestCase):
    F={'answer:Are you comfortable working on-site and commuting to the job location?':'Yes','answer:Are you willing to undergo a drug test?':'Yes',
       'answer:Are you willing to undergo a background check?':'Yes','answer:Are you willing to work night or rotational shifts?':'No','experience':'0'}
    def test_a_paraphrased_question_maps_to_the_approved_answer_it_means(self):
        near=worker.closest_answer_key
        self.assertEqual(near('answer:Are you comfortable working in an onsite setting?',self.F),'answer:Are you comfortable working on-site and commuting to the job location?')
        self.assertEqual(near('answer:Are you willing to take a drug test?',self.F),'answer:Are you willing to undergo a drug test?')
        self.assertEqual(near('answer:Can you work night shifts?',self.F),'answer:Are you willing to work night or rotational shifts?')
    def test_different_or_unrelated_questions_are_never_mapped(self):
        near=worker.closest_answer_key
        for question in ('answer:Do you like dogs?','answer:Are you willing to undergo screening?','answer:Do you have a criminal record?','answer:x','not-an-answer-key','answer:'):
            self.assertIsNone(near(question,self.F),question)
        self.assertIsNone(near('answer:Are you willing to take a test?',{'answer:Are you willing to undergo a drug test?':'Yes','answer:Are you willing to undergo a background test?':'Yes'}),'two candidates: no guess')
    def test_the_plan_is_repaired_and_valid_keys_are_left_alone(self):
        plan={'actions':[{'action':'choose','element_id':1,'field_key':'answer:Are you willing to take a drug test?'},{'action':'fill','element_id':2,'field_key':'experience'},{'action':'fill','element_id':3,'field_key':'answer:Do you like dogs?'},{'action':'click','element_id':4}]}
        fixed=worker.repair_keys(plan,self.F)['actions']
        self.assertEqual([a.get('field_key') for a in fixed],['answer:Are you willing to undergo a drug test?','experience','answer:Do you like dogs?',None])
        for odd in ({},{'actions':'x'},None):self.assertEqual(worker.repair_keys(odd,self.F),odd)

class VerbRepairTests(unittest.TestCase):
    def test_the_wrong_verb_for_a_control_is_corrected_not_abandoned(self):
        elements=[{'id':1,'tag':'SELECT','type':'select-one','label':'Built a full-stack app?','text':'','filled':0,'required':1},
                  {'id':2,'tag':'INPUT','type':'radio','label':'Yes','text':'','filled':0,'required':1},
                  {'id':3,'tag':'INPUT','type':'text','label':'Years','text':'','filled':0,'required':1}]
        fields={'answer:full stack':'Yes','experience':'0'}
        plan={'actions':[{'action':'choose','element_id':1,'field_key':'answer:full stack'},{'action':'select','element_id':2,'field_key':'answer:full stack'},{'action':'fill','element_id':3,'field_key':'experience'}]}
        fixed=worker.repair_verbs(plan,{'elements':elements})
        self.assertEqual([a['action'] for a in fixed['actions']],['select','choose','fill'])
        self.assertEqual(len(worker.validate_batch(fixed,{'elements':elements},fields)),3)
        with self.assertRaises(ValueError):worker.validate_batch(plan,{'elements':elements},fields)
    def test_odd_plans_pass_through(self):
        for odd in ({},{'actions':'x'},None):self.assertEqual(worker.repair_verbs(odd,{'elements':[]}),odd)
        self.assertEqual(worker.repair_verbs({'actions':[{'action':'need_human'},{'action':'fill','element_id':99}]},{'elements':[]})['actions'][1]['element_id'],99)

class RepairInAction(Db):
    def apply(self,html,model):
        from .test_linkedin import WorkerOnLinkedInTests
        return WorkerOnLinkedInTests.apply(self,html,model)
    def test_a_misordered_model_plan_is_repaired_not_skipped(self):
        def misordered(seen):
            base=linkedin_model(seen)
            async def plan(system,payload,max_tokens=0,**_):
                p=await base(system,payload,max_tokens);return {'actions':list(reversed(p['actions']))}
            return plan
        a,_,_=self.apply(JOB_SHADOW,misordered)
        self.assertEqual(a.status,'submitted',[e['text'] for e in a.events])
    def test_the_same_document_is_never_uploaded_twice(self):
        from .test_worker import UPLOAD_FORM,WorkerFlowTests
        def eager(seen):
            async def plan(system,payload,max_tokens=0,**_):
                els=payload['page']['elements'];seen.append(1)
                ready=[e for e in els if 'continue' in e['text'].lower()]
                upload=next(e['id'] for e in els if e['type']=='file')
                if ready:return {'actions':[{'action':'upload_resume','element_id':upload,'reason':'UPLOAD'},{'action':'click','element_id':ready[0]['id'],'reason':'go'}]}
                if 'step 1 of 2' in payload['page']['text'].lower():return {'actions':[{'action':'upload_resume','element_id':upload,'reason':'UPLOAD'}]}
                return {'actions':[{'action':'submit','element_id':next(e['id'] for e in els if 'submit application' in e['text'].lower()),'reason':'send'}]}
            return plan
        a,_=WorkerFlowTests.apply(self,UPLOAD_FORM,model=eager)
        self.assertEqual(a.status,'submitted',[e['text'] for e in a.events])
        self.assertEqual(sum(e['text']=='UPLOAD' for e in a.events),1,'the second upload request must be dropped')
    def test_each_steps_layout_is_recorded_without_personal_values(self):
        a,_,_=self.apply(JOB_SHADOW,linkedin_model)
        steps=a.browser.get('steps');self.assertTrue(steps and all(steps))
        flat=json.dumps(steps);self.assertNotIn('90000',flat);self.assertNotIn('Alex',flat)
        self.assertTrue(any('years of experience' in row[3].lower() for step in steps for row in step))

YEARS_PAGE='''<!DOCTYPE html><html><body>
<main><h1>Backend Intern</h1><a id="easy" role="button" href="/apply" onclick="return false"><span>Easy Apply</span></a></main>
<div id="modal" role="dialog" class="artdeco-modal jobs-easy-apply-modal" hidden>
 <div id="s1"><h2>Additional questions</h2>
  <label for="py">How many years of experience do you have with Python?</label><input id="py" type="number" required>
  <label for="dj">How many years of experience do you have with Django?</label><input id="dj" type="number" required>
  <button type="button" id="next">Next</button></div>
 <div id="s2" hidden><h2>Review your application</h2><button type="button" id="submit">Submit application</button></div>
 <div id="sent" hidden><h2 id="sent-h">Application sent</h2></div>
</div>
<script>
const $=id=>document.getElementById(id);
$('easy').addEventListener('click',()=>{$('modal').hidden=false});
$('next').onclick=()=>{$('s1').hidden=true;$('s2').hidden=false};
$('submit').onclick=()=>{$('sent-h').textContent='Application sent - python='+$('py').value+' django='+$('dj').value;$('s2').hidden=true;$('sent').hidden=false};
</script></body></html>'''

class SkillYearsInAction(Db):
    def apply(self,html,model,skill_years):
        from .test_linkedin import WorkerOnLinkedInTests
        return WorkerOnLinkedInTests.apply(self,html,model,profile={**PROFILE,'skill_years':skill_years})
    def test_listed_skills_are_answered_from_the_profile_with_no_model_call(self):
        a,_,_=self.apply(YEARS_PAGE,never_ask,{'Python':1,'Django':0})
        self.assertEqual(a.status,'submitted',[e['text'] for e in a.events])
        self.assertTrue(any('python=1 django=0' in e['text'] for e in a.events),[e['text'] for e in a.events])
    def test_an_unlisted_skill_is_skipped_and_never_guessed(self):
        asked=[]
        def careful(seen):
            async def plan(system,payload,max_tokens=0,**_):
                asked.append([f for f in payload['approved_fields'] if f.startswith('years:')])
                return {'actions':[{'action':'need_human','reason':'No approved answer for years of experience with Django'}]}
            return plan
        a,_,_=self.apply(YEARS_PAGE,careful,{'Python':1})
        self.assertEqual(a.status,'stopped');self.assertIn('Django',a.events[-1]['text']);self.assertEqual(asked,[['years:python']],'the model sees only what the person entered')

STALL_PAGE='''<!DOCTYPE html><html><body>
<main><h1>Backend Intern</h1><a id="easy" role="button" href="/apply" onclick="return false"><span>Easy Apply</span></a></main>
<div id="modal" role="dialog" class="artdeco-modal jobs-easy-apply-modal" hidden>
 <div id="s1"><h2>Additional questions</h2>
  <label for="loc">Current Location Pune?</label><select id="loc" required><option>Select an option</option><option>Yes</option><option>No</option></select>
  <button type="button" id="next">Next</button></div>
 <div id="s2" hidden><h2>Review your application</h2><button type="button" id="submit">Submit application</button></div>
</div>
<script>
const $=id=>document.getElementById(id);
$('easy').addEventListener('click',()=>{$('modal').hidden=false});
$('next').onclick=()=>{if($('loc').value==='Select an option')return;$('s1').hidden=true;$('s2').hidden=false};
</script></body></html>'''

class StalledFormTests(Db):
    def test_a_placeholder_option_is_not_a_filled_select(self):
        async def go():
            async with async_playwright() as p:
                browser=await p.chromium.launch();page=await browser.new_page();await page.set_content(STALL_PAGE)
                await page.evaluate("document.getElementById('modal').hidden=false")
                before=await page.evaluate(worker.SNAPSHOT_JS,'.jobs-easy-apply-modal')
                await page.select_option('#loc','Yes')
                after=await page.evaluate(worker.SNAPSHOT_JS,'.jobs-easy-apply-modal')
                await browser.close()
                pick=lambda snap:next(e for e in snap['elements'] if e['tag']=='SELECT')
                return pick(before)['filled'],pick(after)['filled']
        self.assertEqual(asyncio.run(go()),(False,True))
    def test_the_rules_leave_an_unanswered_select_to_the_model(self):
        plan=worker.rule_plan({'elements':[el(0,'SELECT','select-one',label='Current Location Pune?',filled=False,required=True),el(1,'BUTTON','button',text='Next')]},FIELDS,PKG)
        self.assertIsNone(plan)
    def test_a_form_that_will_not_advance_is_abandoned_after_a_few_tries(self):
        def stubborn(seen):
            async def plan(system,payload,max_tokens=0,**_):
                page=payload['page'];seen.append(1)
                return {'actions':[{'action':'click','element_id':next(e['id'] for e in page['elements'] if e['text']=='Next')}]}
            return plan
        seen_calls=[]
        from .test_linkedin import WorkerOnLinkedInTests
        a,_,_=WorkerOnLinkedInTests.apply(self,STALL_PAGE,stubborn,profile=PROFILE)
        texts=[e['text'] for e in a.events]
        self.assertEqual(a.status,'stopped',texts);self.assertIn('did not move on',a.events[-1]['text']);self.assertTrue(a.events[-1]['text'].startswith('Skipped: this form could not be completed'))
        self.assertLess(sum(t.startswith('Planned') for t in texts),8,'it stopped early instead of using every step')

class RetryTests(Db):
    def make(self,status='stopped',last='Skipped: this form could not be completed (TimeoutError).',retries=0):
        with self.Session() as db:
            for model in (AgentRun,Application,Job,User):db.query(model).delete()
            db.add(User(id='u',email='r@example.invalid',password='x',profile=PROFILE,settings=SETTINGS));db.flush()
            db.add(Job(id='j',user_id='u',canonical='c',payload={'title':'t','company':'c'}));db.flush()
            db.add(Application(id='a',user_id='u',job_id='j',status=status,package={},events=[{'time':now().isoformat(),'text':last}],browser={'retries':retries,'started_day':'x'}));db.commit()
    def requeue(self):
        with patch.object(platform_agent,'Session',self.Session):
            result=platform_agent.requeue_technical_skip('u','j',{'session_id':'s2','connect_url':'c2'})
        with self.Session() as db:a=db.get(Application,'a');return result,a.status,a.browser,a.events[-1]['text']
    def test_a_technical_skip_is_requeued_on_the_current_session(self):
        self.make();result,status,browser,last=self.requeue()
        self.assertEqual((result,status),('a','prepared'));self.assertEqual((browser['retries'],browser['session_id'],browser['shared'],browser['navigated']),(1,'s2',True,False))
        self.assertIn('attempt 2 of 3',last)
    def test_the_other_technical_skip_wording_is_also_retried(self):
        self.make(last='Skipped: the form asks for something the agent must not do (Terminal action must be last).');self.assertEqual(self.requeue()[0],'a')
    def test_retries_are_capped(self):
        self.make(retries=2);self.assertEqual(self.requeue()[:2],(None,'stopped'))
    def test_real_reasons_are_never_retried(self):
        for last in ('Skipped: already applied on LinkedIn.','Skipped: Easy Apply is not available for this job.','Skipped: a required answer is missing from your confirmed details.','Application stopped.'):
            with self.subTest(last):self.make(last=last);self.assertEqual(self.requeue()[:2],(None,'stopped'))
    def test_only_stopped_applications_are_requeued(self):
        for status in ('submitted','running','needs_input','prepared'):
            with self.subTest(status):self.make(status=status);self.assertIsNone(self.requeue()[0])

class JevInAgentTests(Db):
    """execute_platform end to end with Jev in each mode; job 1 is a real match according to the DeepSeek stub."""
    def run_agent(self,mode,decide):
        with self.Session() as db:
            db.add(User(id='u',email='j@example.invalid',password='x',profile=PROFILE,settings=SETTINGS));db.flush()
            db.add(AgentRun(id='r',user_id='u',status='running',phase='searching',events=[],state={'profile_hash':fingerprint(PROFILE)}));db.commit()
        pages=[('/feed/','<main><h1>Feed</h1></main>'),('/jobs/search/',SEARCH),('/jobs/view/111111111',JOB_SHADOW),('/jobs/view/222222222',EXTERNAL_JOB)]
        contexts=[];assessed=[];decided=[]
        async def released(_):return None
        async def assess(system,payload,max_tokens=0,**_):assessed.append(1);return assessment()
        async def package(profile,job,demo=False,**_):return {'resume':PROFILE['resume_text'],'cover_letter':'c','notes':[],'answers':{}}
        async def session(user_id,proxies=False):return {'id':'s','connectUrl':'local','live_url':'https://live.example/x'}
        async def quick_collect(page):
            await page.wait_for_timeout(300);return [linkedin.job_url(i) for i in await page.evaluate(linkedin.COLLECT_JS)]
        async def fake_decide(state,questions,**kw):
            decided.append(state);return decide()
        patches=[patch.dict(os.environ,{'OPENROUTER_API_KEY':'t','BROWSERBASE_API_KEY':'t','JEV_MODE':mode}),patch.object(platform_agent,'random',SimpleNamespace(uniform=lambda a,b:0.01)),
                 patch.object(linkedin,'collect_job_urls',quick_collect),patch.object(linkedin,'search_urls',lambda profile,roles=None,country_only=False,any_location=False:['https://www.linkedin.com/jobs/search/?keywords=ai']),patch.object(platform_agent,'async_playwright',partial(linkedin_site,pages,contexts)),patch.object(worker,'async_playwright',partial(linkedin_site,pages,contexts)),
                 patch.object(platform_agent,'llm',assess),patch.object(platform_agent,'generate_package',package),patch.object(platform_agent,'user_browser_session',session),
                 patch.object(platform_agent,'release_browser',released),patch.object(worker,'release_browser',released),patch.object(worker,'llm',linkedin_model([])),
                 patch('backend.career_ops_documents.pdf_bytes',fake_pdf),patch.object(jev,'decide',fake_decide)]
        patches+=[patch.object(m,'Session',self.Session) for m in (agent,platform_agent,main,worker)]
        with contextlib.ExitStack() as stack:
            for p in patches:stack.enter_context(p)
            asyncio.run(asyncio.wait_for(platform_agent.execute_platform('r','LinkedIn'),timeout=120))
        with self.Session() as db:
            run=db.get(AgentRun,'r');return run,[a.status for a in db.query(Application).all()],len(assessed),len(decided),[e['text'] for e in run.events]
    def test_shadow_mode_logs_but_never_acts(self):
        run,apps,assessed,decided,texts=self.run_agent('shadow',lambda:answers(choice='four_plus_years'))
        self.assertEqual(apps,['submitted'],texts);self.assertEqual((assessed,decided),(1,1))
        self.assertEqual(run.state['jev'],{'compared':1,'missed_match':1})
        self.assertTrue(any('Jev check: it would have skipped a job DeepSeek matched' in t for t in texts),texts)
    def test_shadow_mode_counts_agreement(self):
        run,apps,_,_,_=self.run_agent('shadow',lambda:answers())
        self.assertEqual(apps,['submitted']);self.assertEqual(run.state['jev'],{'compared':1,'agree_review':1})
    def test_active_mode_skips_confident_rejects_without_a_deepseek_call(self):
        run,apps,assessed,decided,texts=self.run_agent('active',lambda:answers(choice='four_plus_years'))
        self.assertEqual((apps,assessed,decided),([],0,1),texts)
        self.assertTrue(any('Skipped by Jev triage' in t for t in texts),texts);self.assertEqual(run.state['jev']['skipped'],1)
    def test_active_mode_still_reviews_what_jev_passes_or_doubts(self):
        for name,make in (('passes',lambda:answers()),('doubts',lambda:answers(choice='four_plus_years',confidence=0.5))):
            with self.subTest(name):
                self.reset();_,apps,assessed,_,texts=self.run_agent('active',make);self.assertEqual((apps,assessed),(['submitted'],1),texts)
    def test_a_jev_outage_falls_back_to_deepseek_and_says_so_once(self):
        def down():raise jev.JevUnavailable('HTTP 520')
        run,apps,assessed,_,texts=self.run_agent('active',down)
        self.assertEqual((apps,assessed),(['submitted'],1),texts);self.assertEqual(sum('Jev triage unavailable' in t for t in texts),1)
        self.assertNotIn('jev',run.state)
    def test_off_never_calls_jev(self):
        _,apps,assessed,decided,_=self.run_agent('off',lambda:answers());self.assertEqual((apps,assessed,decided),(['submitted'],1,0))
    def reset(self):
        with self.Session() as db:
            for model in (AgentRun,Application,Job,User):db.query(model).delete()
            db.commit()


def quick_only():
    """What the short fit call returns: the verdict without the evidence report."""
    return {k:v for k,v in assessment().items() if k not in ('evaluation','global_score')}
REPORT_ONLY={k:v for k,v in assessment().items() if k in ('evaluation','global_score')}

class TwoStageReviewTests(Db):
    """Short fit call for every job; the long evidence report only for a job that matches; a free years check before any model."""
    def run_agent(self,job_html,model,mode='off',search=SEARCH,unanswerable=False,second_job=EXTERNAL_JOB,seed=None):
        with self.Session() as db:
            db.add(User(id='u',email='t@example.invalid',password='x',profile=PROFILE,settings=SETTINGS));db.flush()
            db.add(AgentRun(id='r',user_id='u',status='running',phase='searching',events=[],state={'profile_hash':fingerprint(PROFILE)}));db.flush()
            if seed:seed(db)
            db.commit()
        pages=[('/feed/','<main><h1>Feed</h1></main>'),('/jobs/search/',search),('/jobs/view/111111111',job_html),('/jobs/view/222222222',second_job)]
        contexts=[];calls=[]
        async def released(_):return None
        async def llm(system,payload,max_tokens=0,**_):
            kind='report' if '"evaluation" (OBJECT)' in system else 'quick';calls.append((kind,max_tokens,payload));return model(kind,len(calls))
        async def package(profile,job,demo=False,**_):return {'resume':PROFILE['resume_text'],'cover_letter':'c','notes':[],'answers':{}}
        async def session(user_id,proxies=False):return {'id':'s','connectUrl':'local','live_url':'https://live.example/x'}
        async def quick_collect(page):
            await page.wait_for_timeout(300);return [linkedin.job_url(i) for i in await page.evaluate(linkedin.COLLECT_JS)]
        patches=[patch.dict(os.environ,{'OPENROUTER_API_KEY':'t','BROWSERBASE_API_KEY':'t','JEV_MODE':mode}),patch.object(platform_agent,'random',SimpleNamespace(uniform=lambda a,b:0.01)),
                 patch.object(linkedin,'collect_job_urls',quick_collect),patch.object(linkedin,'search_urls',lambda profile,roles=None,country_only=False,any_location=False:['https://www.linkedin.com/jobs/search/?keywords=ai']),
                 patch.object(platform_agent,'async_playwright',partial(linkedin_site,pages,contexts)),patch.object(worker,'async_playwright',partial(linkedin_site,pages,contexts)),
                 patch.object(platform_agent,'llm',llm),patch.object(platform_agent,'generate_package',package),patch.object(platform_agent,'user_browser_session',session),
                 patch.object(platform_agent,'release_browser',released),patch.object(worker,'release_browser',released),patch.object(worker,'llm',linkedin_model([],unanswerable)),
                 patch('backend.career_ops_documents.pdf_bytes',fake_pdf)]
        patches+=[patch.object(m,'Session',self.Session) for m in (agent,platform_agent,main,worker)]
        with contextlib.ExitStack() as stack:
            for p in patches:stack.enter_context(p)
            asyncio.run(asyncio.wait_for(platform_agent.execute_platform('r','LinkedIn'),timeout=120))
        with self.Session() as db:
            run=db.get(AgentRun,'r');return run,[a.status for a in db.query(Application).all()],db.query(Job).all(),calls,[e['text'] for e in run.events]
    def test_a_match_costs_one_short_call_then_one_report_call(self):
        run,apps,jobs,calls,texts=self.run_agent(JOB_SHADOW,lambda kind,n:quick_only() if kind=='quick' else REPORT_ONLY)
        self.assertEqual([c[0] for c in calls],['quick','report'],texts);self.assertEqual(apps,['submitted'],texts)
        self.assertLessEqual(calls[0][1],2500);self.assertNotIn('confirmed_evidence',calls[0][2],'the short call does not carry the evidence catalog')
        self.assertIn('confirmed_evidence',calls[1][2]);self.assertIn('evaluation',jobs[0].payload['match']);self.assertTrue(jobs[0].payload['description'])
    def test_a_poor_fit_never_pays_for_the_report(self):
        run,apps,jobs,calls,texts=self.run_agent(JOB_SHADOW,lambda kind,n:{**quick_only(),'score':5})
        self.assertEqual([c[0] for c in calls],['quick'],texts);self.assertEqual(apps,[]);self.assertNotIn('evaluation',jobs[0].payload['match'])
        self.assertFalse(jobs[0].payload['match']['matched'])
    def test_a_report_missing_once_is_asked_for_again(self):
        run,apps,jobs,calls,texts=self.run_agent(JOB_SHADOW,lambda kind,n:quick_only() if kind=='quick' else ({'note':'no report'} if n==2 else REPORT_ONLY))
        self.assertEqual([c[0] for c in calls],['quick','report','report'],texts);self.assertEqual(apps,['submitted'],texts)
    def test_a_report_that_never_arrives_leaves_the_job_for_the_next_run(self):
        run,apps,jobs,calls,texts=self.run_agent(JOB_SHADOW,lambda kind,n:quick_only() if kind=='quick' else {'note':'no report'})
        self.assertEqual((apps,jobs),([],[]),texts);self.assertTrue(any('omitted the required Career Ops report' in t for t in texts),texts)
    def test_a_posting_that_asks_for_years_is_dropped_before_any_model_call(self):
        senior=JOB_SHADOW.replace('Fresher friendly.','About the job Requires 3+ years of professional experience in Python.')
        decided=[]
        async def fake_decide(*a,**k):decided.append(1);return answers()
        with patch.object(jev,'decide',fake_decide):
            run,apps,jobs,calls,texts=self.run_agent(senior,lambda kind,n:quick_only(),mode='active')
        self.assertEqual((calls,decided,apps,jobs),([],[],[],[]),texts)
        self.assertTrue(any('asks for 3+ years' in t for t in texts),texts);self.assertEqual(run.state['prefiltered'],1)
    def test_a_question_the_agent_could_not_answer_is_listed_for_the_person(self):
        run,apps,jobs,calls,texts=self.run_agent(JOB_SHADOW,lambda kind,n:quick_only() if kind=='quick' else REPORT_ONLY,unanswerable=True)
        self.assertEqual(apps,['stopped'],texts);self.assertEqual(run.state['needed'],[{'question':'a portfolio link','job':'AI Engineer'}])
        self.assertTrue(any(t=='Needs your answer: a portfolio link.' for t in texts),texts)
    @staticmethod
    def two_different_jobs(kind,n):
        """The second posting is a different vacancy (another title), not a repost of the first."""
        return REPORT_ONLY if kind=='report' else {**quick_only(),**({'title':'Machine Learning Engineer'} if n>=3 else {})}
    def test_every_candidate_is_reviewed_before_the_best_ones_are_applied_to(self):
        """The agent ranks all matches first, then works through them best-first; applying never interleaves with reviewing."""
        run,apps,jobs,calls,texts=self.run_agent(JOB_SHADOW,self.two_different_jobs,second_job=JOB_SHADOW)
        self.assertEqual(apps,['submitted','submitted'],texts)
        reviews=[i for i,t in enumerate(texts) if t.startswith('Checking resume/JD fit')];results=[i for i,t in enumerate(texts) if t.startswith('Application result')]
        applying=[i for i,t in enumerate(texts) if t.startswith('Applying on LinkedIn')]
        self.assertEqual((len(reviews),len(results)),(2,2),texts)
        self.assertLess(max(reviews),min(applying),'applications started before every candidate was reviewed and ranked: '+repr(texts))
        self.assertTrue(any(t.startswith('Ranked 2 matches best-first') for t in texts),texts)
        self.assertLess(results[0],results[1]);self.assertEqual(texts[-1].startswith('Run complete'),True,texts)
    def test_only_one_application_runs_at_a_time(self):
        run,apps,jobs,calls,texts=self.run_agent(JOB_SHADOW,self.two_different_jobs,second_job=JOB_SHADOW)
        applying=[i for i,t in enumerate(texts) if t.startswith('Applying on LinkedIn')];results=[i for i,t in enumerate(texts) if t.startswith('Application result')]
        self.assertEqual(len(applying),2);self.assertLess(results[0],applying[1],'the second application started only after the first finished: '+repr(texts))
    def test_a_run_stops_cleanly_when_it_reaches_its_model_budget(self):
        from . import services
        services.SPEND.clear();services.SPEND['r']={'usd':1.5,'calls':40}
        self.addCleanup(services.SPEND.clear)   # other tests reuse the run id 'r'
        with patch.dict(os.environ,{'RUN_BUDGET_USD':'1.0'}):
            run,apps,jobs,calls,texts=self.run_agent(JOB_SHADOW,lambda kind,n:quick_only() if kind=='quick' else REPORT_ONLY)
        self.assertEqual((run.status,calls,apps),('completed',[],[]),texts);self.assertTrue(any('spent $1.50 on models' in t and 'RUN_BUDGET_USD' in t for t in texts),texts)
    def test_a_posting_rejected_on_an_earlier_run_is_not_opened_again(self):
        job1='https://www.linkedin.com/jobs/view/111111111/'
        def seed(db):db.add(SkippedJob(id='s1',user_id='u',canonical=job1,reason='the posting asks for 3+ years',profile_hash=fingerprint(PROFILE)))
        run,apps,jobs,calls,texts=self.run_agent(JOB_SHADOW,lambda kind,n:quick_only(),seed=seed)
        self.assertEqual((calls,apps),([],[]),texts)
        self.assertTrue(any('Already reviewed earlier' in t and '111111111' in t and '3+ years' in t for t in texts),texts)
    def test_a_rejection_tied_to_an_old_profile_is_reconsidered(self):
        job1='https://www.linkedin.com/jobs/view/111111111/'
        def seed(db):db.add(SkippedJob(id='s1',user_id='u',canonical=job1,reason='the posting asks for 3+ years',profile_hash='an-older-profile'))
        run,apps,jobs,calls,texts=self.run_agent(JOB_SHADOW,lambda kind,n:quick_only() if kind=='quick' else REPORT_ONLY,seed=seed)
        self.assertEqual(apps,['submitted'],texts)
    def test_new_rejections_are_remembered_for_the_next_run(self):
        senior=JOB_SHADOW.replace('Fresher friendly.','About the job Requires 3+ years of professional experience in Python.')
        run,apps,jobs,calls,texts=self.run_agent(senior,lambda kind,n:quick_only())
        with self.Session() as db:rows=[(r.canonical,r.profile_hash is not None,r.reason) for r in db.query(SkippedJob)]
        self.assertEqual(len(rows),2,rows)   # the senior posting, and the employer-site one
        by={c:(h,r) for c,h,r in rows}
        self.assertEqual(by['https://www.linkedin.com/jobs/view/111111111/'][0],True);self.assertIn('3+ years',by['https://www.linkedin.com/jobs/view/111111111/'][1])
        self.assertEqual(by['https://www.linkedin.com/jobs/view/222222222/'][0],False,'a page-state rejection does not depend on the profile')
    def test_a_senior_title_on_the_results_list_is_skipped_without_opening_the_page(self):
        cards=('<ul><li data-occludable-job-id="111111111"><a href="/jobs/view/111111111/" aria-label="AI Engineer with verification">AI Engineer AI Engineer</a></li>'
               '<li data-occludable-job-id="222222222"><a href="/jobs/view/222222222/">Senior Software Engineer<br>Senior Software Engineer</a></li></ul>')
        opened=[]
        run,apps,jobs,calls,texts=self.run_agent(JOB_SHADOW,lambda kind,n:quick_only() if kind=='quick' else REPORT_ONLY,search=cards)
        self.assertEqual(run.state['titles'],{'https://www.linkedin.com/jobs/view/111111111/':'AI Engineer','https://www.linkedin.com/jobs/view/222222222/':'Senior Software Engineer'})
        self.assertTrue(any(t.startswith('Skipped from the results list') and 'Senior Software Engineer' in t for t in texts),texts)
        self.assertEqual(apps,['submitted'],texts);self.assertEqual(run.state['prefiltered'],1)
    def test_cards_without_a_readable_title_are_left_for_the_page_check(self):
        run,apps,jobs,calls,texts=self.run_agent(JOB_SHADOW,lambda kind,n:quick_only() if kind=='quick' else REPORT_ONLY)
        self.assertEqual(run.state['titles'],{});self.assertEqual(apps,['submitted'],texts)
    def test_the_short_prompt_has_no_description_or_report_fields(self):
        self.assertNotIn('description',platform_agent.QUICK);self.assertNotIn('evaluation',platform_agent.QUICK);self.assertIn('score',platform_agent.QUICK)

class NeededAnswerTests(RetryTests):
    def requeue_with(self,profile_hash):
        with patch.object(platform_agent,'Session',self.Session):
            result=platform_agent.requeue_retryable('u','j',{'session_id':'s2','connect_url':'c2'},profile_hash)
        with self.Session() as db:a=db.get(Application,'a');return result,a.status,a.browser,a.events[-1]['text']
    def test_the_question_is_picked_out_of_the_skip_reason(self):
        n=platform_agent.needed_answer
        self.assertEqual(n('Skipped: Missing approved answer for years of Python experience'),'years of Python experience')
        self.assertEqual(n('Skipped: No approved answer for required drug test question'),'required drug test question')
        self.assertEqual(n('Skipped: Asks for a portfolio link the profile does not have.'),'a portfolio link')
        self.assertEqual(n("Skipped: Question: Have you completed Bachelor's Degree? No approved answer."),"Have you completed Bachelor's Degree?")
        self.assertEqual(n('Skipped: No approved years for backend API integration experience'),'backend API integration experience')
        self.assertEqual(n("Skipped: the form asks for something the agent must not do (Unapproved field value: years:python/django and react.js for 'how much hands-on experience do you have')."),'python/django and react.js')
        for other in ('Skipped: already applied on LinkedIn.','Skipped: this form could not be completed (X).','Application submitted','',None):self.assertIsNone(n(other),other)
    def test_each_question_is_listed_once(self):
        state=platform_agent.record_needed({},'Drug test?','Job A');state=platform_agent.record_needed(state,'drug test?','Job B');state=platform_agent.record_needed(state,'Years of Python','Job B')
        self.assertEqual([i['question'] for i in state['needed']],['Drug test?','Years of Python'])
    def test_a_skip_for_a_missing_answer_is_retried_once_the_profile_has_changed(self):
        self.make(last='Skipped: Missing approved answer for years of Python experience');
        with self.Session() as db:
            a=db.get(Application,'a');a.browser={**a.browser,'profile_hash':'old'};db.commit()
        self.assertEqual(self.requeue_with('old')[:2],(None,'stopped'),'same profile: the answer is still missing')
        result,status,browser,last=self.requeue_with('new')
        self.assertEqual((result,status,browser['retries'],browser['profile_hash']),('a','prepared',1,'new'));self.assertIn('updated answers',last)
    def test_a_verdict_lost_to_a_profile_save_is_restored_for_the_retry(self):
        self.make(last='Skipped: Missing approved answer for years of Python experience')
        with self.Session() as db:
            a=db.get(Application,'a');a.browser={**a.browser,'profile_hash':'old'}
            j=db.get(Job,'j');j.payload={**j.payload,'match':{'score':25,'matched':False,'eligible':False,'blockers':['Country eligibility'],'unknown':['x']}};db.commit()
        self.assertEqual(self.requeue_with('new')[0],'a')
        with self.Session() as db:m=db.get(Job,'j').payload['match']
        self.assertEqual((m['matched'],m['eligible'],m['blockers'],m['unknown'],m['restored']),(True,True,[],[],True))
    def test_the_backlog_pass_requeues_only_skips_worth_retrying_and_no_more_than_the_limit(self):
        self.make(last='Skipped: this form could not be completed (X).')
        with self.Session() as db:
            for n in range(3):
                job=Job(id=f'j{n}',user_id='u',canonical=f'c{n}',payload={'title':f't{n}','company':'co'});db.add(job);db.flush()
                last=['Skipped: already applied on LinkedIn.','Skipped: the form asks for something the agent must not do (Terminal action must be last).','Skipped: this form could not be completed (Y).'][n]
                db.add(Application(id=f'a{n}',user_id='u',job_id=job.id,status='stopped',package={},events=[{'time':now().isoformat(),'text':last}],browser={}))
            db.commit()
        with patch.object(platform_agent,'Session',self.Session):
            found=platform_agent.retry_backlog('u',{'session_id':'s'},'h',limit=2)
        self.assertEqual(len(found),2);self.assertTrue(all(len(item)==4 for item in found))
        self.assertNotIn('a0',[f[0] for f in found],'a job that was already applied to is never retried')
        with patch.object(platform_agent,'Session',self.Session):self.assertEqual(len(platform_agent.retry_backlog('u',{},'h',limit=6)),1,'the remaining one, later')
    def test_other_skips_and_unrecorded_profiles_are_never_retried(self):
        self.make(last='Skipped: already applied on LinkedIn.')
        with self.Session() as db:
            a=db.get(Application,'a');a.browser={**a.browser,'profile_hash':'old'};db.commit()
        self.assertIsNone(self.requeue_with('new')[0])
        self.make(last='Skipped: Missing approved answer for years of Python experience');self.assertIsNone(self.requeue_with('new')[0],'no recorded profile to compare with')

if __name__=='__main__':unittest.main()
