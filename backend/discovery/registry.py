"""Discovery Provider Registry and Search Orchestrator.
Manages provider registration, unified multi-source discovery, deduplication, and persistence.
"""
import logging
from typing import Dict, List, Optional, Any
from .base import BaseJobProvider, DiscoveredJob
from .jobspy_provider import JobSpyProvider
from .platform_providers import LinkedInProvider, IndeedProvider, NaukriProvider
from ..db import Session, Job, JobSource, now
from ..domain import evaluate, fingerprint

logger = logging.getLogger(__name__)

class DiscoveryRegistry:
    def __init__(self):
        self._providers: Dict[str, BaseJobProvider] = {}
        # Register default providers
        self.register(JobSpyProvider())
        self.register(LinkedInProvider())
        self.register(IndeedProvider())
        self.register(NaukriProvider())

    def register(self, provider: BaseJobProvider):
        self._providers[provider.name.lower()] = provider

    def get(self, name: str) -> Optional[BaseJobProvider]:
        return self._providers.get(name.lower())

    def list_providers(self) -> List[Dict[str, Any]]:
        return [
            {
                'name': p.name,
                'capabilities': p.capabilities,
                'enabled': True
            }
            for p in self._providers.values()
        ]

    async def discover_jobs(
        self,
        query: str,
        location: str = '',
        providers: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit_per_provider: int = 10,
        user_id: Optional[str] = None,
        user_profile: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Run job discovery across selected providers, normalize, deduplicate, and persist."""
        target_providers = []
        if providers:
            for p_name in providers:
                p = self.get(p_name)
                if p:
                    target_providers.append(p)
        if not target_providers:
            # Default to JobSpy multi-board search
            jobspy = self.get('jobspy')
            if jobspy:
                target_providers.append(jobspy)

        all_discovered: List[DiscoveredJob] = []
        for provider in target_providers:
            try:
                jobs = await provider.search(query, location=location, filters=filters, limit=limit_per_provider)
                all_discovered.extend(jobs)
            except Exception as e:
                logger.error(f"Error executing discovery on {provider.name}: {e}")

        # Deduplicate by canonical URL / external ID
        seen_keys = set()
        unique_jobs: List[Dict[str, Any]] = []

        for d_job in all_discovered:
            key = (d_job.url or d_job.external_id).split('?')[0].rstrip('/')
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            payload = d_job.to_job_payload()

            # If user profile provided, calculate match score
            if user_profile:
                match_result = evaluate(user_profile, payload)
                payload['match'] = match_result
            else:
                payload['match'] = {
                    'score': 70,
                    'matched': True,
                    'eligible': True,
                    'matched_skills': payload.get('skills', [])[:3],
                    'missing_skills': [],
                    'blockers': [],
                    'unknown': [],
                    'method': 'Default discovery score'
                }

            unique_jobs.append(payload)

        # If user_id is provided, persist into DB jobs table safely
        if user_id and unique_jobs:
            with Session() as db:
                for job_payload in unique_jobs:
                    canonical_url = (job_payload.get('url') or job_payload.get('external_id')).split('?')[0].rstrip('/')
                    existing = db.query(Job).filter_by(user_id=user_id, canonical=canonical_url).first()
                    if not existing:
                        import uuid
                        job_id = str(uuid.uuid4())
                        db.add(Job(
                            id=job_id,
                            user_id=user_id,
                            canonical=canonical_url,
                            payload={**job_payload, 'id': job_id}
                        ))
                db.commit()

        return unique_jobs

registry = DiscoveryRegistry()
