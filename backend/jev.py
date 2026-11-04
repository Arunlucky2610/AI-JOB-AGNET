"""Jev (TypeSafe System One, typesafe/jev-1.13) through OpenRouter's decisions endpoint.

Jev makes fast typed decisions (yes/no, pick-one, rated scale) with a confidence, in well under a second. It does
not write text, is unreliable with numbers, and does not treat page text as hostile. So Orbit uses it only for
read-only triage where the worst case is a skipped or extra-reviewed job, asks small atomic questions, compares
numbers in code, and sends anything uncertain or failed to DeepSeek. It never authorizes a submission.

JEV_MODE (env): 'shadow' (default: Jev decides and is logged, but DeepSeek still reviews every job),
'active' (confident skips are acted on) or 'off'.
No personal data is ever sent: only the public job text.
"""
import asyncio, json, os, re
import httpx

MODEL='typesafe/jev-1.13'
URL='https://openrouter.ai/api/alpha/decisions'
MIN_CONFIDENCE=0.8

class JevUnavailable(Exception):
    """Jev could not answer (no key, error, bad reply). The caller falls back to DeepSeek."""

def mode():
    value=os.getenv('JEV_MODE','shadow').strip().lower()
    return value if value in ('off','shadow','active') else 'shadow'

async def decide(state,questions,retries=2,timeout=20):
    """One fan-out call: all questions answered against the same state."""
    key=os.getenv('OPENROUTER_API_KEY')
    if not key:raise JevUnavailable('no OpenRouter key')
    body={'model':MODEL,'state':state if isinstance(state,str) else json.dumps(state,ensure_ascii=False),'questions':questions}
    last='no attempt'
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(retries+1):
            try:
                response=await client.post(URL,headers={'Authorization':'Bearer '+key},json=body)
            except httpx.HTTPError as error:
                last=type(error).__name__
            else:
                if response.status_code==200:
                    try:return response.json()['answers']
                    except (ValueError,KeyError,TypeError):raise JevUnavailable('unreadable reply')
                if response.status_code in (400,401,402,403,422):raise JevUnavailable(f'HTTP {response.status_code}')
                last=f'HTTP {response.status_code}'   # 429/5xx are worth another try
            if attempt<retries:await asyncio.sleep(0.4*(attempt+1))
    raise JevUnavailable(last)

# --- job triage: small atomic questions; code combines them ---------------------------------------------------
TRIAGE_QUESTIONS={
  'min_experience':{'type':'choice','instructions':'What minimum professional work experience does the job posting require? Use the stated minimum only.',
      'criteria':{'none_stated':'No minimum experience is stated, or freshers and graduates are welcome',
                  'up_to_1_year':'The stated minimum is 1 year or less (or 0-1 years)',
                  'two_to_three_years':'The stated minimum is 2 or 3 years',
                  'four_plus_years':'The stated minimum is 4 years or more'}},
  'ai_ml_role':{'type':'noul','instructions':'Is this job primarily an AI, machine learning or generative AI engineering role?'},
  'software_role':{'type':'noul','instructions':'Is this job a software developer or Python developer role?'},
  'junior_level':{'type':'noul','instructions':'Does the posting describe an internship, trainee, graduate or entry-level position?'},
}
MIN_YEARS={'none_stated':0,'up_to_1_year':1,'two_to_three_years':2,'four_plus_years':4}

ABOUT=re.compile(r'about the job(.*?)(about the company|set alert|similar jobs|people also viewed|$)',re.I|re.S)

def job_state(title,page_text,limit=3500):
    """Only the posting: the 'About the job' section when present. Unrelated page text distracts Jev."""
    match=ABOUT.search(page_text or '')
    body=(match.group(1) if match and match.group(1).strip() else page_text or '')
    return {'title':title,'description':re.sub(r'\s+',' ',body).strip()[:limit]}

def triage(answers,candidate_years,relaxed):
    """('review'|'skip_experience'|'skip_role'|'uncertain', why). Numbers are compared here, in code, never by Jev.
    'skip_*' needs confident answers; anything unsure is 'uncertain' and goes to DeepSeek."""
    try:
        experience=answers['min_experience'];confidence=float(experience.get('confidence',0))
        ai=float(answers['ai_ml_role']['noul']);software=float(answers['software_role']['noul']);junior=float(answers['junior_level']['noul'])
    except (KeyError,TypeError,ValueError,AttributeError):return 'uncertain','unreadable answers'
    if confidence<MIN_CONFIDENCE:return 'uncertain',f'experience confidence {confidence:.2f}'
    minimum=MIN_YEARS.get(experience.get('choice'))
    if minimum is None:return 'uncertain','unknown experience choice'
    if minimum>max(candidate_years,1):return 'skip_experience',f"requires {experience['choice'].replace('_',' ')}"
    if not relaxed:return 'review','experience ok'
    if ai>=0.5 or (software>=0.5 and junior>=0.5):return 'review','role ok'
    if ai<=0.2 and software<=0.2:return 'skip_role','not an AI or software role'
    return 'uncertain','role unclear'

def compare(verdict,deepseek_matched):
    """How Jev's verdict lines up with DeepSeek's later review: agree_skip, agree_review, missed_match, extra_review."""
    skipped=verdict.startswith('skip')
    if skipped and deepseek_matched:return 'missed_match'
    if skipped:return 'agree_skip'
    return 'agree_review' if deepseek_matched else 'extra_review'
