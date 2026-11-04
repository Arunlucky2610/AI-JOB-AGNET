import hashlib, json, re
from datetime import datetime, timedelta, timezone

MODEL = 'deepseek/deepseek-v4-flash-0731'
DEFAULT_SETTINGS = {'source_focus': 'linkedin', 'mode': 'each', 'daily_limit': 3, 'threshold': None, 'auto_enabled': False}
EMPTY_PROFILE = {'name':'','email':'','phone':'','roles':'','country':'','locations':'','work_modes':['Remote','Hybrid'],'experience':0,'skills':'','salary':'','currency':'USD','pay_period':'year','authorization':'','sponsorship':'','notice':'','portfolio':'','linkedin':'','github':'','website':'','resume_text':'','screening':'','excluded_companies':'','strict_location':True,'strict_country':True,'strict_mode':True,'confirmed':False}
EMPTY_PROFILE.update({
    'address':'','current_location':'','summary':'','certifications':[],'projects':[],
    'preferred_industries':'','preferred_companies':'','portfolio_url':'','github_url':'','linkedin_url':'',
    'education':[],'work_history':[],'cover_letter_text':'','availability':'','relocation':'',
    'employment_type':'Full-time','eligibility':'','age_confirmed':False,
    'eeo_gender':'Prefer not to say','eeo_ethnicity':'Prefer not to say','eeo_disability':'Prefer not to say',
    'eeo_veteran':'Prefer not to say','no_experience':False,'resume_filename':'','career_level':'','skill_years':{}
})

def extract_candidate_links(profile):
    """Safely discover confirmed candidate links from profile fields or confirmed resume text."""
    links = {}
    resume_text = str((profile or {}).get('resume_text') or '')
    
    # LinkedIn profile URL
    li = str((profile or {}).get('linkedin') or (profile or {}).get('linkedin_url') or '').strip()
    if not li and 'linkedin.com' in str((profile or {}).get('portfolio') or '').lower():
        li = str(profile.get('portfolio')).strip()
    if not li and resume_text:
        m = re.search(r'(?:https?://)?(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_\-\.\/]+)', resume_text, re.I)
        if m:
            li = m.group(0).rstrip('|/;, \t\n')
    if li:
        if not li.startswith('http'):
            li = 'https://' + li
        links['linkedin'] = li
        links['linkedin_url'] = li
        links['profile_url'] = li
        
    # GitHub profile URL
    gh = str((profile or {}).get('github') or (profile or {}).get('github_url') or '').strip()
    if not gh and 'github.com' in str((profile or {}).get('portfolio') or '').lower():
        gh = str(profile.get('portfolio')).strip()
    if not gh and resume_text:
        m = re.search(r'(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9_\-\.\/]+)', resume_text, re.I)
        if m:
            gh = m.group(0).rstrip('|/;, \t\n')
    if gh:
        if not gh.startswith('http'):
            gh = 'https://' + gh
        links['github'] = gh
        links['github_url'] = gh
        
    # Portfolio / personal website
    pf = str((profile or {}).get('portfolio') or (profile or {}).get('website') or '').strip()
    if pf:
        if not pf.startswith('http') and not pf.startswith('mailto:'):
            pf = 'https://' + pf
        links['portfolio'] = pf
        links['website'] = pf
        
    return links

def parse_salary(val):
    """Safely parse salary input into (raw_formatted, clean_numeric_digits).
    Supports LPA/Lakhs, K notation, comma-separated amounts, currency symbols, and ranges.
    Never hallucinates or guesses unprovided values."""
    s = str(val or '').strip()
    if not s:
        return None, None
    r_match = re.search(r"(?:[₹$€£]|INR\s*|USD\s*)?([0-9.,]+)\s*(k|lpa|lakhs?)?\s*[-–—to]+\s*(?:[₹$€£]|INR\s*|USD\s*)?([0-9.,]+)\s*(k|lpa|lakhs?)?", s, re.I)
    if r_match:
        part1 = r_match.group(1).replace(",", "")
        suffix = (r_match.group(2) or r_match.group(4) or "").lower()
        try:
            num = float(part1)
            if suffix == "k" or "k" in s.lower():
                num *= 1000
            elif "lpa" in s.lower() or "lakh" in s.lower():
                num *= 100000
            return s, str(int(num))
        except (ValueError, TypeError):
            pass
    lpa_match = re.search(r"([0-9.]+)\s*(?:lpa|lakhs?|lac|lacs)\b", s, re.I)
    if lpa_match:
        try:
            return s, str(int(float(lpa_match.group(1)) * 100000))
        except (ValueError, TypeError):
            pass
    k_match = re.search(r"([0-9.]+)\s*k\b", s, re.I)
    if k_match:
        try:
            return s, str(int(float(k_match.group(1)) * 1000))
        except (ValueError, TypeError):
            pass
    clean = re.sub(r"[^\d.]", "", s)
    if clean:
        try:
            return s, str(int(float(clean)))
        except (ValueError, TypeError):
            pass
    return s, s

def career_level(profile):
    """'intern', 'fresher' or 'experienced'. The person's own choice when given, otherwise worked out from their experience."""
    chosen=str(profile.get('career_level') or '').strip().lower()
    for level in ('intern','fresher','experienced'):
        if chosen.startswith(level):return level
    try:years=float(profile.get('experience') or 0)
    except (TypeError,ValueError):years=0
    return 'fresher' if profile.get('no_experience') or years<=1 else 'experienced'
DEMO_PROFILE = {**EMPTY_PROFILE, 'name':'Alex Morgan','email':'alex@example.com','roles':'Frontend Engineer, Software Engineer','country':'United States','locations':'New York, San Francisco','experience':3,'skills':'React, TypeScript, JavaScript, CSS, Next.js, accessibility, testing','salary':'100000–140000','authorization':'Authorized to work in the United States','sponsorship':'No','notice':'2 weeks','portfolio':'https://example.com','confirmed':True,'resume_text':'Alex Morgan\nFrontend Engineer\nExperience: Frontend Engineer at Example Studio, 2023–present. Built accessible React and TypeScript interfaces. Improved component testing and worked with designers on a shared component library.\nEducation: BS Computer Science, 2023.\nSkills: React, TypeScript, JavaScript, CSS, Next.js, accessibility, testing.'}

def fingerprint(package):
    return hashlib.sha256(json.dumps(package, sort_keys=True).encode()).hexdigest()

def evaluate(profile, job, threshold=70):
    text = (job.get('title','')+' '+job.get('description','')).lower()
    skills = [s.strip() for s in profile.get('skills','').split(',') if s.strip()]
    matched = [s for s in skills if s.lower() in text]
    roles = [r.strip().lower() for r in profile.get('roles','').split(',') if r.strip()]
    role_match = job.get('role_verified') is True or any(r in job.get('title','').lower() for r in roles)
    score = min(100, round(65 * len(matched)/max(len(skills),1) + (25 if role_match else 5) + (10 if job.get('mode') in profile.get('work_modes',[]) else 0)))
    blockers = []
    if roles and not role_match: blockers.append('Target role does not match')
    unknown = []
    if job.get('company','').lower() in [x.strip().lower() for x in profile.get('excluded_companies','').split(',') if x.strip()]: blockers.append('Company excluded in your preferences')
    if profile.get('strict_mode') and job.get('mode') not in profile.get('work_modes',[]):
        (unknown if job.get('mode') == 'Unknown' else blockers).append('Work mode is unknown' if job.get('mode') == 'Unknown' else 'Work mode does not match')
    # Independent toggles: a person open to any city can still require the right country (visa/authorization
    # usually depends on it), and one open to any country at all skips both, since neither is meaningful then.
    if profile.get('strict_country', True):
        if not job.get('country'): unknown.append('Country eligibility needs confirmation')
        elif profile.get('country','').strip().casefold() != job.get('country','').strip().casefold(): blockers.append('Target country does not match')
    if profile.get('strict_country', True) and profile.get('strict_location'):
        locations = [s.strip().lower() for s in profile.get('locations','').split(',') if s.strip()]
        if job.get('mode') != 'Remote' and locations and not any(s in job.get('location','').lower() for s in locations): blockers.append('Preferred location does not match')
    if job.get('min_experience') is None: unknown.append('Required experience needs confirmation')
    elif float(profile.get('experience',0)) < job['min_experience']: blockers.append('Required experience exceeds your profile')
    if not job.get('authorization_verified'): unknown.append('Work authorization requirements need confirmation')
    eligible = not blockers and not unknown
    return {'score':score, 'matched_skills':matched, 'missing_skills':[s for s in job.get('skills',[]) if s.lower() not in profile.get('skills','').lower()], 'blockers':blockers, 'unknown':unknown,'eligible':eligible,'matched':eligible and score >= threshold, 'method':'Rules + keyword coverage' }

def demo_jobs():
    rows = [('Linear','Frontend Engineer','Remote','Ashby',['React','TypeScript','CSS'], '#c8bbfc'),('Vercel','Software Engineer, Dashboard','Remote','Greenhouse',['React','Next.js','TypeScript'],'#ededed'),('Notion','Frontend Engineer, Product','Hybrid','Ashby',['React','TypeScript','accessibility'],'#e6dcc6'),('Figma','Software Engineer, Web','Hybrid','Greenhouse',['React','TypeScript','testing'],'#ffb6a2'),('Ramp','Frontend Engineer','Remote','Ashby',['React','TypeScript','JavaScript'],'#e2f998'),('Stripe','Senior Backend Engineer','Onsite','Greenhouse',['Java','Go','SQL'],'#cabfff'),('Canva','Frontend Engineer','Remote','Workday',['React','CSS','accessibility'],'#9ae9d7'),('Duolingo','Software Engineer','Hybrid','Greenhouse',['React','JavaScript','testing'],'#b5e984'),('Miro','Product Designer','Hybrid','LinkedIn',['Figma','Research'],'#f6dc79'),('Webflow','Frontend Engineer','Remote','Ashby',['React','TypeScript','CSS'],'#9bbdfd'),('Intercom','Software Engineer','Remote','Indeed',['React','TypeScript','testing'],'#b4d3ff'),('Airtable','Frontend Engineer','Hybrid','Glassdoor',['React','TypeScript','accessibility'],'#ffcea5')]
    jobs=[]
    for i,(company,title,mode,source,skills,color) in enumerate(rows):
        skills_text=', '.join(dict.fromkeys(skills + ['React','TypeScript','JavaScript','CSS']))
        jobs.append({'title':title,'company':company,'mode':mode,'source':source,'skills':skills,'color':color,'location':'United States' if mode=='Remote' else 'New York, United States','country':'United States','salary':'$110k – $145k','min_experience':5 if i==5 else 2,'authorization_verified':True,'description':f'This is a fictional demonstration listing, not a current vacancy.\n\nAs a {title}, you will build thoughtful products with a collaborative team. Work with {skills_text}.\n\nResponsibilities\n• Build accessible, reliable product experiences.\n• Collaborate with design and engineering.\n• Write maintainable code and meaningful tests.\n\nRequirements\n2+ years of relevant experience and strong communication skills.','url':'','demo':True,'posted':(datetime.now(timezone.utc)-timedelta(days=i%7)).isoformat()})
    return jobs
