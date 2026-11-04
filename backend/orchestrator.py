"""The agent's decision layer: pure, testable rules the run loop (platform_agent.py) calls between tool uses.

Control loop (one orchestrator, specialised tools):
  OBSERVE   read the candidate's goals, today's quota and spend, and what is already known about a job
  REASON    judge fit (model) against hard rules (code); rank eligible jobs best-first
  PLAN      build_plan(): searches, quota, budget, threshold, open questions, all shown to the person
  SELECT    pick the next tool: skip a duplicate, re-verify a vacancy, write documents, hand off to the person
  EXECUTE   browser and model tools (platform_agent / worker / services)
  VERIFY    classify_vacancy() before applying, grounding_report() on documents, submission evidence in worker.py
  MEMORY    decision traces and shortlist in the run state, jobs/applications/outcomes in the database
  EVALUATE  conversion_stats(), bucket_report() and compare_rankings() over recorded outcomes

Nothing here lets a model verdict override a safety check: these functions only ever make the agent stricter.
"""
import asyncio, json, re
from datetime import datetime, timezone
from pathlib import Path

EVIDENCE_DIR=Path('data')/'evidence'   # screenshots taken just before submitting and at the confirmation screen

PROGRESSED=('shortlisted','assessment','interview','offer')
STAGES=('waiting',*PROGRESSED,'rejected','no_response')

# --- goals and plan ---------------------------------------------------------------------------------------------

def is_junior(profile):
    from .domain import career_level
    return career_level(profile) in ('intern','fresher')

def fit_threshold(profile,settings):
    """The minimum fit score for an application. The person's own setting wins; otherwise 60% for interns and
    freshers and 70% for experienced candidates. Model scores are estimates, not probabilities."""
    custom=(settings or {}).get('threshold')
    if isinstance(custom,(int,float)) and not isinstance(custom,bool):return int(custom)
    return 60 if is_junior(profile) else 70

def blocking_questions(profile):
    """What the agent must ask before searching, instead of silently assuming."""
    asks=[]
    if not [r for r in (profile.get('roles') or '').split(',') if r.strip()]:asks.append('Which job roles should I search for?')
    if not (profile.get('country') or '').strip():asks.append('Which country do you want to work in?')
    return asks

def soft_questions(profile):
    """Gaps that do not stop a run but change what it can do. Shown in the plan."""
    asks=[]
    if not (profile.get('authorization') or '').strip():asks.append('Are you authorised to work in your target country?')
    if not (profile.get('sponsorship') or '').strip():asks.append('Do you need visa sponsorship? Jobs that do not say are flagged for your review.')
    if not profile.get('work_modes'):asks.append('Which work modes are acceptable (Remote, Hybrid, Onsite)?')
    return asks

def build_plan(profile,settings,searches,started_today=0,waiting=0,spent=0.0,budget=1.0):
    """A transparent plan for this run, stored in the run state and shown on the Live agent page."""
    limit=int((settings or {}).get('daily_limit',3))
    slots=slots_left(limit,started_today,waiting)
    threshold=fit_threshold(profile,settings)
    from .domain import career_level
    return {'objective':{'roles':[r.strip() for r in (profile.get('roles') or '').split(',') if r.strip()],'level':career_level(profile),
                'country':profile.get('country',''),'locations':profile.get('locations',''),'work_modes':profile.get('work_modes',[]),
                'sponsorship':profile.get('sponsorship',''),'blacklist':[c.strip() for c in (profile.get('excluded_companies') or '').split(',') if c.strip()]},
        'searches':list(searches),'threshold':threshold,'quota':{'limit':limit,'used_today':started_today,'waiting':waiting,'slots':slots},
        'budget':{'usd_limit':budget,'usd_spent':round(spent,4)},'questions':soft_questions(profile),
        'steps':['Search your target roles on LinkedIn Easy Apply','Drop obvious misses and duplicates with free checks',
                 f'Judge fit against your goals; keep only {threshold}% or better',f'Rank the matches best-first and keep the top {slots}',
                 'Re-open each chosen job and confirm it is still open','Write role-specific documents from your confirmed evidence',
                 'Wait for your approval of the exact package, then submit and record the confirmation']}

def slots_left(limit,started_today,waiting):
    """How many more applications to prepare: the daily limit minus what is sent, in flight, or already waiting for review."""
    return max(0,int(limit)-int(started_today)-int(waiting))

# --- ranking and duplicates -------------------------------------------------------------------------------------

CORP=re.compile(r'\b(inc|llc|ltd|limited|corp|corporation|pvt|private|co|company|gmbh|plc)\b\.?',re.I)
LEVEL=re.compile(r'\b(sr|senior|jr|junior|lead)\b\.?',re.I)
def _clean(text):return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9+# ]+',' ',text.casefold())).strip()

def entity_key(company,title,location=''):
    """A key that is the same for one vacancy reposted under another URL: company and title with corporate
    suffixes, seniority words and bracketed notes removed, plus the first part of the location."""
    title=re.sub(r'[\(\[].*?[\)\]]','',title or '')
    place=(location or '').split(',')[0]
    return '|'.join((_clean(CORP.sub('',company or '')),_clean(LEVEL.sub('',title)),_clean(place)))

BASELINE='baseline'   # ranking by the model's fit score alone: the reference every proposal is measured against

def exp_band(years):
    return 'not stated' if years is None else '0-1 years' if years<=1 else '2+ years'

def features(item):
    """The few job attributes a learned adjustment may use. Deliberately coarse and human-readable."""
    return {'mode':item.get('mode') or 'Unknown','experience':exp_band(item.get('min_experience'))}

def adjustment_for(item,adjustments):
    """Points added to a job's ORDER SCORE by an accepted ranking. Never changes the fit score itself."""
    if not adjustments:return 0
    return sum(int(adjustments.get(kind,{}).get(value,0)) for kind,value in features(item).items())

def rank_jobs(jobs,adjustments=None):
    """Best-first and deterministic. With no adjustments this is the baseline: fit score, then evidence-report score, then matched
    skills, then a stable id. An accepted adjustment only shifts the order of jobs that already passed every check; the fit floor,
    verification, approval, duplicate and quota rules are applied by the caller to every job regardless of its rank."""
    key=lambda j:(-(int(j.get('score') or 0)+adjustment_for(j,adjustments)),-int(j.get('score') or 0),-float(j.get('global_score') or 0),-len(j.get('matched_skills') or []),str(j.get('canonical') or j.get('job_id') or ''))
    return sorted(jobs,key=key)

# --- live vacancy verification ----------------------------------------------------------------------------------

def classify_vacancy(verdict,url='',now=None):
    """Turn the job page's observed state into open / closed / uncertain, with evidence. Only 'open' is verified open."""
    status,evidence={'easy':('open','The page shows an active Easy Apply button.'),
        'closed':('closed','The page says the job is no longer accepting applications.'),
        'applied':('closed','You have already applied to this job.'),
        'external':('closed','The job applies on the employer site, not in LinkedIn Easy Apply.'),
        }.get(verdict,('uncertain','The page did not show a clear open or closed state.'))
    return {'status':status,'evidence':evidence,'method':'live LinkedIn job page','verdict':verdict,'url':(url or '').split('?')[0],'checked_at':(now or datetime.now(timezone.utc)).isoformat()}

def verified_open(verification):
    return bool(verification) and verification.get('status')=='open'

def blocks_application(verification):
    """Closed or uncertain vacancies are never started. A job nobody has re-checked yet ('unverified') still gets the
    worker's own live check when its page is opened, so only an explicit closed/uncertain result stops it here."""
    return bool(verification) and verification.get('status') in ('closed','uncertain')

# --- truthful documents -----------------------------------------------------------------------------------------

NUMBER_CLAIM=re.compile(r'(?<![\w.])(?:[$₹€£]\s?\d[\d,.]*\s?[kKmMbB]?|\d[\d,.]*\s?%|\d[\d,.]*\s?[xX](?!\w)|\d+\+?\s?(?:years?|yrs?)(?!\w)|\d[\d,]*\+?\s?(?:users|customers|clients|requests|records|projects|stars|downloads))',re.I)
CERT_CLAIM=re.compile(r'\b(?:[A-Z][\w+#.\-]*\s+){0,3}(?:Certified|Certification|Certificate)(?:\s+[A-Z][\w+#.\-]*){0,4}')
def _squash(text):return re.sub(r'\s+','',(text or '').casefold())

def evidence_text(profile):
    return _squash(json.dumps(profile,ensure_ascii=False)+' '+str(profile.get('resume_text','')))

def grounding_report(package,profile,missing_skills=(),confirmed=()):
    """Claims in the generated documents that the candidate's confirmed profile does not support: numbers and
    metrics, certifications, and skills the job needs that the candidate lacks. The person can confirm a claim
    (it is then theirs) or edit it out; an unresolved one blocks approval."""
    evidence=evidence_text(profile);resume=str(package.get('resume',''));letter=str(package.get('cover_letter',''))
    found=[]
    for source,text in (('resume',resume),('cover letter',letter)):
        for match in NUMBER_CLAIM.finditer(text):
            claim=match.group(0).strip()
            if _squash(claim) not in evidence:found.append(f'{claim} ({source})')
        for match in CERT_CLAIM.finditer(text):
            claim=match.group(0).strip()
            if _squash(claim) not in evidence:found.append(f'{claim} ({source})')
    for skill in missing_skills or ():
        if skill and _squash(skill) not in evidence and re.search(r'(?<!\w)'+re.escape(skill)+r'(?!\w)',resume,re.I):found.append(f'{skill} (skill you lack, in resume)')
    done={_squash(c) for c in confirmed or ()}
    pending=[c for c in dict.fromkeys(found) if _squash(c) not in done and _squash(c.rsplit(' (',1)[0]) not in done]
    return {'ungrounded':pending,'confirmed':list(confirmed or ())}

# --- decision traces and retries --------------------------------------------------------------------------------

REDACT=[(re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'),'[email]'),(re.compile(r'(?<!\d)\+?\d[\d\s().-]{8,}\d'),'[phone]'),(re.compile(r'(sk|bb|key)[-_][A-Za-z0-9_-]{12,}'),'[secret]')]
def redact(text):
    for pattern,label in REDACT:text=pattern.sub(label,str(text))
    return text

def trace(state,step,subject,decision,reason='',**data):
    """Append one concise decision to the run's trace (newest last, capped). Only short, redacted fields are kept."""
    entry={'time':datetime.now(timezone.utc).isoformat(),'step':step,'subject':redact(subject)[:90],'decision':decision,'reason':redact(reason)[:200],**{k:v for k,v in data.items() if isinstance(v,(int,float,bool,str)) and len(str(v))<=60}}
    return {**state,'trace':[*state.get('trace',[]),entry][-200:]}

def is_transient(error):
    """Worth another try: timeouts, network faults, rate limits and provider 5xx. Never a 4xx the person must fix."""
    import httpx
    from fastapi import HTTPException
    if isinstance(error,(asyncio.TimeoutError,TimeoutError,httpx.TransportError)):return True
    return isinstance(error,HTTPException) and error.status_code in (429,502,503,504)

async def retry(operation,attempts=3,delay=0.5,sleep=asyncio.sleep):
    """Run `operation()` up to `attempts` times, waiting longer each time, retrying only transient errors."""
    last=None
    for attempt in range(max(1,attempts)):
        try:return await operation()
        except asyncio.CancelledError:raise
        except Exception as error:
            last=error
            if not is_transient(error) or attempt==attempts-1:raise
            await sleep(delay*(2**attempt))
    # pyrefly: ignore [bad-raise]
    raise last

# --- outcomes and evaluation ------------------------------------------------------------------------------------

def conversion_stats(rows):
    """rows: [{'stage': ..., 'fit_feedback': ...}], one per SUBMITTED application (stage 'waiting' when none recorded).

    Definitions (denominators stated so the numbers cannot be misread):
      shortlist_rate = applications that reached shortlisted/assessment/interview/offer / ALL submitted applications
      decided_rate   = the same numerator / applications with a known result (progressed + rejected)
      response_rate  = (progressed + rejected) / ALL submitted applications"""
    stages={s:0 for s in STAGES}
    for row in rows:stages[row.get('stage') if row.get('stage') in stages else 'waiting']+=1
    total=len(rows);progressed=sum(stages[s] for s in PROGRESSED);decided=progressed+stages['rejected']
    feedback=[r.get('fit_feedback') for r in rows if r.get('fit_feedback')]
    pct=lambda a,b:round(100*a/b) if b else None
    return {'submitted':total,'stages':stages,'progressed':progressed,'shortlist_rate':pct(progressed,total),'decided_rate':pct(progressed,decided),
        'response_rate':pct(decided,total),'fit_up':feedback.count('up'),'fit_down':feedback.count('down'),
        'definition':'shortlist rate = shortlisted, assessment, interview or offer divided by all submitted applications; decided rate divides by applications with a known result.'}

def _bucket(score):
    score=int(score or 0)
    return '80+' if score>=80 else '70-79' if score>=70 else '60-69' if score>=60 else 'under 60'

def bucket_report(history):
    """history: [{'score','mode','min_experience','progressed','decided'}]. Conversion by fit score, work mode and asked experience,
    over applications with a known result only. Small groups are shown with their size so they are not over-read."""
    def group(keyfn):
        out={}
        for item in history:
            if not item.get('decided'):continue
            slot=out.setdefault(keyfn(item),{'decided':0,'progressed':0})
            slot['decided']+=1;slot['progressed']+=int(bool(item.get('progressed')))
        return {k:{**v,'rate':round(100*v['progressed']/v['decided'])} for k,v in sorted(out.items())}
    exp=lambda i:'not stated' if i.get('min_experience') is None else '0-1 years' if i['min_experience']<=1 else '2+ years'
    return {'by_fit_score':group(lambda i:_bucket(i.get('score'))),'by_work_mode':group(lambda i:i.get('mode') or 'Unknown'),'by_experience_asked':group(exp)}

def average_precision(history,key):
    """How early the applications that progressed appear when ranked best-first by `key` (1.0 = all at the top)."""
    ordered=sorted((h for h in history if h.get('decided')),key=lambda h:(-key(h),str(h.get('id',''))))
    hits=0;total=0.0
    for position,item in enumerate(ordered,1):
        if item.get('progressed'):hits+=1;total+=hits/position
    return total/hits if hits else 0.0

MIN_DECIDED=20;MIN_PROGRESSED=5
def compare_rankings(history,candidate_key,baseline_key=lambda h:h.get('score') or 0):
    """Offline test of a ranking idea against the current one (model fit score) on recorded results. Returns a verdict
    only with enough data; with less it says so and proposes nothing."""
    decided=[h for h in history if h.get('decided')];progressed=sum(bool(h.get('progressed')) for h in decided)
    if len(decided)<MIN_DECIDED or progressed<MIN_PROGRESSED:
        return {'enough_data':False,'decided':len(decided),'progressed':progressed,'needed':f'{MIN_DECIDED} results with at least {MIN_PROGRESSED} that progressed'}
    base=average_precision(decided,baseline_key);cand=average_precision(decided,candidate_key)
    return {'enough_data':True,'decided':len(decided),'progressed':progressed,'baseline_ap':round(base,3),'candidate_ap':round(cand,3),'delta':round(cand-base,3),'better':cand>base+0.02}

def suggest_threshold(history,current):
    """An advisory only: if applications below the current floor's next band convert clearly worse than the rest, say so.
    Never changes a setting by itself."""
    report=bucket_report(history)['by_fit_score'];low=report.get('60-69');high=[v for k,v in report.items() if k in ('70-79','80+')]
    if not low or not high or low['decided']<5 or sum(v['decided'] for v in high)<5:return None
    high_rate=100*sum(v['progressed'] for v in high)/sum(v['decided'] for v in high)
    if high_rate-low['rate']>=20 and current<70:return f'Applications scored 60-69% progressed {low["rate"]}% of the time versus {round(high_rate)}% at 70% or more. Consider raising your minimum match score to 70%.'
    return None


# --- outcome-driven ranking proposals ---------------------------------------------------------------------------
# A proposal is a small table of point adjustments by work mode and asked experience, learned from the person's own recorded
# results, shrunk toward the overall rate and capped. It is only ever PROPOSED: it takes effect after the person accepts it,
# and it only reorders jobs that already passed every check.
ADJUST_CAP=8          # most points any one feature can add or remove
ADJUST_SCALE=20       # points per 100 percentage points of difference in progress rate
GROUP_MIN=5           # decided results a group needs before it can move
SHRINK=5              # pseudo-results pulling a small group toward the overall rate
MIN_GAIN=0.03         # held-out average-precision gain required to propose

def learn_adjustments(history):
    """Per-feature point adjustments from decided results: groups that progressed more than the overall rate move up, fewer move down."""
    decided=[h for h in history if h.get('decided')]
    if not decided:return {}
    overall=sum(bool(h.get('progressed')) for h in decided)/len(decided);table={}
    for kind in ('mode','experience'):
        groups={}
        for h in decided:
            groups.setdefault(features(h)[kind],[]).append(bool(h.get('progressed')))
        for value,hits in sorted(groups.items()):
            if len(hits)<GROUP_MIN:continue
            smoothed=(sum(hits)+overall*SHRINK)/(len(hits)+SHRINK)
            points=max(-ADJUST_CAP,min(ADJUST_CAP,round((smoothed-overall)*ADJUST_SCALE)))
            if points:table.setdefault(kind,{})[value]=int(points)
    return table

def ranking_version(adjustments):
    import hashlib
    return 'adj-'+hashlib.sha1(json.dumps(adjustments,sort_keys=True).encode()).hexdigest()[:8] if adjustments else BASELINE

def evaluate_adjustments(history):
    """Held-out check: learn on one half of the decided results, score ranking quality on the other half, and swap. A proposal
    needs the adjusted ranking to beat the baseline on both halves, so it cannot be learned and judged on the same results."""
    decided=sorted((h for h in history if h.get('decided')),key=lambda h:str(h.get('id','')))
    halves=[decided[0::2],decided[1::2]];folds=[]
    for train,test in ((halves[0],halves[1]),(halves[1],halves[0])):
        table=learn_adjustments(train)
        base=average_precision(test,lambda h:h.get('score') or 0)
        adj=average_precision(test,lambda h:(h.get('score') or 0)+adjustment_for(h,table))
        folds.append({'baseline_ap':round(base,3),'adjusted_ap':round(adj,3),'delta':round(adj-base,3)})
    return folds

def propose_ranking(history,rejected=()):
    """{'status': ...} always. 'proposed' carries the adjustments, a plain-language rationale and the held-out evaluation.
    status is insufficient_data, no_improvement, rejected or proposed; nothing here activates anything."""
    decided=[h for h in history if h.get('decided')];progressed=sum(bool(h.get('progressed')) for h in decided)
    base={'decided':len(decided),'progressed':progressed}
    if len(decided)<MIN_DECIDED or progressed<MIN_PROGRESSED:
        return {**base,'status':'insufficient_data','needed':f'{MIN_DECIDED} results with at least {MIN_PROGRESSED} that progressed'}
    table=learn_adjustments(decided)
    if not table:return {**base,'status':'no_improvement','reason':'No work mode or experience group differs enough from your overall results.'}
    folds=evaluate_adjustments(decided);mean=round(sum(f['delta'] for f in folds)/len(folds),3)
    evaluation={'folds':folds,'mean_delta':mean,'baseline_ap':round(sum(f['baseline_ap'] for f in folds)/2,3),'adjusted_ap':round(sum(f['adjusted_ap'] for f in folds)/2,3)}
    if mean<MIN_GAIN or any(f['delta']<0 for f in folds):
        return {**base,'status':'no_improvement','evaluation':evaluation,'reason':'On held-out results the adjusted order was not clearly better than ranking by fit score alone.'}
    version=ranking_version(table)
    if version in set(rejected):return {**base,'status':'rejected','version':version,'evaluation':evaluation}
    rationale=[f"{'+' if p>0 else ''}{p} points for {kind.replace('mode','work mode').replace('experience','experience asked')} {value}" for kind,vals in table.items() for value,p in vals.items()]
    return {**base,'status':'proposed','version':version,'adjustments':table,'evaluation':evaluation,'rationale':rationale,
            'caveat':'A pattern in your own recorded results, not proof it will raise interviews. It only reorders jobs that already passed every check.'}
