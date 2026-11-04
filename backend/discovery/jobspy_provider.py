"""JobSpy Multi-Board Provider Adapter.
Integrates python-jobspy to aggregate vacancies across LinkedIn, Indeed, Glassdoor, and ZipRecruiter.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from .base import BaseJobProvider, DiscoveredJob

logger = logging.getLogger(__name__)

class JobSpyProvider(BaseJobProvider):
    def __init__(self, sites: Optional[List[str]] = None):
        self._sites = sites or ["linkedin", "indeed", "glassdoor", "zip_recruiter"]

    @property
    def name(self) -> str:
        return "JobSpy"

    @property
    def capabilities(self) -> List[str]:
        return ["search", "multi_board", "filter_remote", "experience_filter"]

    async def search(self, query: str, location: str = '', filters: Optional[Dict[str, Any]] = None, limit: int = 15) -> List[DiscoveredJob]:
        filters = filters or {}
        is_remote = filters.get('is_remote', False)
        country = filters.get('country', 'USA').lower()
        if 'india' in country:
            country_code = 'india'
        elif 'united kingdom' in country or 'uk' in country:
            country_code = 'uk'
        elif 'canada' in country:
            country_code = 'canada'
        else:
            country_code = 'usa'

        results: List[DiscoveredJob] = []

        def _run_scrape():
            try:
                from jobspy import scrape_jobs
                jobs_df = scrape_jobs(
                    site_name=self._sites,
                    search_term=query,
                    location=location or ("Remote" if is_remote else ""),
                    results_wanted=min(limit, 25),
                    hours_old=filters.get('hours_old', 168), # Last 7 days default
                    country_indeed=country_code,
                    is_remote=is_remote,
                )
                return jobs_df
            except Exception as e:
                logger.warning(f"JobSpy scrape error: {e}")
                return None

        # Run scrape in background thread pool to avoid blocking async event loop
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(None, _run_scrape)

        if df is None or getattr(df, 'empty', True):
            return results

        now_iso = datetime.now(timezone.utc).isoformat()

        for _, row in df.iterrows():
            try:
                site = str(row.get('site', 'JobBoard')).capitalize()
                title = str(row.get('title', 'Unknown Title')).strip()
                company = str(row.get('company', 'Unknown Company')).strip()
                loc = str(row.get('location', location or 'Remote')).strip()
                job_url = str(row.get('job_url', '')).strip()
                if not job_url or not title or not company:
                    continue

                desc = str(row.get('description', '')).strip()
                min_amt = row.get('min_amount')
                max_amt = row.get('max_amount')
                currency = str(row.get('currency', 'USD'))
                salary_str = ''
                if min_amt and max_amt:
                    salary_str = f"{currency} {int(min_amt):,} – {int(max_amt):,}"
                elif min_amt:
                    salary_str = f"From {currency} {int(min_amt):,}"

                mode = 'Remote' if is_remote or 'remote' in loc.lower() or 'remote' in title.lower() else 'Onsite'
                if 'hybrid' in loc.lower() or 'hybrid' in title.lower():
                    mode = 'Hybrid'

                ext_id = f"{site.lower()}_{hash(job_url) & 0xffffffffffff}"

                results.append(DiscoveredJob(
                    external_id=ext_id,
                    source=site,
                    title=title,
                    company=company,
                    location=loc,
                    country=country_code.upper(),
                    work_mode=mode,
                    employment_type=str(row.get('job_type', 'Full-time')),
                    salary=salary_str,
                    description=desc,
                    url=job_url,
                    application_url=str(row.get('job_url_direct') or job_url),
                    posted_at=str(row.get('date_posted') or now_iso),
                    verified_at=now_iso,
                    source_attribution=site,
                    application_method='External',
                    raw_payload=dict(row)
                ))
            except Exception as row_err:
                logger.debug(f"Row conversion error: {row_err}")
                continue

        return results[:limit]
