"""Read current public ATS data before spending a model call on stale links."""
import re
from urllib.parse import urlparse, parse_qs
import httpx
from fastapi import HTTPException

async def public_posting(url):
    parsed=urlparse(url);host=parsed.hostname or '';parts=parsed.path.strip('/').split('/')
    if len(parts)<2 or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',parts[0]):return None
    board=parts[0];job_id=parts[1]
    if host in ['boards.greenhouse.io','job-boards.greenhouse.io'] and board=='embed':
        query=parse_qs(parsed.query);board=query.get('for',[''])[0];job_id=query.get('token',[''])[0]
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',board) or not job_id.isdigit():return None
        parts=[board,'jobs',job_id];job_id='jobs'
    if host in ['boards.greenhouse.io','job-boards.greenhouse.io'] and job_id=='jobs' and len(parts)>2:
        job_id=parts[2]
        if not job_id.isdigit():return None
        endpoint=f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}?content=true';provider='Greenhouse'
    elif host=='jobs.lever.co' and re.fullmatch(r'[a-f0-9-]{36}',job_id):
        endpoint=f'https://api.lever.co/v0/postings/{board}/{job_id}?mode=json';provider='Lever'
    elif host=='jobs.ashbyhq.com' and re.fullmatch(r'[a-f0-9-]{36}',job_id):
        endpoint=f'https://api.ashbyhq.com/posting-api/job-board/{board}';provider='Ashby'
    else:return None
    async with httpx.AsyncClient(timeout=20) as client:
        response=await client.get(endpoint)
    if response.status_code in [404,410]:raise HTTPException(410,f'{provider} public API confirms this vacancy is unavailable.')
    response.raise_for_status();data=response.json()
    if provider=='Ashby':
        data=next((j for j in data.get('jobs',[]) if job_id in (j.get('jobUrl','')+' '+j.get('applyUrl',''))),None)
        if not data:raise HTTPException(410,'Ashby public API no longer lists this vacancy.')
    return {'provider':provider,'posting':data}

async def greenhouse_board_jobs(url):
    """Expand an observed employer board into its currently published vacancies."""
    parsed=urlparse(url);board=parsed.path.strip('/').split('/')[0]
    if board=='embed':board=parse_qs(parsed.query).get('for',[''])[0]
    if parsed.hostname not in ['boards.greenhouse.io','job-boards.greenhouse.io'] or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',board):return []
    async with httpx.AsyncClient(timeout=20) as client:
        response=await client.get(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs')
    response.raise_for_status()
    return response.json().get('jobs',[])

def canonical_job_url(url):
    """Greenhouse aliases and tracking parameters identify one employer vacancy."""
    parsed=urlparse(url);parts=parsed.path.strip('/').split('/')
    if (parsed.hostname or '').endswith('.myworkdayjobs.com'):
        # Adapt Career Ops workdayDedupKey; an observed /apply suffix is the same requisition.
        if parts[-1]=='apply':parts=parts[:-1]
        tail=parts[-1] if parts else ''
        if '_' in tail:
            req=tail.split('_',1)[1].lower()
            m=re.fullmatch(r'(.*?)-(\d{1,2})',req)
            if m and re.fullmatch(r'[a-z]*\d[a-z0-9_]*\d{2,}',m[1]):req=m[1]
            return f'workday:{parsed.hostname.lower()}:{req}'
    if parsed.hostname in ['jobs.ashbyhq.com','jobs.lever.co','jobs.eu.lever.co'] and len(parts)>1 and re.fullmatch(r'[a-f0-9-]{36}',parts[1]):
        return f'https://{parsed.hostname}/{parts[0]}/{parts[1]}'
    if parsed.hostname in ['boards.greenhouse.io','job-boards.greenhouse.io']:
        board=parts[0];job_id=''
        if board=='embed':
            query=parse_qs(parsed.query);board=query.get('for',[''])[0];job_id=query.get('token',[''])[0]
        elif len(parts)>2 and parts[1]=='jobs':job_id=parts[2]
        if re.fullmatch(r'[A-Za-z0-9_-]{1,100}',board) and job_id.isdigit():
            return f'https://job-boards.greenhouse.io/{board}/jobs/{job_id}'
    return url.split('#')[0].rstrip('/')

def existing_vacancy(db,user_id,url):
    """Resolve aliases without deleting legacy jobs or application history."""
    from .db import Job, Application
    key=canonical_job_url(url)
    jobs=[j for j in db.query(Job).filter_by(user_id=user_id) if canonical_job_url(j.payload.get('url',''))==key]
    if not jobs:return None
    app=db.query(Application).filter(Application.user_id==user_id,Application.job_id.in_([j.id for j in jobs])).first()
    return next((j for j in jobs if app and j.id==app.job_id),jobs[0])
