"""Career Ops fit evaluation, adapted to Orbit's user state. (Employer-feed discovery was removed.)"""
import json, re
from fastapi import HTTPException
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
UPSTREAM=ROOT/'vendor'/'career-ops'

def evaluation_instructions():
    """Use upstream evidence tiers and requirement importance, adapted to freshers."""
    source=(UPSTREAM/'modes'/'oferta.md').read_text(encoding='utf-8')
    evidence=source[source.index('### Evidence tiers'):source.index('### Gaps')][:1800]
    return (' REQUIRED JSON ROOT PROPERTIES, in addition to the requested job assessment fields: "evaluation" (OBJECT) and "global_score" (number). The exact shape is {"evaluation":{"A":"role summary","B":[{"requirement":"requirement","importance":"high","tier":"stated","jd_evidence":"exact JD excerpt","profile_evidence":"exact profile excerpt or empty","match":"strong|partial|missing|unknown"}],"C":"seniority fit","D":"advertised pay only","E":"tailoring plan","F":"interview preparation","G":"posting risks","H":"screening questions needing user input"},"global_score":3.0}. NEVER omit evaluation. A,C,D,E,F,G,H are strings; B is an array, never a Markdown table. '
            'Each B row has requirement, importance (critical/high/meaningful/low), tier (stated/structural/inferred), jd_evidence (exact JD quote), profile_evidence (exact confirmed resume/profile quote, or empty), profile_evidence_ids (array of supplied confirmed_evidence IDs), match (strong/partial/missing/unknown). Cite supporting confirmed_evidence IDs rather than paraphrasing quotes. Personal project evidence supports hands-on skills, not professional years. Prefer 8 rows, max 12 except retain every critical/high requirement. Each quote <=180 characters, requirement <=120 characters. Each A,C,D,E,F,G,H block <=35 words. Inferred requirements cannot be critical/high. Never fabricate evidence. Never apply senior-founder defaults to a graduate. Also return global_score (1-5, holistic skill/role fit; not an employer ATS result). No researched salary or external assumptions. Upstream reference methodology follows; its prose/table formatting instructions do not override the requested JSON schema: '+evidence+' Return only the compact JSON object, no Markdown report or extra keys. Entire evaluation <=1200 words.')

def evidence_catalog(profile):
    lines=[{'source':'resume','text':line.strip()} for line in profile.get('resume_text','').splitlines() if line.strip()]
    for field in ['skills','experience','education','work_history','country','authorization','sponsorship','relocation','employment_type','portfolio']:
        value=profile.get(field)
        if value is not None and value!='' and value!=[]:lines.append({'source':field,'text':value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)})
    return [{'id':f'e{i+1}','source':line['source'],'text':line['text'][:400]} for i,line in enumerate(lines[:160])]

def validated_evaluation(result, profile, job_text):
    raw=result.get('evaluation') or result.get('structured_evaluation') or result.get('career_ops_evaluation')
    if not isinstance(raw,dict) and all(k in result for k in 'ABCDEFGH'):raw={k:result[k] for k in 'ABCDEFGH'}
    if not isinstance(raw,dict):raise HTTPException(502,'The model omitted the required Career Ops report. Retry assessment; no fit result was saved.')
    rows=raw.get('B')
    if not isinstance(rows,list):raise HTTPException(502,'The model returned an invalid Career Ops requirements table. Retry assessment; no fit result was saved.')
    evidence=json.dumps(profile,ensure_ascii=False).casefold()+' '+profile.get('resume_text','').casefold()
    def norm(value):return re.sub(r'\s+',' ',value.casefold()).strip()
    evidence=norm(evidence);jd=norm(job_text);clean=[]
    catalog={entry['id']:entry for entry in evidence_catalog(profile)}
    for row in rows[:30]:
        if not isinstance(row,dict):continue
        r={k:str(row.get(k) or '')[:1800] for k in ['requirement','importance','tier','jd_evidence','profile_evidence','match']}
        refs=row.get('profile_evidence_ids')
        cited=[catalog[id]['text'] for id in refs[:3] if isinstance(id,str) and id in catalog] if isinstance(refs,list) else []
        if cited:r['profile_evidence']=' | '.join(cited)
        if r['tier'] not in ['stated','structural','inferred']:r['tier']='inferred'
        if r['importance'] not in ['critical','high','meaningful','low']:r['importance']='meaningful'
        if r['tier']=='inferred' and r['importance'] in ['critical','high']:r['importance']='meaningful'
        if r['jd_evidence'] and norm(r['jd_evidence']) not in jd:r.update(tier='inferred',importance='meaningful',jd_evidence='')
        if r['match'] not in ['strong','partial','missing','unknown']:r['match']='unknown'
        if r['profile_evidence'] and not cited and norm(r['profile_evidence']) not in evidence:r.update(profile_evidence='',match='unknown')
        if r['match'] in ['strong','partial'] and not r['profile_evidence']:r['match']='unknown'
        clean.append(r)
    clean.sort(key=lambda r:({'critical':0,'high':1,'meaningful':2,'low':3}[r['importance']],r['match']=='strong'))
    return {**{k:str(raw.get(k) or 'Not stated / not assessed')[:2000] for k in 'ACDEFGH'},'B':clean,'global_score':max(1,min(5,float(result.get('global_score',3)))),'source':'Career Ops A-H adapted for Orbit'}

# Terms of the job a fresher is willing to take on to get started: where and when they work, for how long and for
# what pay. These are the person's own choice, not claims about their skills, so a fresher accepts them. Anything
# that asks the candidate to pay (fee, deposit) is excluded: that is how job scams look.
FRESHER_TERMS=re.compile(r'\b(on-?site|in[- ]office|work from office|wfo|relocat\w*|commut\w*|based in|located in|location|city|travel\w*|'
                         r'shifts?|night|rotational|weekends?|timings?|working hours|duration|\d+[- ]months?|months? (?:internship|commitment)|full[- ]time availability|'
                         r'available (?:for|to)|availability|immediate(?:ly)? join\w*|joining|notice period|stipend|unpaid|salary|pay|paid|compensation|ctc|'
                         r'performance[- ]based|bond|service agreement|willing to|ok(?:ay)? with|open to|ready to|mentor\w*)\b',re.I)
CANDIDATE_PAYS=re.compile(r'\b(fee|fees|deposit|pay (?:us|for (?:the )?training)|registration charge|security amount)\b',re.I)

def fresher_accepts(requirement):
    return bool(FRESHER_TERMS.search(requirement or '')) and not CANDIDATE_PAYS.search(requirement or '')

def enforce_evidence_constraints(match,fresher=False):
    """A high similarity score cannot override an evidenced mandatory gap. A fresher accepts the job's own
    terms (on-site, relocation, duration, stipend, shifts); those become review notes, not blockers."""
    for row in match.get('evaluation',{}).get('B',[]):
        if row['importance']!='critical' or row['tier']!='stated' or not row['jd_evidence']:continue
        if fresher and row['match'] in ['missing','unknown'] and fresher_accepts(row['requirement']):
            match.setdefault('review_notes',[]).append('Accepted as a fresher: '+row['requirement'])
        elif row['match']=='missing':match['blockers'].append('Mandatory requirement not evidenced in profile: '+row['requirement'])
        elif row['match']=='unknown':match['unknown'].append('Mandatory requirement needs confirmation: '+row['requirement'])
    if fresher:
        # The assessment's own open questions about the job's terms are accepted the same way.
        accepted=[v for v in match['unknown'] if fresher_accepts(v.removeprefix('Mandatory requirement needs confirmation: '))]
        match['unknown']=[v for v in match['unknown'] if v not in accepted]
        notes=match.setdefault('review_notes',[])
        notes.extend(n for n in ('Accepted as a fresher: '+v.removeprefix('Mandatory requirement needs confirmation: ') for v in accepted) if n not in notes)
    match['blockers']=list(dict.fromkeys(match['blockers']));match['unknown']=list(dict.fromkeys(match['unknown']))
    if match['blockers'] or match['unknown']:match.update(eligible=False,matched=False)
    elif fresher:match.update(eligible=True,matched=True)   # fresher matching is relaxed: no score threshold, and a low fit is already a blocker
    return match
