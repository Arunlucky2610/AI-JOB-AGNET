"""Profile-Based Transparent Job Matching and Eligibility Engine.
Provides reproducible, multi-dimensional scoring (0-100) with detailed breakdowns and eligibility handling.
"""
import re
from typing import Dict, Any, List

def calculate_match(profile: Dict[str, Any], job: Dict[str, Any], settings: Dict[str, Any] = None) -> Dict[str, Any]:
    """Calculate transparent 0-100 score and eligibility breakdown."""
    settings = settings or {}
    effective_threshold = float(settings.get('threshold') or settings.get('effective_threshold') or 60)

    # 1. Target Role Relevance (30%)
    raw_roles = [r.strip().lower() for r in profile.get('roles', '').split(',') if r.strip()]
    job_title = job.get('title', '').lower()
    
    role_matched = False
    role_score = 0
    if not raw_roles:
        role_score = 25 # No roles specified, assume open
        role_matched = True
    else:
        for r in raw_roles:
            if r in job_title:
                role_score = 30
                role_matched = True
                break
            # Partial word overlap (e.g. 'developer' or 'engineer' or 'python')
            r_words = set(r.split())
            t_words = set(job_title.split())
            if r_words & t_words:
                role_score = max(role_score, 18)
                role_matched = True

    # 2. Required Skills Overlap (25%)
    cand_skills = [s.strip().lower() for s in profile.get('skills', '').split(',') if s.strip()]
    jd_text = (job.get('title', '') + ' ' + job.get('description', '')).lower()
    job_skills = [s.strip().lower() for s in job.get('skills', []) if s.strip()]

    matched_skills = []
    missing_skills = []

    for s in cand_skills:
        # Match exact word boundaries or substring
        if re.search(r'\b' + re.escape(s) + r'\b', jd_text) or s in job_skills:
            matched_skills.append(s)

    for js in job_skills:
        if js not in cand_skills:
            missing_skills.append(js)

    if cand_skills:
        skill_ratio = min(1.0, len(matched_skills) / max(1, min(len(cand_skills), 6)))
        skill_score = round(25 * skill_ratio)
    else:
        skill_score = 15

    # 3. Experience Compatibility (15%)
    try:
        user_exp = float(profile.get('experience', 0))
    except (ValueError, TypeError):
        user_exp = 0.0

    min_exp = job.get('min_experience')
    exp_blocker = False
    exp_score = 15

    if min_exp is not None:
        try:
            min_exp = float(min_exp)
            if user_exp >= min_exp:
                exp_score = 15
            elif user_exp >= (min_exp - 1.0):
                exp_score = 10
            else:
                exp_score = 3
                exp_blocker = True
        except (ValueError, TypeError):
            exp_score = 10
    else:
        # Check text for fresher / senior
        if 'fresher' in jd_text or 'entry level' in jd_text or 'junior' in jd_text:
            exp_score = 15 if user_exp <= 2.0 else 12
        elif 'senior' in jd_text or 'lead' in jd_text or 'staff' in jd_text:
            exp_score = 5 if user_exp < 3.0 else 15
            if user_exp < 2.0:
                exp_blocker = True

    # 4. Location & Work-mode Compatibility (15%)
    loc_score = 15
    user_modes = [m.lower() for m in profile.get('work_modes', ['Remote', 'Hybrid', 'Onsite'])]
    job_mode = job.get('mode', 'Unknown').lower()
    user_locations = [l.strip().lower() for l in profile.get('locations', '').split(',') if l.strip()]
    job_loc = job.get('location', '').lower()

    mode_match = job_mode in user_modes or job_mode == 'unknown' or 'remote' in user_modes and 'remote' in job_loc
    if mode_match:
        loc_score = 15
    else:
        loc_score = 5

    if profile.get('strict_location') and job_mode != 'remote' and user_locations:
        if not any(l in job_loc for l in user_locations):
            loc_score = max(0, loc_score - 8)

    # 5. Employment Type Compatibility (5%)
    user_type = profile.get('employment_type', 'Full-time').lower()
    job_type = job.get('employment_type', 'Full-time').lower()
    type_score = 5 if user_type in job_type or job_type in user_type else 3

    # 6. Other Configured Preferences and Eligibility (10%)
    pref_score = 10
    blockers = []
    unknown = []

    # Excluded companies
    excluded_comps = [c.strip().lower() for c in profile.get('excluded_companies', '').split(',') if c.strip()]
    if job.get('company', '').lower() in excluded_comps:
        blockers.append(f"Company {job.get('company')} is in your excluded preferences")
        pref_score = 0

    # Country check
    user_country = profile.get('country', '').strip().lower()
    job_country = job.get('country', '').strip().lower()
    if profile.get('strict_country', True) and user_country and job_country:
        if user_country != job_country and 'remote' not in job_loc:
            blockers.append(f"Target country does not match ({job.get('country')})")
            pref_score = max(0, pref_score - 5)

    if exp_blocker:
        blockers.append(f"Required experience exceeds your profile ({user_exp} yrs vs {min_exp} required)")

    if not role_matched and raw_roles:
        blockers.append("Target role does not match")

    # Sponsorship & Work Authorization
    user_sponsorship = profile.get('sponsorship', '').strip().lower()
    if user_sponsorship.startswith('yes'):
        unknown.append("Visa sponsorship eligibility needs verification")

    # Final Normalized Score
    total_score = min(100, max(0, role_score + skill_score + exp_score + loc_score + type_score + pref_score))
    
    # Eligibility status
    if blockers:
        eligibility_status = 'ineligible'
    elif unknown:
        eligibility_status = 'potentially_eligible'
    else:
        eligibility_status = 'eligible'

    is_matched = (eligibility_status != 'ineligible') and (total_score >= effective_threshold)

    explanation = (
        f"Match: {total_score}%. Role fit: {role_score}/30, Skills fit: {skill_score}/25 "
        f"({len(matched_skills)} matched: {', '.join(matched_skills[:4]) or 'none'}), "
        f"Experience fit: {exp_score}/15, Location & mode: {loc_score}/15."
    )

    return {
        'score': total_score,
        'matched': is_matched,
        'eligible': eligibility_status != 'ineligible',
        'eligibility_status': eligibility_status,
        'matched_skills': matched_skills,
        'missing_skills': missing_skills[:6],
        'blockers': blockers,
        'unknown': unknown,
        'method': 'Transparent Multi-Factor Rules',
        'explanation': explanation,
        'breakdown': {
            'role_score': role_score,
            'skill_score': skill_score,
            'exp_score': exp_score,
            'loc_score': loc_score,
            'type_score': type_score,
            'pref_score': pref_score,
            'total_score': total_score
        }
    }
