"""Conservative local extraction. Unrecognized facts stay blank for review."""
import re

def clean_skills(text):
    """A comma list from a resume skills section: no 'Frontend:' labels, bullets, empties or repeats. Mirrors parseSkillList in app/profile-logic.ts."""
    out=[];seen=set()
    for raw in re.split(r'[\n;|]+|,(?![^(]*\))',text or ''):
        item=re.sub(r'^(?:skills?|technical skills|competencies)\s*:?\s*','',raw.strip(),flags=re.I)
        labelled=re.match(r'^[A-Za-z][A-Za-z &/+.-]{1,40}:\s*(.+)$',item)
        if labelled:item=labelled.group(1)
        item=re.sub(r'^[-•·*\s]+','',item);item=re.sub(r'[-•·*\s.,;:]+$','',item).strip()
        if not item or len(item)>60 or item.casefold() in seen:continue
        seen.add(item.casefold());out.append(item)
    return out

def extract_profile(text):
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    result={}
    email=re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text)
    phone=re.search(r'(?<!\w)(?:\+\d{1,3}[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}(?!\w)',text)
    if email:result['email']=email.group()
    if phone:result['phone']=phone.group().strip()
    if lines and re.fullmatch(r'[A-Za-zÀ-ž]+(?:[ .\'-]+[A-Za-zÀ-ž]+){1,4}',lines[0]) and not re.search(r'resume|curriculum|engineer|designer',lines[0],re.I):result['name']=lines[0]
    url=re.search(r'https?://(?:www\.)?(?:github\.com|linkedin\.com/in|[\w.-]+\.(?:dev|io|me))/[^\s,]*',text)
    if url:result['portfolio']=url.group()
    
    li_m=re.search(r'https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9_\-\.\/]+',text)
    if li_m:result['linkedin']=li_m.group().rstrip('|/;, \t\n');result['linkedin_url']=result['linkedin']
    
    gh_m=re.search(r'https?://(?:www\.)?github\.com/[A-Za-z0-9_\-\.\/]+',text)
    if gh_m:result['github']=gh_m.group().rstrip('|/;, \t\n');result['github_url']=result['github']

    section=None;sections={'education':[],'work':[],'skills':[],'summary':[],'projects':[],'certifications':[]}
    for line in lines:
        if re.match(r'^(education|academic background)\b',line,re.I):section='education'
        elif re.match(r'^(work experience|professional experience|employment|experience)\b',line,re.I):section='work'
        elif re.match(r'^(technical skills|skills|competencies)\b',line,re.I):section='skills'
        elif re.match(r'^(summary|professional summary|about me|profile)\b',line,re.I):section='summary'
        elif re.match(r'^(projects|personal projects|key projects)\b',line,re.I):section='projects'
        elif re.match(r'^(certifications|licenses & certifications|certificates)\b',line,re.I):section='certifications'
        elif re.match(r'^(awards|interests|languages|publications)\s*:?$',line,re.I):section=None
        if section:sections[section].append(line)
    
    if sections['summary']:
        summary_lines=[l for l in sections['summary'] if not re.match(r'^(summary|professional summary|about me|profile)\b',l,re.I)]
        if summary_lines:result['summary']=' '.join(summary_lines[:5]).strip()
        
    if sections['projects']:
        projects=[]
        curr_proj=None
        for pline in sections['projects']:
            if re.match(r'^(projects|personal projects|key projects)\b',pline,re.I):continue
            if pline.startswith(('•','-','*')) and curr_proj:
                curr_proj['description']=(curr_proj['description']+' '+pline.lstrip('•-* ')).strip()
            elif len(pline)<80 and not pline.endswith('.'):
                if curr_proj:projects.append(curr_proj)
                curr_proj={'name':pline.strip(),'description':'','url':'','technologies':''}
            elif curr_proj:
                curr_proj['description']=(curr_proj['description']+' '+pline).strip()
        if curr_proj:projects.append(curr_proj)
        if projects:result['projects']=projects[:5]

    if sections['certifications']:
        certs=[]
        for cline in sections['certifications']:
            if re.match(r'^(certifications|licenses & certifications|certificates)\b',cline,re.I):continue
            clean_c=re.sub(r'^[-•*]\s*','',cline).strip()
            if clean_c and len(clean_c)>3:
                certs.append({'name':clean_c,'issuer':'','year':''})
        if certs:result['certifications']=certs[:6]
    if sections['skills']:
        skills=clean_skills(chr(10).join(sections['skills']))
        if skills:result['skills']=', '.join(skills)
    education=[]
    for line in sections['education']:
        degree=re.search(r'\b(Bachelor(?:[’\']s)?|Master(?:[’\']s)?|PhD|Ph\.D\.?|BS|BSc|B\.Sc|BA|BTech|B\.Tech|MSc|MS|MBA|Associate|Diploma)\b',line,re.I)
        if degree:
            year=re.search(r'\b(19\d{2}|20\d{2})\b',line)
            major=re.search(r'(?:in|of)\s+([A-Za-z &]+?)(?:,|\||\d|$)',line,re.I)
            school=re.search(r'(?:at|from|,|\|)\s*([^|,]*(?:University|College|Institute)[^|,]*)',line,re.I)
            d=degree.group().lower();kind='Bachelor’s degree' if d.startswith(('b','bachelor')) else 'Master’s degree' if d.startswith(('m','master')) else 'Doctorate' if d.startswith('ph') else 'Associate degree' if d.startswith('associate') else 'Diploma'
            education.append({'degree':kind,'school':school.group(1).strip() if school else '', 'year':year.group() if year else '', 'major':major.group(1).strip() if major else ''})
    if education:result['education']=education
    work=[]
    for i,line in enumerate(sections['work']):
        role=re.search(r'(?:Experience:\s*)?(.+?)\s+(?:at|@)\s+([^,|]+)',line,re.I)
        if role:
            dates=re.search(r'\b(20\d{2}|19\d{2})(?:-(\d{2}))?\s*[–—-]\s*(present|current|20\d{2}|19\d{2})(?:-(\d{2}))?',line,re.I)
            responsibilities=line[role.end():].strip(' ,.-') if not dates else line[dates.end():].strip(' .,-')
            rest=[]
            for next_line in sections['work'][i+1:]:
                if re.search(r'\s(?:at|@)\s',next_line):break
                rest.append(next_line)
            work.append({'title':role.group(1).strip(),'company':role.group(2).strip(),'start':f'{dates.group(1)}-{dates.group(2) or "01"}-01' if dates else '', 'end':f'{dates.group(3)}-{dates.group(4) or "01"}-01' if dates and dates.group(3).isdigit() else '', 'current':bool(dates and not dates.group(3).isdigit()),'responsibilities':'\n'.join([responsibilities,*rest]).strip()})
    if work:result['work_history']=work
    return {'fields':result,'notes':['Extracted locally without an LLM. Review every suggestion. Unrecognized information is left blank.','Year-only employment dates use January 1 as a placeholder; correct them before confirming.']}
