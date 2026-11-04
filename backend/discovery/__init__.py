from .base import BaseJobProvider, DiscoveredJob
from .jobspy_provider import JobSpyProvider
from .platform_providers import LinkedInProvider, IndeedProvider, NaukriProvider
from .registry import DiscoveryRegistry, registry
from .engine import (
    start_discovery_run,
    cancel_active_discovery_run,
    get_latest_discovery_run,
    validate_user_preferences
)
from .freshness import verify_job_freshness
from .url_validator import validate_url, canonicalize_url
from .matching import calculate_match

__all__ = [
    'BaseJobProvider',
    'DiscoveredJob',
    'JobSpyProvider',
    'LinkedInProvider',
    'IndeedProvider',
    'NaukriProvider',
    'DiscoveryRegistry',
    'registry',
    'start_discovery_run',
    'cancel_active_discovery_run',
    'get_latest_discovery_run',
    'validate_user_preferences',
    'verify_job_freshness',
    'validate_url',
    'canonicalize_url',
    'calculate_match'
]
