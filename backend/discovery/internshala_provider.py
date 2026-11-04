"""Internshala Public Jobs & Internships Provider Adapter.
Discovers live fresher jobs and internships directly from Internshala public listings.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup
from .base import BaseJobProvider, DiscoveredJob
from ..web_researcher import HEADERS

logger = logging.getLogger(__name__)

def slugify(text: str) -> str:
    """Convert a role or location string to an Internshala URL slug."""
    text = re.sub(r'[^a-zA-Z0-9\s-]', '', text.lower())
    return re.sub(r'[\s_]+', '-', text).strip('-')

class InternshalaProvider(BaseJobProvider):
    @property
    def name(self) -> str:
        return "Internshala"

    @property
    def capabilities(self) -> List[str]:
        return ["search", "fresher_jobs", "internships", "filter_remote"]

    async def search(self, query: str, location: str = '', filters: Optional[Dict[str, Any]] = None, limit: int = 15) -> List[DiscoveredJob]:
        filters = filters or {}
        is_remote = filters.get('is_remote', False)
        country = filters.get('country', 'India').lower()

        # Internshala primarily operates for India and Remote positions
        if 'india' not in country and not is_remote and country:
            return []

        role_slug = slugify(query) if query else 'software-development'
        loc_slug = slugify(location) if location and not is_remote else ''

        urls = []
        if is_remote:
            urls.append(f"https://internshala.com/jobs/work-from-home/{role_slug}-jobs/")
            urls.append(f"https://internshala.com/internships/work-from-home/{role_slug}-internships/")
        elif loc_slug:
            urls.append(f"https://internshala.com/jobs/{role_slug}-jobs-in-{loc_slug}/")
            urls.append(f"https://internshala.com/internships/{role_slug}-internship-in-{loc_slug}/")
        else:
            urls.append(f"https://internshala.com/jobs/{role_slug}-jobs/")
            urls.append(f"https://internshala.com/internships/{role_slug}-internships/")

        results: List[DiscoveredJob] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=HEADERS) as client:
            for url in urls:
                if len(results) >= limit:
                    break
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, 'html.parser')
                    cards = soup.find_all(class_='individual_internship') or soup.find_all(class_='container-fluid')
                    
                    for c in cards:
                        if len(results) >= limit:
                            break

                        # Title & link
                        title_el = c.find('a', class_='job-title-href') or c.find('h3', class_='job-internship-name') or c.find('a')
                        if not title_el:
                            continue
                        
                        href = title_el.get('href', '')
                        if not href or ('/job/detail/' not in href and '/internship/detail/' not in href):
                            continue

                        full_url = urljoin('https://internshala.com', href)
                        title = title_el.get_text(strip=True)

                        # Company name
                        company_el = c.find('p', class_='company-name') or c.find('a', class_='link_display_like_text')
                        company = company_el.get_text(strip=True) if company_el else 'Company on Internshala'

                        # Location
                        loc_el = c.find('a', class_='location_link') or c.find(class_='row-1-item')
                        loc_text = loc_el.get_text(strip=True) if loc_el else (location or 'India')
                        
                        mode = 'Remote' if is_remote or 'work from home' in loc_text.lower() else 'Onsite'
                        if 'hybrid' in loc_text.lower():
                            mode = 'Hybrid'

                        # Salary / CTC
                        stipend_el = c.find(class_='stipend') or c.find(class_='salary')
                        salary = stipend_el.get_text(strip=True) if stipend_el else 'Competitive'

                        is_internship = '/internship/detail/' in href
                        emp_type = 'Internship' if is_internship else 'Full-time'

                        job_id_match = re.search(r'detail/(?:[a-zA-Z0-9_-]+-)?(\d+)', href)
                        ext_id = f"internshala_{job_id_match.group(1)}" if job_id_match else f"internshala_{hash(full_url) & 0xffffffffffff}"

                        results.append(DiscoveredJob(
                            external_id=ext_id,
                            source='Internshala',
                            title=title,
                            company=company,
                            location=loc_text,
                            country='India',
                            work_mode=mode,
                            employment_type=emp_type,
                            salary=salary,
                            description=f"{title} position at {company}. Location: {loc_text}. {salary}.",
                            url=full_url,
                            application_url=full_url,
                            posted_at=now_iso,
                            verified_at=now_iso,
                            source_attribution='Internshala',
                            application_method='Internshala Apply',
                            raw_payload={'internshala_href': href, 'is_internship': is_internship}
                        ))
                except Exception as e:
                    logger.debug(f"Internshala fetch error for {url}: {e}")
                    continue

        return results[:limit]
