"""Modular Job Discovery Architecture.
Provides standardized normalized job models and provider interfaces.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

@dataclass
class DiscoveredJob:
    external_id: str
    source: str                     # e.g., 'LinkedIn', 'Indeed', 'Naukri', 'JobSpy', 'Company Career'
    title: str
    company: str
    location: str
    country: str = ''
    work_mode: str = 'Unknown'      # 'Remote' | 'Hybrid' | 'Onsite' | 'Unknown'
    employment_type: str = 'Full-time'
    min_experience: Optional[float] = None
    max_experience: Optional[float] = None
    required_skills: List[str] = field(default_factory=list)
    preferred_skills: List[str] = field(default_factory=list)
    salary: str = ''
    currency: str = 'USD'
    description: str = ''
    url: str = ''
    application_url: str = ''
    posted_at: Optional[str] = None
    verified_at: Optional[str] = None
    source_attribution: str = ''
    application_method: str = 'External' # 'Easy Apply' | 'Indeed Apply' | 'Naukri Apply' | 'External'
    status: str = 'active'          # 'active' | 'closed' | 'expired'
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    def to_job_payload(self) -> Dict[str, Any]:
        """Convert to the internal job representation stored in database."""
        skills = list(dict.fromkeys(self.required_skills + self.preferred_skills))
        return {
            'external_id': self.external_id,
            'source': self.source,
            'title': self.title,
            'company': self.company,
            'location': self.location,
            'country': self.country or 'United States',
            'mode': self.work_mode,
            'employment_type': self.employment_type,
            'skills': skills,
            'required_skills': self.required_skills,
            'preferred_skills': self.preferred_skills,
            'salary': self.salary or 'Competitive',
            'min_experience': self.min_experience,
            'description': self.description,
            'url': self.url,
            'application_url': self.application_url or self.url,
            'posted': self.posted_at or datetime.now(timezone.utc).isoformat(),
            'verified_at': self.verified_at or datetime.now(timezone.utc).isoformat(),
            'source_attribution': self.source_attribution or self.source,
            'application_method': self.application_method,
            'color': '#c2f970',
            'demo': False
        }

class BaseJobProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the provider (e.g. 'LinkedIn', 'Indeed', 'Naukri', 'JobSpy')."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> List[str]:
        """List of capabilities (e.g. ['search', 'apply', 'filter_remote'])."""
        pass

    @abstractmethod
    async def search(self, query: str, location: str = '', filters: Optional[Dict[str, Any]] = None, limit: int = 15) -> List[DiscoveredJob]:
        """Execute search for jobs matching the query, location, and filters."""
        pass

    async def verify_freshness(self, job_url: str) -> bool:
        """Check if listing is still active and accepting applications."""
        return True
