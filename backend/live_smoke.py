"""Opt-in real DeepSeek + Browserbase smoke test on an intercepted synthetic form.

Run with python -m backend.live_smoke. Uses fictional data and an isolated DB.
All browser HTTP requests are intercepted: fixture pages are fulfilled locally,
everything else is aborted. No employer receives an application.
"""
import asyncio, json, os, tempfile, uuid, time, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
scratch=tempfile.TemporaryDirectory()
os.environ['DATABASE_URL']='sqlite:///'+str(Path(scratch.name)/'smoke.db').replace('\\','/')
from playwright.async_api import async_playwright
from .db import init, Session, User, Job, Application, engine
from .domain import DEMO_PROFILE, DEFAULT_SETTINGS, fingerprint, MODEL
from .services import generate_package, browser_session, release_browser, llm
from . import worker as worker_module
from .worker import run
# The synthetic fixture is not on a job platform, so the platform-only allow-list would refuse it. Fixture only.
worker_module.allowed_application_url=lambda url,source=None:True

FORM='''<!DOCTYPE html><html><head><title>Orbit synthetic application test</title>
<style>body{font-family:Arial;max-width:650px;margin:50px auto;background:#f7faf3}label{display:block;margin:20px}input{display:block;padding:12px;width:90%}button{padding:15px;background:#c2f970;border:0;border-radius:8px}</style></head><body>
<h1>Orbit Test Company — Frontend Engineer</h1><p>Synthetic form. No employer submission.</p>
<form onsubmit="event.preventDefault(); document.querySelector('#confirmation').textContent='Application successfully submitted'; this.hidden=true;">
<label>Full name<input name="name" required></label><label>Email<input name="email" type="email" required></label>
<label>Phone<input name="phone" required></label><label>Resume<input name="resume" type="file" required></label>
<button type="submit">Submit application</button></form><h2 id="confirmation"></h2></body></html>'''

async def main():
    report={'model':MODEL,'synthetic':True,'checks':{},'events':[]}
    session=None
    try:
        profile={**DEMO_PROFILE,'phone':'+1 202 555 0142'}
        job={'title':'Frontend Engineer','company':'Orbit Test Company','description':'Build accessible React and TypeScript interfaces, collaborate with designers, and maintain component tests.','url':'https://jobs.ashbyhq.com/orbit-synthetic-test/apply'}
        if '--form-only' in sys.argv:
            package={'resume':profile['resume_text'],'cover_letter':'Synthetic test cover letter. Alex Morgan.','notes':[],'answers':{}}
            report['scope']='Form planning and execution only; document generation verified in earlier run.'
        else:
            probe=await llm('Return JSON {"connected":true}.',{'task':'connection test'})
            report['checks']['model_connection']=probe.get('connected') is True
            package=await generate_package(profile,job)
            report['checks']['resume_generated']=bool(package['resume'])
            report['checks']['cover_letter_generated']=bool(package['cover_letter'])
        session=await browser_session()
        report['session_url']='https://www.browserbase.com/sessions/'+session['id']
        report['checks']['live_view_available']=bool(session.get('live_url'))
        print(json.dumps({'phase':'Browserbase synthetic test started','session_url':report['session_url']}),flush=True)
        init();user_id=str(uuid.uuid4());job_id=str(uuid.uuid4());app_id=str(uuid.uuid4())
        with Session() as db:
            db.add(User(id=user_id,email='smoke@example.invalid',password='test-only',profile=profile,settings=DEFAULT_SETTINGS));db.flush()
            db.add(Job(id=job_id,user_id=user_id,canonical=job['url'],payload=job));db.flush()
            db.add(Application(id=app_id,user_id=user_id,job_id=job_id,status='running',package=package,approved_hash=fingerprint(package),events=[],browser={'connect_url':session['connectUrl'],'session_id':session['id'],'live_url':session.get('live_url')}));db.commit()
        async with async_playwright() as p:
            browser=await p.chromium.connect_over_cdp(session['connectUrl'])
            context=browser.contexts[0]
            async def intercept(route):
                if route.request.url==job['url']:await route.fulfill(status=200,content_type='text/html',body=FORM)
                else:await route.abort()
            await context.route('**/*',intercept)
            started=time.monotonic()
            await run(app_id)
            report['browser_agent_seconds']=round(time.monotonic()-started,2)
            with Session() as db:
                a=db.get(Application,app_id)
                report['status']=a.status;report['events']=a.events;report['model_batches']=a.browser.get('model_batches',0)
                report['checks']['verified_synthetic_submission']=a.status=='submitted'
            report['checks']['agent_filled_fields']=any('fill' in e['text'].lower() or 'name' in e['text'].lower() for e in report['events'])
        report['passed']=all(report['checks'].values())
    except Exception as e:
        report['passed']=False;report['error']=str(getattr(e,'detail',type(e).__name__))
    finally:
        if session:
            try:await release_browser(session['id'])
            except Exception:pass
        engine.dispose();scratch.cleanup()
        Path('agent-test-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':asyncio.run(main())
