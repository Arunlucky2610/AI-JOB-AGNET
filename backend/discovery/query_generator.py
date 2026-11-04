"""Targeted Query Generator for Job Discovery.
Constructs intelligent, deduplicated search queries based on the user's actual profile and preferences.
"""
from typing import List, Dict, Any

def generate_targeted_queries(profile: Dict[str, Any], settings: Dict[str, Any], max_queries: int = 6) -> List[str]:
    """Generate prioritized, high-yield web research and job search queries.
    
    Considers:
    - Target roles
    - Top required skills
    - Locations & Country
    - Experience level (Fresher / Entry level vs Senior)
    - Work mode (Remote, Hybrid)
    """
    raw_roles = [r.strip() for r in profile.get('roles', '').split(',') if r.strip()]
    if not raw_roles:
        raw_roles = ['Software Engineer']

    raw_skills = [s.strip() for s in profile.get('skills', '').split(',') if s.strip()]
    top_skills = raw_skills[:4]
    skill_str = ' '.join(top_skills[:2]) if top_skills else ''

    raw_locations = [loc.strip() for loc in profile.get('locations', '').split(',') if loc.strip()]
    primary_location = raw_locations[0] if raw_locations else ''
    country = profile.get('country', '').strip()
    work_modes = profile.get('work_modes', [])
    is_remote_preferred = any('remote' in m.lower() for m in work_modes)

    try:
        exp_years = float(profile.get('experience', 0))
    except (ValueError, TypeError):
        exp_years = 0.0

    is_fresher = exp_years <= 1.0 or 'fresher' in profile.get('roles', '').lower()
    seniority = 'fresher' if is_fresher else 'entry level' if exp_years <= 2.0 else f'{int(exp_years)} years'

    queries = []
    
    # 1. Primary Role + Location/Country queries
    for role in raw_roles[:2]:
        loc_token = primary_location or country or 'India'
        
        # ATS site-specific query for official company postings
        if is_remote_preferred:
            queries.append(f"site:boards.greenhouse.io {role} {country or loc_token}".strip())
            queries.append(f"site:jobs.lever.co {role} {country or loc_token}".strip())
            queries.append(f"site:jobs.ashbyhq.com {role} remote".strip())
        else:
            queries.append(f"site:boards.greenhouse.io {role} {loc_token}".strip())
            queries.append(f"site:jobs.lever.co {role} {loc_token}".strip())

        # General web query with skill and seniority
        if is_fresher:
            queries.append(f'"{role}" {skill_str} {seniority} {loc_token} jobs'.strip())
        else:
            queries.append(f'"{role}" {skill_str} {loc_token} careers'.strip())

    # 2. Company career queries
    if raw_roles:
        main_role = raw_roles[0]
        loc_str = primary_location or country
        queries.append(f"{main_role} {skill_str} {loc_str} job vacancy".strip())

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for q in queries:
        cleaned = ' '.join(q.split())
        if cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            deduped.append(cleaned)
        if len(deduped) >= max_queries:
            break

    return deduped
