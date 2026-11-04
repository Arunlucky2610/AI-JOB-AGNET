"""Free checks on a job posting's text, before any model is called.

The experience check reads the years the posting asks of the candidate. It is deliberately conservative: a
sentence that looks like company boasting ("we have 15 years of experience") or an optional extra ("5+ years
preferred") is ignored, and when nothing is clear it says nothing, so Jev and DeepSeek still decide.
"""
import re

RANGE=re.compile(r'(?<![\d.])(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b',re.I)
PLUS=re.compile(r'(?<![\d.])(\d{1,2})\s*\+\s*(?:years?|yrs?)\b',re.I)
MINIMUM=re.compile(r'\b(?:minimum|min\.?|at\s*least)\s*(?:of\s*)?(\d{1,2})\s*(?:\+\s*)?(?:years?|yrs?)\b',re.I)
PLAIN=re.compile(r'(?<![\d.])(\d{1,2})\s*(?:years?|yrs?)\s*(?:of\s*)?(?:(?:relevant|professional|hands[- ]on|working|industry|proven|total|prior|practical|solid|real[- ]world)\s+)*(?:work\s+)?(?:experience|exp\b)',re.I)
EXPERIENCE=re.compile(r'experience|\bexp\b',re.I)
# Sentences about the employer, not the candidate, or requirements that are only a wish.
COMPANY=re.compile(r"\b(we\s+(?:have|are|been)|our\s+(?:team|company|firm|clients?|experts?|engineers?)|founded|established|since\s+\d{4}|for\s+over|over\s+\d+\s+years|track\s+record|clients?|customers?|industry\s+leader|years\s+in\s+(?:business|the\s+industry))\b",re.I)
OPTIONAL=re.compile(r'\b(preferred|preferably|desirable|nice\s+to\s+have|a\s+plus|bonus|good\s+to\s+have|advantage|optional|not\s+mandatory|not\s+required)\b',re.I)
SPLIT=re.compile(r'[\n\r•·▪●;]+|(?<=[a-z0-9\)])\.\s+(?=[A-Z])')

def _minimum_in(fragment):
    """The smallest number of years this one sentence asks for, or None."""
    found=[]
    for match in RANGE.finditer(fragment):found.append(min(int(match.group(1)),int(match.group(2))))
    for pattern in (MINIMUM,PLUS,PLAIN):
        for match in pattern.finditer(fragment):found.append(int(match.group(1)))
    return min(found) if found else None

def years_required(text):
    """The minimum years of experience the posting asks of the candidate, or None when it does not say clearly.

    Several requirements (per-skill lines) give the smallest one: the candidate only needs to satisfy the lowest
    general bar for the posting to be plausible, and a wrong 'too senior' verdict costs a real opportunity."""
    values=[]
    for fragment in SPLIT.split(text or ''):
        if not EXPERIENCE.search(fragment) or COMPANY.search(fragment) or OPTIONAL.search(fragment):continue
        value=_minimum_in(fragment)
        if value is not None and 0<=value<=40:values.append(value)
    return min(values) if values else None

def experience_skip_reason(text,candidate_years):
    """Why the posting asks for more experience than the candidate has, or None."""
    try:have=float(candidate_years or 0)
    except (TypeError,ValueError):have=0
    need=years_required(text)
    if need is not None and need>have:
        return f'the posting asks for {need}+ years of experience and your profile has {have:g}.'
    return None

def posting_text(page_text,limit=6000):
    """Just the vacancy: the 'About the job' section when the page has one, else the whole page text."""
    from .jev import ABOUT
    match=ABOUT.search(page_text or '')
    body=match.group(1) if match and match.group(1).strip() else page_text or ''
    return re.sub(r'[ \t]+',' ',body).strip()[:limit]
