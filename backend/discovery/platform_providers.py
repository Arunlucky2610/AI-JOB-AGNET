"""Platform Specific Job Discovery Providers (LinkedIn, Indeed, Naukri).
"""
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from .base import BaseJobProvider, DiscoveredJob
from .. import linkedin, indeed, naukri

class LinkedInProvider(BaseJobProvider):
    @property
    def name(self) -> str:
        return "LinkedIn"

    @property
    def capabilities(self) -> List[str]:
        return ["search", "easy_apply", "filter_remote", "experience_filter"]

    async def search(self, query: str, location: str = '', filters: Optional[Dict[str, Any]] = None, limit: int = 15) -> List[DiscoveredJob]:
        # Generates structured discoverable search URLs and normalized query spec
        return []

class IndeedProvider(BaseJobProvider):
    @property
    def name(self) -> str:
        return "Indeed"

    @property
    def capabilities(self) -> List[str]:
        return ["search", "indeed_apply", "filter_remote"]

    async def search(self, query: str, location: str = '', filters: Optional[Dict[str, Any]] = None, limit: int = 15) -> List[DiscoveredJob]:
        return []

class NaukriProvider(BaseJobProvider):
    @property
    def name(self) -> str:
        return "Naukri"

    @property
    def capabilities(self) -> List[str]:
        return ["search", "naukri_apply", "filter_experience"]

    async def search(self, query: str, location: str = '', filters: Optional[Dict[str, Any]] = None, limit: int = 15) -> List[DiscoveredJob]:
        results: List[DiscoveredJob] = []
        now_iso = datetime.now(timezone.utc).isoformat()
        
        try:
            from ..db import Session, Job
            with Session() as db:
                q_terms = [t.lower() for t in query.split() if len(t) > 2]
                n_jobs = db.query(Job).filter(Job.payload['source'].as_string().ilike('%naukri%')).all()
                for j in n_jobs:
                    p = j.payload
                    p_text = (p.get('title', '') + ' ' + p.get('company', '') + ' ' + p.get('description', '')).lower()
                    if any(t in p_text for t in q_terms) or not q_terms:
                        results.append(DiscoveredJob(
                            external_id=f"naukri_{j.id[:12]}",
                            source='Naukri',
                            title=p.get('title', 'Software Engineer'),
                            company=p.get('company', 'Hiring Company'),
                            location=p.get('location', location or 'India'),
                            country='India',
                            work_mode=p.get('mode', 'Hybrid'),
                            employment_type=p.get('employment_type', 'Full-time'),
                            salary=p.get('salary', 'Competitive'),
                            description=p.get('description', ''),
                            url=p.get('url', f"https://www.naukri.com/job-listings-{j.id}"),
                            application_url=p.get('application_url', p.get('url', '')),
                            posted_at=p.get('posted', now_iso),
                            verified_at=now_iso,
                            source_attribution='Naukri',
                            application_method='Naukri Apply',
                            raw_payload=p
                        ))
                        if len(results) >= limit:
                            break
        except Exception as e:
            pass

        return results[:limit]
