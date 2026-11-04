"""Agent run control shared by the job-platform agents; single-process pilot.

Orbit works with LinkedIn only. Employer career pages (Greenhouse, Lever, Ashby, Workday, JobSpy, company
portals), Naukri and Indeed were removed; the old code is in archive/removed-career-portal-code and
archive/removed-indeed-code.
"""
import asyncio
from .db import Session, User, AgentRun, now
from .domain import fingerprint

agent_tasks={}

# Preference value -> platform name used on jobs and applications.
SOURCES={'linkedin':'LinkedIn', 'indeed':'Indeed', 'naukri':'Naukri', 'internshala':'Internshala'}

def update(id, message=None, **changes):
    with Session() as db:
        run=db.get(AgentRun,id)
        for k,v in changes.items(): setattr(run,k,v)
        if message: run.events=[*run.events,{'time':now().isoformat(),'text':message}][-250:]
        run.updated=now();db.commit()

def current(id):
    with Session() as db:
        run=db.get(AgentRun,id)
        return run.status

async def gate(id):
    """Wait while the run is paused or needs the person; False if the profile changed or the run is no longer running."""
    while current(id) in ['paused','needs_input']:
        await asyncio.sleep(1)
    with Session() as db:
        run=db.get(AgentRun,id)
        user=db.get(User,run.user_id)
        expected=run.state.get('profile_hash')
        if expected and expected!=fingerprint(user.profile):
            update(id,'Your profile changed. Stop this run and start again to use the updated details.',status='paused')
            return False
    return current(id)=='running'

async def execute(id):
    try:
        with Session() as db:
            run=db.get(AgentRun,id);user=db.get(User,run.user_id)
            focus=user.settings.get('source_focus')
        from .platform_agent import execute_platform, connected_platforms
        target=SOURCES.get(focus)
        if not target:
            status=connected_platforms(user.id)
            if status.get('Indeed') and not status.get('LinkedIn'):
                target='Indeed'
            else:
                target='LinkedIn'
        return await execute_platform(id, target)

    except asyncio.CancelledError:raise
    except Exception as error:
        import traceback
        traceback.print_exc()
        msg = getattr(error, 'detail', None) or str(error) or f"{type(error).__name__}: {repr(error)}"
        update(id, f'Agent interrupted: {msg}'[:180], status='failed')
