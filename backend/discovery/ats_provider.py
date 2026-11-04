"""Official Company Career Page and ATS Public API Adapters.
Discovers and extracts validated jobs from Greenhouse, Lever, Ashby, and schema.org JobPosting JSON-LD.
"""
import html
import json
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse, parse_qs
import httpx
from bs4 import BeautifulSoup
from .base import DiscoveredJob
from .url_validator import validate_url, canonicalize_url
from ..web_researcher import HEADERS

logger = logging.getLogger(__name__)

def extract_json_ld_job(soup: BeautifulSoup, page_url: str) -> Optional[DiscoveredJob]:
    """Extract structured JobPosting metadata from HTML ld+json scripts."""
    for script in soup.find_all('script', type='application/ld+json'):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get('@graph', [data])
            else:
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue
                type_val = item.get('@type', '')
                if type_val == 'JobPosting' or 'JobPosting' in str(type_val):
                    title = str(item.get('title') or '').strip()
                    org = item.get('hiringOrganization', {})
                    company = str(org.get('name') if isinstance(org, dict) else org or '').strip()
                    if not title or not company:
                        continue

                    # Location
                    loc_val = item.get('jobLocation')
                    loc_str = 'Remote'
                    if isinstance(loc_val, dict):
                        addr = loc_val.get('address', {})
                        if isinstance(addr, dict):
                            loc_str = addr.get('addressLocality') or addr.get('addressRegion') or addr.get('addressCountry') or 'Remote'
                        elif isinstance(addr, str):
                            loc_str = addr

                    desc = item.get('description', '')
                    if desc:
                        desc_soup = BeautifulSoup(desc, 'html.parser')
                        desc = desc_soup.get_text(separator=' ').strip()

                    app_url = str(item.get('url') or page_url)
                    ext_id = f"jsonld_{hash(page_url) & 0xffffffffffff}"
                    
                    return DiscoveredJob(
                        external_id=ext_id,
                        source='Company Career',
                        title=title,
                        company=company,
                        location=loc_str,
                        country='',
                        work_mode='Remote' if 'remote' in loc_str.lower() or 'remote' in title.lower() else 'Onsite',
                        employment_type=str(item.get('employmentType') or 'Full-time'),
                        description=desc[:4000],
                        url=canonicalize_url(page_url),
                        application_url=canonicalize_url(app_url),
                        posted_at=str(item.get('datePosted') or datetime.now(timezone.utc).isoformat()),
                        verified_at=datetime.now(timezone.utc).isoformat(),
                        source_attribution='Official Career Page (JSON-LD)',
                        status='active',
                        raw_payload=item
                    )
        except Exception as e:
            logger.debug(f"JSON-LD extraction failed: {e}")
    return None

class ATSCareerProvider:
    """Discovers openings across employer applicant tracking systems and career sites."""

    @staticmethod
    def identify_ats(url: str) -> Optional[tuple[str, str, Optional[str]]]:
        """Returns (ats_name, board_token, job_id) if recognized."""
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or '').lower()
            parts = parsed.path.strip('/').split('/')
            
            # Greenhouse
            if host in ('boards.greenhouse.io', 'job-boards.greenhouse.io'):
                board = parts[0] if parts else ''
                if board == 'embed':
                    q = parse_qs(parsed.query)
                    board = q.get('for', [''])[0]
                job_id = None
                if len(parts) > 2 and parts[1] == 'jobs':
                    job_id = parts[2]
                if board:
                    return 'greenhouse', board, job_id

            # Lever
            if host in ('jobs.lever.co', 'jobs.eu.lever.co'):
                board = parts[0] if parts else ''
                job_id = parts[1] if len(parts) > 1 and re.fullmatch(r'[a-f0-9-]{36}', parts[1]) else None
                if board:
                    return 'lever', board, job_id

            # Ashby
            if host == 'jobs.ashbyhq.com':
                board = parts[0] if parts else ''
                job_id = parts[1] if len(parts) > 1 and re.fullmatch(r'[a-f0-9-]{36}', parts[1]) else None
                if board:
                    return 'ashby', board, job_id

        except Exception:
            pass
        return None

    @classmethod
    async def fetch_greenhouse_jobs(cls, board: str, limit: int = 15) -> List[DiscoveredJob]:
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        jobs: List[DiscoveredJob] = []
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
                resp = await client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    company_name = board.capitalize()
                    for item in data.get('jobs', [])[:limit]:
                        title = item.get('title', '').strip()
                        job_url = item.get('absolute_url', '')
                        if not title or not job_url:
                            continue
                        loc_dict = item.get('location', {})
                        loc_name = loc_dict.get('name', 'Remote') if isinstance(loc_dict, dict) else str(loc_dict)
                        content = item.get('content', '')
                        desc = BeautifulSoup(content, 'html.parser').get_text(separator=' ') if content else ''
                        ext_id = f"greenhouse_{item.get('id')}"
                        mode = 'Remote' if 'remote' in loc_name.lower() or 'remote' in title.lower() else 'Onsite'
                        jobs.append(DiscoveredJob(
                            external_id=ext_id,
                            source='Greenhouse',
                            title=title,
                            company=company_name,
                            location=loc_name,
                            country='',
                            work_mode=mode,
                            employment_type='Full-time',
                            description=desc[:4000],
                            url=canonicalize_url(job_url),
                            application_url=canonicalize_url(job_url),
                            posted_at=item.get('updated_at') or datetime.now(timezone.utc).isoformat(),
                            verified_at=datetime.now(timezone.utc).isoformat(),
                            source_attribution=f"Greenhouse ({company_name})",
                            status='active',
                            raw_payload=item
                        ))
        except Exception as e:
            logger.debug(f"Greenhouse board fetch error for {board}: {e}")
        return jobs

    @classmethod
    async def fetch_lever_jobs(cls, board: str, limit: int = 15) -> List[DiscoveredJob]:
        api_url = f"https://api.lever.co/v0/postings/{board}?mode=json"
        jobs: List[DiscoveredJob] = []
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
                resp = await client.get(api_url)
                if resp.status_code == 200:
                    postings = resp.json()
                    company_name = board.capitalize()
                    for item in postings[:limit]:
                        title = item.get('text', '').strip()
                        hosted_url = item.get('hostedUrl', '')
                        apply_url = item.get('applyUrl', '') or hosted_url
                        if not title or not hosted_url:
                            continue
                        cats = item.get('categories', {}) or {}
                        loc_name = cats.get('location') or 'Remote'
                        work_type = cats.get('commitment', 'Full-time')
                        desc = item.get('descriptionPlain', '') or ''
                        ext_id = f"lever_{item.get('id')}"
                        mode = 'Remote' if 'remote' in loc_name.lower() or 'remote' in title.lower() or cats.get('workplaceType') == 'remote' else 'Onsite'
                        jobs.append(DiscoveredJob(
                            external_id=ext_id,
                            source='Lever',
                            title=title,
                            company=company_name,
                            location=loc_name,
                            country='',
                            work_mode=mode,
                            employment_type=work_type,
                            description=desc[:4000],
                            url=canonicalize_url(hosted_url),
                            application_url=canonicalize_url(apply_url),
                            posted_at=datetime.fromtimestamp(item.get('createdAt', 0)/1000, tz=timezone.utc).isoformat() if item.get('createdAt') else datetime.now(timezone.utc).isoformat(),
                            verified_at=datetime.now(timezone.utc).isoformat(),
                            source_attribution=f"Lever ({company_name})",
                            status='active',
                            raw_payload=item
                        ))
        except Exception as e:
            logger.debug(f"Lever board fetch error for {board}: {e}")
        return jobs

    @classmethod
    async def fetch_ashby_jobs(cls, board: str, limit: int = 15) -> List[DiscoveredJob]:
        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{board}"
        jobs: List[DiscoveredJob] = []
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
                resp = await client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    company_name = board.capitalize()
                    for item in data.get('jobs', [])[:limit]:
                        title = item.get('title', '').strip()
                        job_url = item.get('jobUrl', '')
                        apply_url = item.get('applyUrl', '') or job_url
                        if not title or not job_url:
                            continue
                        loc_name = item.get('location', 'Remote')
                        is_remote = item.get('isRemote', False)
                        desc = item.get('descriptionHtml', '') or ''
                        desc_text = BeautifulSoup(desc, 'html.parser').get_text(separator=' ') if desc else ''
                        ext_id = f"ashby_{item.get('id')}"
                        mode = 'Remote' if is_remote or 'remote' in loc_name.lower() else 'Onsite'
                        jobs.append(DiscoveredJob(
                            external_id=ext_id,
                            source='Ashby',
                            title=title,
                            company=company_name,
                            location=loc_name,
                            country='',
                            work_mode=mode,
                            employment_type=item.get('employmentType', 'Full-time'),
                            description=desc_text[:4000],
                            url=canonicalize_url(job_url),
                            application_url=canonicalize_url(apply_url),
                            posted_at=item.get('publishedAt') or datetime.now(timezone.utc).isoformat(),
                            verified_at=datetime.now(timezone.utc).isoformat(),
                            source_attribution=f"Ashby ({company_name})",
                            status='active',
                            raw_payload=item
                        ))
        except Exception as e:
            logger.debug(f"Ashby board fetch error for {board}: {e}")
        return jobs

    @classmethod
    async def inspect_page(cls, url: str) -> Optional[DiscoveredJob]:
        """Fetch and extract job details from a specific career page URL with SSRF protection."""
        is_safe, err = validate_url(url)
        if not is_safe:
            logger.debug(f"URL rejected by SSRF guard: {url} ({err})")
            return None

        ats_info = cls.identify_ats(url)
        if ats_info:
            ats_name, board, job_id = ats_info
            if ats_name == 'greenhouse':
                jobs = await cls.fetch_greenhouse_jobs(board, limit=20)
                if job_id:
                    for j in jobs:
                        if job_id in j.external_id or job_id in j.url:
                            return j
                return jobs[0] if jobs else None
            elif ats_name == 'lever':
                jobs = await cls.fetch_lever_jobs(board, limit=20)
                if job_id:
                    for j in jobs:
                        if job_id in j.external_id or job_id in j.url:
                            return j
                return jobs[0] if jobs else None
            elif ats_name == 'ashby':
                jobs = await cls.fetch_ashby_jobs(board, limit=20)
                if job_id:
                    for j in jobs:
                        if job_id in j.external_id or job_id in j.url:
                            return j
                return jobs[0] if jobs else None

        # Generic web page extraction
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=HEADERS) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    job = extract_json_ld_job(soup, str(resp.url))
                    if job:
                        return job
                    
                    # Fallback to meta tags & title
                    page_title = soup.title.string.strip() if soup.title else ''
                    if ' - ' in page_title:
                        parts = page_title.split(' - ')
                        title = parts[0].strip()
                        company = parts[1].strip()
                    elif ' at ' in page_title:
                        parts = page_title.split(' at ')
                        title = parts[0].strip()
                        company = parts[1].strip()
                    else:
                        title = page_title
                        company = urlparse(str(resp.url)).netloc

                    if title and len(title) < 100:
                        meta_desc = soup.find('meta', {'name': 'description'}) or soup.find('meta', {'property': 'og:description'})
                        desc = meta_desc['content'].strip() if meta_desc and meta_desc.get('content') else ''
                        return DiscoveredJob(
                            external_id=f"page_{hash(str(resp.url)) & 0xffffffffffff}",
                            source='Company Career',
                            title=title,
                            company=company,
                            location='Remote' if 'remote' in title.lower() else 'Unknown',
                            country='',
                            work_mode='Remote' if 'remote' in title.lower() else 'Unknown',
                            description=desc[:2000],
                            url=canonicalize_url(str(resp.url)),
                            application_url=canonicalize_url(str(resp.url)),
                            posted_at=datetime.now(timezone.utc).isoformat(),
                            verified_at=datetime.now(timezone.utc).isoformat(),
                            source_attribution='Official Career Page',
                            status='active'
                        )
        except Exception as e:
            logger.debug(f"Direct page inspection failed for {url}: {e}")
        return None
