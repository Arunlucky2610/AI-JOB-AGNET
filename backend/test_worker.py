"""Worker and model-gateway checks. No employer, Browserbase or OpenRouter traffic.

Browser tests drive the real backend.worker.run() in local Chromium against a local page.
They use their own temporary database, whatever else has been imported.
"""
import asyncio, contextlib, http.server, os, tempfile, threading, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(tempfile.gettempdir())/'orbit-test-worker-unused.db').replace('\\','/'))
from fastapi import HTTPException
from playwright.async_api import async_playwright
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from . import services, worker
from .db import Base, User, Job, Application
from .domain import DEMO_PROFILE, DEFAULT_SETTINGS, fingerprint

def el(tag='BUTTON',type='submit',text='',label=''):return {'tag':tag,'type':type,'text':text,'label':label}

class ClassifyControlTests(unittest.TestCase):
    def kind(self,element,action='click'):return worker.classify_control(element,action)
    def test_step_buttons_advance_instead_of_stopping(self):
        for text in ['Next','Next step','Continue','Proceed','Save and continue','Save & Continue','Continue to review','Upload from computer']:
            with self.subTest(text):self.assertEqual(self.kind(el(text=text)),'navigate')
    def test_model_calling_a_step_button_submit_still_only_advances(self):
        self.assertEqual(self.kind(el(text='Next step'),'submit'),'navigate')
    def test_real_submit_controls_are_final(self):
        for text in ['Submit application','Submit','Send application','Save and submit']:
            with self.subTest(text):self.assertEqual(self.kind(el(text=text)),'submit')
        self.assertEqual(self.kind(el(text='Apply'),'submit'),'submit')
        self.assertEqual(self.kind(el(text='Apply now')),'submit')
    def test_apply_link_only_opens_the_form(self):
        self.assertEqual(self.kind(el(tag='A',type='',text='Apply')),'navigate')
    def test_unreadable_submit_control_needs_a_human(self):
        self.assertEqual(self.kind(el(text='',label='')),'review')
        self.assertEqual(self.kind(el(text='Finish up')),'review')
        self.assertEqual(self.kind(el(tag='A',type='',text=''),'submit'),'review')
    def test_ordinary_click_is_navigation(self):
        self.assertEqual(self.kind(el(type='button',text='Add another employer')),'navigate')

FORM='''<!DOCTYPE html><html><body>
<div id="one"><h1>Step 1 of 2</h1>
<label>Full name<input name="full_name" required></label>
<label>Email address<input name="mail" type="email" required></label>
%(next)s</div>
<div id="two" hidden><h1>Step 2 of 2</h1><p>Review your details.</p>%(final)s</div>
<h2 id="done" hidden>Thank you for applying</h2>
<script>
document.getElementById('one').addEventListener('click',e=>{const b=e.target.closest('[type=submit]');if(b){one.hidden=true;two.hidden=false;}});
document.getElementById('two').addEventListener('click',e=>{const b=e.target.closest('[type=submit]');if(b){two.hidden=true;done.hidden=false;}});
</script></body></html>'''

class _Quiet(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body=self.server.page.encode();self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*a):pass

@contextlib.contextmanager
def serve(page):
    server=http.server.HTTPServer(('127.0.0.1',0),_Quiet);server.page=page
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:yield f'http://127.0.0.1:{server.server_port}/'
    finally:server.shutdown();server.server_close()

def local_chromium():
    """Stands in for Browserbase: worker.run() asks for a CDP browser, we hand it local Chromium."""
    @contextlib.asynccontextmanager
    async def fake():
        async with async_playwright() as real:
            launched=[]
            async def connect_over_cdp(url,timeout=None):
                browser=await real.chromium.launch();launched.append(browser)
                return SimpleNamespace(contexts=[await browser.new_context()])
            try:yield SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=connect_over_cdp))
            finally:
                for browser in launched:await browser.close()
    return fake()

def scripted_model(seen):
    """Stands in for DeepSeek. Finds controls by the text/label the worker put in the snapshot."""
    async def plan(system,payload,max_tokens=0,**_):
        elements=payload['page']['elements'];seen.append(payload['page'])
        def find(caption):
            for e in elements:
                if caption in (e['label']+' '+e['text']).lower():return e['id']
            raise AssertionError(f'{caption!r} not visible to the model; snapshot was {elements}')
        if 'step 1 of 2' in payload['page']['text'].lower():
            return {'actions':[{'action':'fill','element_id':find('full name'),'field_key':'name'},{'action':'fill','element_id':find('email address'),'field_key':'email'},{'action':'click','element_id':find('next step' if any('next step' in e['text'].lower() for e in elements) else 'save and continue')}]}
        # Like a real model, pick the form's submit control whatever its caption turned out to be.
        return {'actions':[{'action':'submit','element_id':next(e['id'] for e in elements if e['type']=='submit')}]}
    return plan

# Shaped like an Avature-style portal: the file input is hidden, and the step's Continue button only appears
# when the file arrived through the visible trigger. The zero-size decoy is a site's hidden third-party button.
UPLOAD_FORM='''<!DOCTYPE html><html><body>
<div id="one"><h1>Step 1 of 2</h1>
<button type="submit" id="decoy" style="position:absolute;width:0;height:0;visibility:hidden">Default Apply</button>
<a id="trigger" href="#" role="button">Upload From Computer</a>
<a id="li" href="#" role="button">Upload CV from LinkedIn</a>
<input id="cv" type="file" accept=".pdf" style="display:none">
<div id="reveal" hidden><span id="filename"></span><button type="submit" id="go">Continue</button></div></div>
<div id="two" hidden><h1>Step 2 of 2</h1><button type="submit" id="final">Submit application</button></div>
<h2 id="done" hidden>Thank you for applying</h2>
<script>
let armed=false;window.linkedinClicked=false;
trigger.onclick=e=>{e.preventDefault();armed=true;cv.click()};
li.onclick=e=>{e.preventDefault();window.linkedinClicked=true};
cv.onchange=()=>{if(armed){filename.textContent=cv.files[0].name;reveal.hidden=false}};
go.onclick=e=>{e.preventDefault();one.hidden=true;two.hidden=false};
final.onclick=e=>{e.preventDefault();two.hidden=true;done.hidden=false};
</script></body></html>'''
PDF={'name':'resume.pdf','mimeType':'application/pdf','buffer':b'%PDF-1.4 test'}

def upload_model(seen):
    async def plan(system,payload,max_tokens=0,**_):
        elements=payload['page']['elements'];seen.append(payload['page'])
        ready=[e for e in elements if 'continue' in e['text'].lower()]
        if ready:return {'actions':[{'action':'click','element_id':ready[0]['id']}]}
        if 'step 1 of 2' in payload['page']['text'].lower():
            return {'actions':[{'action':'upload_resume','element_id':next(e['id'] for e in elements if e['type']=='file')}]}
        return {'actions':[{'action':'submit','element_id':next(e['id'] for e in elements if 'submit application' in e['text'].lower())}]}
    return plan

async def fake_pdf(*a,**k):return PDF['buffer']

class AttachFileTests(unittest.TestCase):
    def browse(self,body):
        async def go():
            async with async_playwright() as p:
                browser=await p.chromium.launch();page=await browser.new_page();await page.set_content(UPLOAD_FORM)
                out=await body(page);await browser.close();return out
        return asyncio.run(go())
    def test_hidden_input_is_filled_through_the_visible_trigger(self):
        async def body(page):
            await worker.attach_file(page,page.locator('#cv'),PDF)
            return await page.locator('#go').is_visible(),await page.inner_text('#filename'),await page.evaluate('window.linkedinClicked')
        revealed,name,linkedin=self.browse(body)
        self.assertTrue(revealed);self.assertEqual(name,'resume.pdf');self.assertFalse(linkedin)
    def test_setting_the_hidden_input_directly_leaves_the_step_stuck(self):
        """The behaviour this replaced: the file is attached but the Continue button never appears."""
        async def body(page):
            await page.locator('#cv').set_input_files(PDF)
            return await page.locator('#go').is_visible()
        self.assertFalse(self.browse(body))
    def test_visible_input_is_set_directly(self):
        async def go():
            async with async_playwright() as p:
                browser=await p.chromium.launch();page=await browser.new_page();await page.set_content('<input id="f" type="file">')
                await worker.attach_file(page,page.locator('#f'),PDF)
                name=await page.evaluate('document.getElementById("f").files[0].name');await browser.close();return name
        self.assertEqual(asyncio.run(go()),'resume.pdf')
    def test_hidden_input_with_no_trigger_still_gets_the_file(self):
        async def go():
            async with async_playwright() as p:
                browser=await p.chromium.launch();page=await browser.new_page();await page.set_content('<input id="f" type="file" style="display:none">')
                await worker.attach_file(page,page.locator('#f'),PDF)
                count=await page.evaluate('document.getElementById("f").files.length');await browser.close();return count
        self.assertEqual(asyncio.run(go()),1)

class WorkerFlowTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.engine=create_engine('sqlite:///'+str(Path(self.dir.name)/'w.db').replace('\\','/'),connect_args={'check_same_thread':False})
        Base.metadata.create_all(self.engine)
        self.Session=sessionmaker(bind=self.engine,expire_on_commit=False)
    def tearDown(self):
        self.engine.dispose();self.dir.cleanup()
    def apply(self,page,approved=True,model=None):
        """Runs the real worker on `page` and returns (application, snapshots the model saw)."""
        model=model or scripted_model
        package={'resume':DEMO_PROFILE['resume_text'],'cover_letter':'Synthetic cover letter.','notes':[],'answers':{}}
        seen=[]
        with serve(page) as url:
            job={'title':'Frontend Engineer','company':'Local Test Co','description':'x','url':url}
            with self.Session() as db:
                db.add(User(id='u',email='w@example.invalid',password='x',profile=DEMO_PROFILE,settings=DEFAULT_SETTINGS));db.flush()
                db.add(Job(id='j',user_id='u',canonical=url,payload=job));db.flush()
                db.add(Application(id='a',user_id='u',job_id='j',status='running',package=package,approved_hash=fingerprint(package) if approved else 'stale',events=[],browser={'connect_url':'local','session_id':'s','navigated':False}));db.commit()
            async def released(_):return None
            with patch.object(worker,'Session',self.Session),patch.object(worker,'async_playwright',local_chromium),patch.object(worker,'llm',model(seen)),patch('backend.career_ops_documents.pdf_bytes',fake_pdf),patch.object(worker,'allowed_application_url',lambda url,source=None:True),patch.object(worker,'release_browser',released):
                asyncio.run(worker.run('a'))
        with self.Session() as db:return db.get(Application,'a'),seen
    def test_two_step_form_with_input_buttons_reaches_confirmed_submission(self):
        a,seen=self.apply(FORM%{'next':'<input type="submit" value="Next step">','final':'<input type="submit" value="Submit application">'})
        self.assertEqual(a.status,'submitted',[e['text'] for e in a.events])
        self.assertTrue(any('Employer confirmation' in e['text'] for e in a.events))
        self.assertEqual(len(seen),2)
    def test_portal_with_hidden_file_input_completes_and_never_sees_the_decoy(self):
        a,seen=self.apply(UPLOAD_FORM,model=upload_model)
        self.assertEqual(a.status,'submitted',[e['text'] for e in a.events])
        self.assertNotIn('Default Apply',str(seen))
        self.assertTrue(any(e['type']=='file' for e in seen[0]['elements']))
    def test_snapshot_does_not_leak_typed_values(self):
        a,seen=self.apply(FORM%{'next':'<input type="submit" value="Next step">','final':'<input type="submit" value="Submit application">'})
        self.assertNotIn(DEMO_PROFILE['email'],str(seen[1]['elements']))
    def test_unreadable_submit_button_hands_over_with_a_reason(self):
        a,_=self.apply(FORM%{'next':'<input type="submit" value="Next step">','final':'<input type="submit" value="">'})
        self.assertEqual(a.status,'needs_input')
        self.assertIn('Could not tell',a.events[-1]['text'])
        self.assertNotIn('confirmation',a.events[-1]['text'].lower())
    def test_stale_approval_is_reported_not_left_running(self):
        # Text-based buttons, so this isolates the approval check from the button-caption bug.
        a,_=self.apply(FORM%{'next':'<button type="submit">Save and continue</button>','final':'<button type="submit">Submit application</button>'},approved=False)
        self.assertEqual(a.status,'needs_input',a.events[-1]['text'])
        self.assertIn('approval',a.events[-1]['text'].lower())

class SnapshotTests(unittest.TestCase):
    def test_input_captions_are_read_but_field_values_are_not(self):
        async def go():
            async with async_playwright() as p:
                browser=await p.chromium.launch();page=await browser.new_page()
                await page.set_content('<input id=t type=text value="secret-typed"><input type=submit value="Go on"><button>Plain</button>')
                snap=await page.evaluate(worker.SNAPSHOT_JS);await browser.close();return snap
        elements=asyncio.run(go())['elements']
        self.assertEqual([e['text'] for e in elements],['','Go on','Plain'])
        self.assertNotIn('secret-typed',str(elements))

    def test_invisible_controls_are_skipped_but_hidden_file_inputs_are_kept(self):
        async def go():
            async with async_playwright() as p:
                browser=await p.chromium.launch();page=await browser.new_page()
                await page.set_content('<button style="position:absolute;width:0;height:0;visibility:hidden">Ghost</button><button>Real</button><input type=file style="display:none">')
                snap=await page.evaluate(worker.SNAPSHOT_JS);await browser.close();return snap
        elements=asyncio.run(go())['elements']
        self.assertEqual([(e['tag'],e['text']) for e in elements],[('BUTTON','Real'),('INPUT','')])
    def test_ids_from_a_hidden_earlier_step_do_not_collide(self):
        async def go():
            async with async_playwright() as p:
                browser=await p.chromium.launch();page=await browser.new_page()
                await page.set_content('<div id=one><input name=a><input type=submit value=Next></div><div id=two hidden><button>Submit application</button></div>')
                await page.evaluate(worker.SNAPSHOT_JS)
                await page.evaluate("one.hidden=true;two.hidden=false")
                snap=await page.evaluate(worker.SNAPSHOT_JS)
                counts=[await page.locator(f'[data-orbit-id="{e["id"]}"]').count() for e in snap['elements']]
                await browser.close();return snap,counts
        snap,counts=asyncio.run(go())
        self.assertEqual([e['text'] for e in snap['elements']],['Submit application'])
        self.assertEqual(counts,[1])

class FakeResponse:
    def __init__(self,status=200,content=None,finish='stop'):
        self.status_code=status;self._body={'choices':[{'message':{'content':content if content is not None else '{"ok": true}'},'finish_reason':finish}]}
    def json(self):return self._body

def fake_client(responses,calls):
    class Client:
        def __init__(self,*a,**k):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):return False
        async def post(self,url,headers=None,json=None):
            calls.append(json['max_tokens']);return responses[min(len(calls)-1,len(responses)-1)]
    return Client

class FakeGeoResponse:
    def __init__(self,status=200,payload=None):
        self.status_code=status;self._payload=[] if payload is None else payload
    def json(self):return self._payload

def fake_geo_client(response,calls=None):
    class Client:
        def __init__(self,*a,**k):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):return False
        async def get(self,url,params=None):
            if calls is not None:calls.append(params)
            return response
    return Client

class GeocodeTests(unittest.TestCase):
    """services.geocode_cities: a real, confirmed place instead of whatever a person typed."""
    def test_no_key_returns_empty_without_calling_out(self):
        calls=[]
        with patch.dict(os.environ,{'LOCATIONIQ_API_KEY':''}),patch.object(services.httpx,'AsyncClient',fake_geo_client(FakeGeoResponse(),calls)):
            self.assertEqual(asyncio.run(services.geocode_cities('Hyderabad')),[]);self.assertEqual(calls,[])
    def test_a_blank_query_is_never_sent(self):
        calls=[]
        with patch.dict(os.environ,{'LOCATIONIQ_API_KEY':'k'}),patch.object(services.httpx,'AsyncClient',fake_geo_client(FakeGeoResponse(),calls)):
            self.assertEqual(asyncio.run(services.geocode_cities('   ')),[]);self.assertEqual(calls,[])
    def test_results_are_simplified_labelled_and_deduplicated(self):
        payload=[{'address':{'name':'Hyderabad','state':'Telangana','country':'India'}},
                 {'address':{'name':'Hyderabad','state':'Telangana','country':'India'}},
                 {'address':{'name':'Hyderabad','state':'Sindh','country':'Pakistan'}},
                 {'address':{}}]   # no usable name: dropped, not guessed
        with patch.dict(os.environ,{'LOCATIONIQ_API_KEY':'k'}),patch.object(services.httpx,'AsyncClient',fake_geo_client(FakeGeoResponse(200,payload))):
            got=asyncio.run(services.geocode_cities('Hyderabad'))
        self.assertEqual(got,[{'label':'Hyderabad, Telangana, India','city':'Hyderabad','state':'Telangana','country':'India'},
                               {'label':'Hyderabad, Sindh, Pakistan','city':'Hyderabad','state':'Sindh','country':'Pakistan'}])
    def test_a_bad_status_or_reply_shape_never_raises(self):
        with patch.dict(os.environ,{'LOCATIONIQ_API_KEY':'k'}),patch.object(services.httpx,'AsyncClient',fake_geo_client(FakeGeoResponse(500))):
            self.assertEqual(asyncio.run(services.geocode_cities('x')),[])
        with patch.dict(os.environ,{'LOCATIONIQ_API_KEY':'k'}),patch.object(services.httpx,'AsyncClient',fake_geo_client(FakeGeoResponse(200,{'not':'a list'}))):
            self.assertEqual(asyncio.run(services.geocode_cities('x')),[])

class LlmGatewayTests(unittest.TestCase):
    def call(self,responses,**kw):
        calls=[]
        async def no_sleep(_):return None
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test'}),patch.object(services.httpx,'AsyncClient',fake_client(responses,calls)),patch.object(services.asyncio,'sleep',no_sleep):
            try:return asyncio.run(services.llm('s',{},max_tokens=1000,**kw)),calls
            except HTTPException as error:return error,calls
    def test_invalid_json_is_retried_once(self):
        result,calls=self.call([FakeResponse(content='not json'),FakeResponse()])
        self.assertEqual(result,{'ok':True});self.assertEqual(len(calls),2)
    def test_truncation_retries_with_a_larger_budget(self):
        result,calls=self.call([FakeResponse(content='{"a":',finish='length'),FakeResponse()])
        self.assertEqual(result,{'ok':True});self.assertEqual(calls,[1000,1500])
    def test_the_retry_after_a_cut_off_reply_asks_for_less_and_samples_differently(self):
        sent=[]
        class Client:
            def __init__(self,*a,**k):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*a):return False
            async def post(self,url,headers=None,json=None):
                sent.append((json['messages'][0]['content'],json['temperature'],json['max_tokens']));return FakeResponse(content='{"a":',finish='length') if len(sent)==1 else FakeResponse()
        async def no_sleep(_):return None
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test'}),patch.object(services.httpx,'AsyncClient',Client),patch.object(services.asyncio,'sleep',no_sleep):
            self.assertEqual(asyncio.run(services.llm('base',{},max_tokens=1000)),{'ok':True})
        self.assertEqual(sent[0],('base',0.2,1000));self.assertEqual(sent[1][1:],(0.5,1500));self.assertIn('concisely',sent[1][0]);self.assertTrue(sent[1][0].startswith('base'))
    def test_each_calls_cost_is_billed_to_the_run_that_made_it(self):
        def priced(cost):
            r=FakeResponse();r._body['usage']={'cost':cost};return r
        services.SPEND.clear();token=services.current_run.set('run-1')
        try:
            self.call([priced(0.004)]);self.call([priced(0.006)])
            self.assertEqual(services.run_spend('run-1'),{'usd':0.01,'calls':2})
            self.call([FakeResponse()]);bad=FakeResponse();bad._body['usage']={'cost':'lots'};self.call([bad])
            self.assertEqual(services.run_spend('run-1')['calls'],2,'a reply without a usable cost is not counted')
        finally:services.current_run.reset(token)
        self.call([priced(5)]);self.assertEqual(services.run_spend('nobody'),{'usd':0.0,'calls':0},'calls outside a run are not billed')
        self.assertEqual(services.run_spend('run-1')['usd'],0.01)
    def test_the_run_budget_comes_from_the_environment_with_a_safe_default(self):
        for value,expected in ((None,1.0),('2.5',2.5),('junk',1.0),('-1',1.0),('0',1.0)):
            with patch.dict(os.environ,{'RUN_BUDGET_USD':value} if value else {},clear=not value):self.assertEqual(services.budget(),expected,value)
    def test_documents_are_written_without_hidden_reasoning_and_with_room_to_finish(self):
        sent=[]
        class Client:
            def __init__(self,*a,**k):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*a):return False
            async def post(self,url,headers=None,json=None):
                sent.append(json);return FakeResponse(content='{"resume":"r","cover_letter":"c","notes":[],"answers":{}}')
        profile={**services.EMPTY_PROFILE,'confirmed':True,'name':'A B','email':'a@example.invalid','resume_text':'x'}
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test'}),patch.object(services.httpx,'AsyncClient',Client):
            asyncio.run(services.generate_package(profile,{'title':'t','company':'c','description':'d'}))
            asyncio.run(services.generate_package(profile,{'title':'t','company':'c','description':'d'},patient=True))
        for body in sent:self.assertEqual((body['reasoning'],body['max_tokens']),({'enabled':False},5000))
        self.assertEqual(len(sent),2)
    def test_the_agent_asks_a_second_time_for_documents_the_ui_does_not(self):
        for patient,expected in ((False,1),(True,2)):
            calls=[]
            class Client:
                def __init__(self,*a,**k):pass
                async def __aenter__(self):return self
                async def __aexit__(self,*a):return False
                async def post(self,url,headers=None,json=None):
                    calls.append(1);return FakeResponse(content='{"resume":"r","cover_letter":"c"',finish='length')
            async def no_sleep(_):return None
            profile={**services.EMPTY_PROFILE,'confirmed':True,'name':'A B','email':'a@example.invalid','resume_text':'x'}
            with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test'}),patch.object(services.httpx,'AsyncClient',Client),patch.object(services.asyncio,'sleep',no_sleep):
                with self.assertRaises(HTTPException):asyncio.run(services.generate_package(profile,{'title':'t','company':'c','description':'d'},patient=patient))
            self.assertEqual(len(calls),expected,patient)
    def test_persistent_bad_json_gives_up_with_a_clear_error(self):
        result,calls=self.call([FakeResponse(content='nope')])
        self.assertEqual((result.status_code,len(calls)),(502,2));self.assertIn('invalid JSON',result.detail)
    def test_retries_can_be_disabled_for_user_facing_calls(self):
        result,calls=self.call([FakeResponse(content='nope'),FakeResponse()],retries=0)
        self.assertEqual(len(calls),1);self.assertIsInstance(result,HTTPException)
    def test_exhausted_credits_are_named_and_not_retried(self):
        result,calls=self.call([FakeResponse(status=402)])
        self.assertEqual((result.status_code,len(calls)),(402,1));self.assertIn('credits',result.detail)
    def test_key_spending_limit_stops_the_run_like_exhausted_credits(self):
        limit=FakeResponse(status=403);limit.text='{"error":{"message":"Key limit exceeded (total limit).","code":403}}'
        result,calls=self.call([limit])
        self.assertEqual((result.status_code,len(calls)),(402,1));self.assertIn('spending limit',result.detail)
        other=FakeResponse(status=403);other.text='{"error":{"message":"Forbidden"}}'
        result,calls=self.call([other])
        self.assertEqual(result.status_code,502)
    def test_rate_limit_is_retried_then_reported(self):
        result,calls=self.call([FakeResponse(status=429)])
        self.assertEqual((result.status_code,len(calls)),(429,2))
        result,calls=self.call([FakeResponse(status=503),FakeResponse()])
        self.assertEqual(result,{'ok':True})

if __name__=='__main__':unittest.main()
