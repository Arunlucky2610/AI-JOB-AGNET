"""Model Provider Abstraction & AI Job Matching Engine.
Provides swappable LLM providers (OpenRouter, local/mock fallback) and strict schema validation
for job compatibility evaluations.
"""
import asyncio
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import httpx
from pydantic import BaseModel, Field, ValidationError
from .domain import MODEL

logger = logging.getLogger(__name__)

class JobMatchSchema(BaseModel):
    match_score: int = Field(ge=0, le=100, description="Estimated compatibility score between 0 and 100")
    matching_skills: List[str] = Field(default_factory=list, description="Skills present in both job and candidate profile")
    missing_required_skills: List[str] = Field(default_factory=list, description="Mandatory job skills missing from candidate evidence")
    missing_preferred_skills: List[str] = Field(default_factory=list, description="Nice-to-have job skills missing from candidate evidence")
    experience_alignment: str = Field(description="Evaluation of years and seniority alignment")
    location_alignment: str = Field(description="Evaluation of location, country, and work mode compatibility")
    salary_alignment: str = Field(description="Evaluation of compensation range alignment")
    eligibility_concerns: List[str] = Field(default_factory=list, description="Blockers such as sponsorship, legal authorization, or company exclusions")
    recommendation: str = Field(description="Actionable verdict (e.g. Strong Match, Apply with Tailoring, Gap Identified, Do Not Apply)")
    explanation: str = Field(description="Clear human-readable summary of the evaluation")

class BaseModelProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def generate_json(self, system: str, payload: Dict[str, Any], model: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
        pass

class OpenRouterProvider(BaseModelProvider):
    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None):
        self._api_key = api_key or os.getenv('OPENROUTER_API_KEY', '')
        self._default_model = default_model or os.getenv('OPENROUTER_MODEL', MODEL)

    @property
    def name(self) -> str:
        return "OpenRouter"

    async def test_connection(self) -> Dict[str, Any]:
        """Verify API key validity against OpenRouter API."""
        key = self._api_key or os.getenv('OPENROUTER_API_KEY', '')
        if not key:
            return {'connected': False, 'error': 'Missing OPENROUTER_API_KEY'}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get('https://openrouter.ai/api/v1/auth/key', headers={'Authorization': f'Bearer {key}'})
                if res.status_code == 200:
                    data = res.json().get('data', {})
                    return {
                        'connected': True,
                        'label': data.get('label', 'Default Key'),
                        'limit': data.get('limit'),
                        'usage': data.get('usage', 0),
                        'rate_limit': data.get('rate_limit', {})
                    }
                return {'connected': False, 'status_code': res.status_code, 'error': res.text[:200]}
        except Exception as e:
            return {'connected': False, 'error': str(e)}

    async def generate_json(self, system: str, payload: Dict[str, Any], model: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
        key = self._api_key or os.getenv('OPENROUTER_API_KEY', '')
        if not key:
            raise ValueError("OPENROUTER_API_KEY is not configured.")

        target_model = model or self._default_model
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                json={
                    'model': target_model,
                    'messages': [
                        {'role': 'system', 'content': system},
                        {'role': 'user', 'content': json.dumps(payload)}
                    ],
                    'response_format': {'type': 'json_object'},
                    'temperature': 0.2,
                    'max_tokens': 3000
                }
            )
            if res.status_code != 200:
                raise RuntimeError(f"OpenRouter returned {res.status_code}: {res.text[:300]}")
            body = res.json()
            raw_content = body['choices'][0]['message']['content'].strip()
            if raw_content.startswith('```'):
                raw_content = re.sub(r'^```(?:json)?\s*', '', raw_content, flags=re.I)
                raw_content = re.sub(r'\s*```$', '', raw_content)
            return json.loads(raw_content)

class DeterministicFallbackProvider(BaseModelProvider):
    @property
    def name(self) -> str:
        return "DeterministicFallback"

    async def generate_json(self, system: str, payload: Dict[str, Any], model: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
        profile = payload.get('profile', {})
        job = payload.get('job', {})
        cand_skills = [s.strip().lower() for s in profile.get('skills', '').split(',') if s.strip()]
        job_skills = [s.strip().lower() for s in job.get('skills', []) if s.strip()]
        jd_text = (job.get('title', '') + ' ' + job.get('description', '')).lower()

        matched = [s for s in cand_skills if s in jd_text or s in job_skills]
        missing = [s for s in job_skills if s not in cand_skills]

        score = min(100, max(20, round(60 * len(matched) / max(len(cand_skills) or 1, 1) + 20)))
        return {
            "match_score": score,
            "matching_skills": matched[:8],
            "missing_required_skills": missing[:4],
            "missing_preferred_skills": [],
            "experience_alignment": f"Profile lists {profile.get('experience', 0)} years experience.",
            "location_alignment": f"Job is {job.get('mode', 'Unknown')} in {job.get('location', 'Unknown')}.",
            "salary_alignment": "Compensation not fully verified.",
            "eligibility_concerns": [],
            "recommendation": "Moderate Match" if score >= 60 else "Potential Fit Gap",
            "explanation": f"Evaluated with deterministic baseline rule. Matched {len(matched)} skills."
        }

class AIJobMatcher:
    def __init__(self, provider: Optional[BaseModelProvider] = None):
        self.provider = provider or (OpenRouterProvider() if os.getenv('OPENROUTER_API_KEY') else DeterministicFallbackProvider())

    async def evaluate_job(self, profile: Dict[str, Any], job: Dict[str, Any]) -> JobMatchSchema:
        """Evaluate job fit against candidate profile with deterministic guardrails and LLM reasoning."""
        cand_skills = [s.strip().lower() for s in profile.get('skills', '').split(',') if s.strip()]
        jd_text = (job.get('title', '') + ' ' + job.get('description', '')).lower()
        matched_skills = [s for s in cand_skills if s in jd_text]

        blockers: List[str] = []
        # Check excluded companies
        excluded = [c.strip().lower() for c in profile.get('excluded_companies', '').split(',') if c.strip()]
        if job.get('company', '').lower() in excluded:
            blockers.append(f"Company {job.get('company')} is in your excluded preferences.")

        # Check strict country
        if profile.get('strict_country', True) and profile.get('country') and job.get('country'):
            if profile.get('country', '').strip().lower() != job.get('country', '').strip().lower():
                blockers.append(f"Target country mismatch: job in {job.get('country')}, profile requires {profile.get('country')}.")

        system_prompt = (
            "You are RapidSkill AI Job Matcher. Evaluate the job vacancy against the candidate's verified profile. "
            "Never hallucinate qualifications. Ground all reasoning in explicit candidate evidence. "
            "Return valid JSON matching this schema exactly: "
            "{"
            '"match_score": <integer 0-100>,'
            '"matching_skills": [<string>],'
            '"missing_required_skills": [<string>],'
            '"missing_preferred_skills": [<string>],'
            '"experience_alignment": "<string describing experience/seniority fit>",'
            '"location_alignment": "<string describing location/work-mode fit>",'
            '"salary_alignment": "<string describing compensation fit>",'
            '"eligibility_concerns": [<string describing citizenship, visa, or clearance blockers>],'
            '"recommendation": "<Strong Match | Good Match | Apply with Tailoring | Moderate Gap | High Risk Gap>",'
            '"explanation": "<detailed factual 2-3 sentence explanation>"'
            "}"
        )

        try:
            raw = await self.provider.generate_json(system_prompt, {'profile': profile, 'job': job})
            # Combine deterministic blockers with model concerns
            concerns = list(dict.fromkeys(blockers + raw.get('eligibility_concerns', [])))
            raw['eligibility_concerns'] = concerns
            if blockers:
                raw['match_score'] = min(raw.get('match_score', 50), 30)
                raw['recommendation'] = "Eligibility Blocker Identified"
            return JobMatchSchema(**raw)
        except Exception as e:
            logger.warning(f"AI Match failed, falling back to deterministic evaluator: {e}")
            fallback = await DeterministicFallbackProvider().generate_json(system_prompt, {'profile': profile, 'job': job})
            fallback['eligibility_concerns'] = list(dict.fromkeys(blockers + fallback.get('eligibility_concerns', [])))
            if blockers:
                fallback['match_score'] = min(fallback.get('match_score', 50), 30)
                fallback['recommendation'] = "Eligibility Blocker Identified"
            return JobMatchSchema(**fallback)

matcher = AIJobMatcher()
