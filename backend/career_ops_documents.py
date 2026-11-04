"""HTML/PDF renderer using the pinned Career Ops templates, with escaped facts."""
import html, re
import hashlib, asyncio
from pathlib import Path
from .career_ops import UPSTREAM
_pdf_locks={}

SECTIONS={'SUMMARY','SKILLS','PROJECTS','EXPERIENCE','EDUCATION','CERTIFICATIONS','AWARDS','INTERESTS','PROFESSIONAL SUMMARY','WORK EXPERIENCE','TECHNICAL SKILLS'}

def paragraphs(lines):
    return ''.join('<p>'+html.escape(re.sub(r'^[-*]\s+','• ',line))+'</p>' for line in lines)

def document_html(text,kind,profile,job):
    template=(UPSTREAM/'templates'/('cv-template.html' if kind=='resume' else 'cover-letter-template.html')).read_text(encoding='utf-8')
    values={'LANG':'en','PAGE_WIDTH':'100%','NAME':html.escape(profile.get('name','')),'PHONE':html.escape(profile.get('phone','')),'EMAIL':html.escape(profile.get('email','')),'LOCATION':html.escape(profile.get('locations','')),'LINKEDIN_URL':'','LINKEDIN_DISPLAY':'','PORTFOLIO_URL':'','PORTFOLIO_DISPLAY':html.escape(profile.get('portfolio',''))}
    lines=[re.sub(r'^#{1,6}\s*','',l.strip()).replace('**','') for l in text.splitlines() if l.strip()]
    if kind=='resume':
        groups={};current='SUMMARY';start=1 if lines and lines[0].casefold()==profile.get('name','').casefold() else 0
        for line in lines[start:]:
            if line.upper() in SECTIONS:
                current={'PROFESSIONAL SUMMARY':'SUMMARY','WORK EXPERIENCE':'EXPERIENCE','TECHNICAL SKILLS':'SKILLS'}.get(line.upper(),line.upper());continue
            # Contact details have their own header, not the professional summary.
            if current=='SUMMARY' and ('@' in line or (profile.get('phone') and profile['phone'] in line)):continue
            groups.setdefault(current,[]).append(line)
        for section in ['SUMMARY','COMPETENCIES','EXPERIENCE','PROJECTS','EDUCATION','CERTIFICATIONS','AWARDS','INTERESTS','SKILLS']:
            content=paragraphs(groups.get(section,[]));values['SECTION_'+section]=section.title();values['SUMMARY_TEXT' if section=='SUMMARY' else section]=content
            if not content:
                template=re.sub(r'<div class="section">\s*<div class="section-title">\{\{SECTION_'+section+r'\}\}</div>\s*(?:<div class="[^"]+">\s*)?\{\{[A-Z_]+\}\}\s*(?:</div>\s*)?</div>', '',template,flags=re.S)
        # All user links are displayed as text: no arbitrary hyperlinks/network loads.
        contact=html.escape(' | '.join(filter(None,[profile.get('phone'),profile.get('email'),profile.get('portfolio'),profile.get('locations')])))
        template=re.sub(r'<div class="contact-row">.*?</div>','<div class="contact-row">'+contact+'</div>',template,flags=re.S)
    else:
        values.update({'CONTACT_LINE':html.escape(' | '.join(filter(None,[profile.get('email'),profile.get('phone'),profile.get('locations')]))),'ROLE_TITLE':html.escape(job.get('title','')),'DATELINE':html.escape(job.get('company','')),'OPENING':'','PROFILE_INTRO':'','ACHIEVEMENTS_BLOCK':paragraphs(lines),'SIGNATURE_BLOCK':''})
        template=template.replace('<p>{{OPENING}}</p>','').replace('<p>{{PROFILE_INTRO}}</p>','')
    rendered=re.sub(r'\{\{([A-Z_]+)\}\}',lambda m:values.get(m.group(1),''),template)
    rendered=rendered.replace('</style>','p{margin:0 0 6px;overflow-wrap:anywhere}.section{break-inside:auto}.section-title{break-after:avoid} .separator:empty{display:none}@page{size:A4;margin:16mm} body{padding:24px!important}</style>')
    return rendered

async def pdf_bytes(text,kind,profile,job):
    content=document_html(text,kind,profile,job)
    digest=hashlib.sha256(content.encode()).hexdigest()
    cache=Path(__file__).resolve().parent.parent/'data'/'rendered'/digest/(kind+'.pdf')
    async with _pdf_locks.setdefault(digest,asyncio.Lock()):
        if cache.exists():return cache.read_bytes()
        data=await _render_pdf(content)
        cache.parent.mkdir(parents=True,exist_ok=True);cache.write_bytes(data)
        return data

async def _render_pdf(content):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        # Uses the local Edge engine; never sends candidate data to an external service.
        browser=await p.chromium.launch(channel='msedge',headless=True)
        try:
            page=await browser.new_page()
            await page.route('**/*',lambda route:route.abort())
            await page.set_content(content,wait_until='domcontentloaded')
            return await page.pdf(format='A4',print_background=True,prefer_css_page_size=True)
        finally:await browser.close()
