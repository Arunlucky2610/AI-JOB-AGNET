"""Job Listing Freshness and Real-Time Verification.
Validates whether a discovered job posting is still active, expired, or closed.
"""
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse
import httpx
from .url_validator import validate_url
from .ats_provider import ATSCareerProvider
from ..web_researcher import HEADERS

logger = logging.getLogger(__name__)

async def verify_job_freshness(url: str, source: str = '') -> dict:
    """Verify if a job listing is active, closed, or inaccessible.
    
    Returns:
        {
            'status': 'active' | 'possibly_active' | 'closed' | 'expired' | 'inaccessible' | 'unverified',
            'verified_at': iso_timestamp,
            'reason': str
        }
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    if not url:
        return {'status': 'unverified', 'verified_at': now_iso, 'reason': 'No URL provided'}

    is_safe, err = validate_url(url)
    if not is_safe:
        return {'status': 'inaccessible', 'verified_at': now_iso, 'reason': f'URL validation failed: {err}'}

    # 1. ATS Public API Verification
    ats_info = ATSCareerProvider.identify_ats(url)
    if ats_info:
        ats_name, board, job_id = ats_info
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=HEADERS) as client:
                if ats_name == 'greenhouse' and job_id:
                    resp = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}")
                    if resp.status_code == 200:
                        return {'status': 'active', 'verified_at': now_iso, 'reason': 'Verified open via Greenhouse API'}
                    elif resp.status_code in (404, 410):
                        return {'status': 'closed', 'verified_at': now_iso, 'reason': 'Greenhouse API confirms posting closed/removed'}
                elif ats_name == 'lever' and job_id:
                    resp = await client.get(f"https://api.lever.co/v0/postings/{board}/{job_id}")
                    if resp.status_code == 200:
                        return {'status': 'active', 'verified_at': now_iso, 'reason': 'Verified open via Lever API'}
                    elif resp.status_code in (404, 410):
                        return {'status': 'closed', 'verified_at': now_iso, 'reason': 'Lever API confirms posting closed/removed'}
        except Exception as e:
            logger.debug(f"ATS verification network check error: {e}")

    # 2. General HTTP Verification
    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code in (404, 410):
                return {'status': 'closed', 'verified_at': now_iso, 'reason': f'HTTP {resp.status_code} Not Found'}
            if resp.status_code == 200:
                body_lower = resp.text.lower()
                # Check for explicit closed keywords
                closed_indicators = [
                    'this job has expired', 'this job is no longer available',
                    'this position has been filled', 'job posting is closed',
                    'no longer accepting applications', 'posting expired'
                ]
                if any(ind in body_lower for ind in closed_indicators):
                    return {'status': 'closed', 'verified_at': now_iso, 'reason': 'Posting contains explicit closure notice'}

                # Check if redirected back to careers index
                orig_path = urlparse(url).path.rstrip('/')
                final_path = urlparse(str(resp.url)).path.rstrip('/')
                if orig_path != final_path and ('/jobs' not in final_path or final_path.endswith('/jobs')):
                    return {'status': 'closed', 'verified_at': now_iso, 'reason': 'Redirected to general careers page'}

                return {'status': 'active', 'verified_at': now_iso, 'reason': 'Page accessible and accepting applications'}
            elif resp.status_code in (401, 403):
                return {'status': 'possibly_active', 'verified_at': now_iso, 'reason': f'Access restricted ({resp.status_code}), cannot inspect directly'}
            else:
                return {'status': 'possibly_active', 'verified_at': now_iso, 'reason': f'HTTP status {resp.status_code}'}
    except Exception as e:
        logger.debug(f"HTTP verification error for {url}: {e}")
        return {'status': 'inaccessible', 'verified_at': now_iso, 'reason': 'Connection timeout or network failure'}
