"""Search Engine Provider Abstraction and Integrations.
Supports DuckDuckGo HTML (zero credentials required), Google Custom Search, and SerpAPI.
"""
import logging
import os
import urllib.parse
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import httpx
from ..web_researcher import search_web, HEADERS
from .url_validator import validate_url, canonicalize_url

logger = logging.getLogger(__name__)

class BaseSearchProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        pass

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Returns list of {'url': str, 'title': str, 'snippet': str}."""
        pass

class DuckDuckGoSearchProvider(BaseSearchProvider):
    @property
    def name(self) -> str:
        return "DuckDuckGo"

    @property
    def is_configured(self) -> bool:
        return True

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        try:
            results = await search_web(query, max_results=max_results)
            safe_results = []
            for r in results:
                url = r.get('url', '')
                is_safe, _ = validate_url(url)
                if is_safe:
                    safe_results.append({
                        'url': canonicalize_url(url),
                        'title': r.get('title', ''),
                        'snippet': r.get('snippet', '')
                    })
            return safe_results
        except Exception as e:
            logger.warning(f"DuckDuckGo search error: {e}")
            return []

class GoogleCustomSearchProvider(BaseSearchProvider):
    def __init__(self, api_key: Optional[str] = None, engine_id: Optional[str] = None):
        self._api_key = api_key or os.getenv('GOOGLE_SEARCH_API_KEY') or os.getenv('JOB_SEARCH_API_KEY', '')
        self._engine_id = engine_id or os.getenv('GOOGLE_SEARCH_ENGINE_ID', '')

    @property
    def name(self) -> str:
        return "GoogleCustomSearch"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._engine_id)

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        if not self.is_configured:
            return []
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': self._api_key,
            'cx': self._engine_id,
            'q': query,
            'num': min(max_results, 10)
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get('items', [])
                    results = []
                    for it in items:
                        link = it.get('link', '')
                        is_safe, _ = validate_url(link)
                        if is_safe:
                            results.append({
                                'url': canonicalize_url(link),
                                'title': it.get('title', ''),
                                'snippet': it.get('snippet', '')
                            })
                    return results
                else:
                    logger.warning(f"Google Search returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Google Search error: {e}")
        return []

class SerpApiSearchProvider(BaseSearchProvider):
    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv('SERPAPI_API_KEY', '')

    @property
    def name(self) -> str:
        return "SerpAPI"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        if not self.is_configured:
            return []
        url = "https://serpapi.com/search.json"
        params = {
            'api_key': self._api_key,
            'q': query,
            'engine': 'google',
            'num': min(max_results, 10)
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    organic = data.get('organic_results', [])
                    results = []
                    for it in organic:
                        link = it.get('link', '')
                        is_safe, _ = validate_url(link)
                        if is_safe:
                            results.append({
                                'url': canonicalize_url(link),
                                'title': it.get('title', ''),
                                'snippet': it.get('snippet', '')
                            })
                    return results
                else:
                    logger.warning(f"SerpAPI returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"SerpAPI search error: {e}")
        return []

def get_search_provider() -> BaseSearchProvider:
    """Return the primary configured search provider, falling back to DuckDuckGo."""
    provider_pref = os.getenv('JOB_SEARCH_PROVIDER', '').lower()
    
    if provider_pref == 'google':
        google = GoogleCustomSearchProvider()
        if google.is_configured:
            return google
        logger.info("Google search provider requested but GOOGLE_SEARCH_API_KEY or GOOGLE_SEARCH_ENGINE_ID missing. Falling back to DuckDuckGo.")
    
    if provider_pref == 'serpapi':
        serp = SerpApiSearchProvider()
        if serp.is_configured:
            return serp
        logger.info("SerpAPI requested but SERPAPI_API_KEY missing. Falling back to DuckDuckGo.")

    # Check if google keys exist anyway
    google = GoogleCustomSearchProvider()
    if google.is_configured:
        return google

    serp = SerpApiSearchProvider()
    if serp.is_configured:
        return serp

    # Default robust fallback
    return DuckDuckGoSearchProvider()
