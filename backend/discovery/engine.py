"""Core Job Discovery Engine.
Orchestrates preference validation, query generation, multi-source research, deduplication, scoring, and persistence.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from ..db import Session, Job, DiscoveryRun, now
from .base import DiscoveredJob
from .query_generator import generate_targeted_queries
from .search_provider import get_search_provider
from .ats_provider import ATSCareerProvider
from .jobspy_provider import JobSpyProvider
from .matching import calculate_match
from .url_validator import validate_url, canonicalize_url

logger = logging.getLogger(__name__)

# Active background tasks: run_id -> asyncio.Task
_ACTIVE_RUNS: Dict[str, asyncio.Task] = {}

def validate_user_preferences(profile: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Verify that user profile has enough information to conduct an intelligent job search."""
    errors = []
    roles = [r.strip() for r in profile.get('roles', '').split(',') if r.strip()]
    if not roles:
        errors.append("Please specify at least one target role in your profile.")
    
    country = profile.get('country', '').strip()
    if not country:
        errors.append("Please specify your target country in your profile.")

    skills = [s.strip() for s in profile.get('skills', '').split(',') if s.strip()]
    if not skills:
        errors.append("Please list your key skills in your profile to enable match scoring.")

    return len(errors) == 0, errors

def normalize_title(title: str) -> str:
    """Normalize a job title for fuzzy deduplication."""
    import re
    t = re.sub(r'[^a-zA-Z0-9\s]', ' ', title.lower())
    # Remove common seniority noise words for base match
    t = re.sub(r'\b(senior|sr|junior|jr|lead|principal|staff|associate|entry level|intern)\b', '', t)
    return ' '.join(t.split())

def deduplicate_jobs(jobs: List[DiscoveredJob]) -> tuple[List[DiscoveredJob], int]:
    """Multi-step deduplication by canonical URL and (Company + normalized Title)."""
    seen_urls = set()
    seen_entities = set()
    unique_jobs: List[DiscoveredJob] = []
    duplicates_count = 0

    for job in jobs:
        # 1. Canonical URL check
        c_url = canonicalize_url(job.url or job.application_url)
        if c_url in seen_urls:
            duplicates_count += 1
            continue

        # 2. Company + Title entity check
        comp_norm = job.company.strip().lower()
        title_norm = normalize_title(job.title)
        entity_key = f"{comp_norm}::{title_norm}"

        if comp_norm and title_norm and entity_key in seen_entities:
            # Check if this new listing has an official ATS application URL to prefer
            existing_idx = next((i for i, j in enumerate(unique_jobs) if f"{j.company.strip().lower()}::{normalize_title(j.title)}" == entity_key), None)
            if existing_idx is not None:
                existing_job = unique_jobs[existing_idx]
                if job.source in ('Greenhouse', 'Lever', 'Ashby', 'Company Career') and existing_job.source not in ('Greenhouse', 'Lever', 'Ashby', 'Company Career'):
                    # Swap with the official ATS listing
                    unique_jobs[existing_idx] = job
            duplicates_count += 1
            continue

        seen_urls.add(c_url)
        if comp_norm and title_norm:
            seen_entities.add(entity_key)
        unique_jobs.append(job)

    return unique_jobs, duplicates_count

async def run_discovery_pipeline(run_id: str, user_id: str, profile: Dict[str, Any], settings: Dict[str, Any]):
    """Execute the end-to-end background discovery pipeline with live telemetry."""
    def log_event(phase: str, text: str, progress_updates: Optional[Dict[str, Any]] = None):
        with Session() as db:
            run = db.get(DiscoveryRun, run_id)
            if not run or run.status == 'cancelled':
                return False
            run.phase = phase
            run.events = [*run.events, {'time': datetime.now(timezone.utc).isoformat(), 'text': text}]
            if progress_updates:
                cur_prog = dict(run.progress or {})
                cur_prog.update(progress_updates)
                run.progress = cur_prog
            db.commit()
            return True

    progress = {
        'queries_executed': 0,
        'sources_searched': 0,
        'pages_inspected': 0,
        'listings_discovered': 0,
        'valid_listings': 0,
        'duplicates_removed': 0,
        'jobs_matching': 0,
        'jobs_saved': 0,
        'failed_sources': 0
    }

    try:
        if not log_event('validating', 'Validating job search preferences...', progress):
            return

        is_valid, validation_errors = validate_user_preferences(profile)
        if not is_valid:
            with Session() as db:
                run = db.get(DiscoveryRun, run_id)
                if run:
                    run.status = 'failed'
                    run.error = '; '.join(validation_errors)
                    run.completed_at = now()
                    db.commit()
            return

        # Phase 2: Generating Queries
        queries = generate_targeted_queries(profile, settings, max_queries=4)
        log_event('generating_queries', f"Generated {len(queries)} targeted research queries.", {'queries_generated': len(queries)})

        all_discovered: List[DiscoveredJob] = []
        search_provider = get_search_provider()
        jobspy_provider = JobSpyProvider()

        # Phase 3: Searching Sources
        log_event('searching', f"Initiating web discovery using {search_provider.name} and platform boards...", progress)

        # 1. Search Web queries
        for q in queries:
            try:
                progress['queries_executed'] += 1
                results = await search_provider.search(q, max_results=4)
                progress['sources_searched'] += 1
                for r in results:
                    progress['pages_inspected'] += 1
                    page_url = r.get('url', '')
                    if not page_url:
                        continue
                    # Inspect ATS or career page
                    job = await ATSCareerProvider.inspect_page(page_url)
                    if job:
                        all_discovered.append(job)
                        progress['listings_discovered'] += 1
            except Exception as e:
                logger.warning(f"Error querying search for '{q}': {e}")
                progress['failed_sources'] += 1

        log_event('searching', f"Web search completed. Running multi-board aggregator search...", progress)

        # 2. Multi-board search (JobSpy)
        roles = [r.strip() for r in profile.get('roles', '').split(',') if r.strip()]
        locations = [l.strip() for l in profile.get('locations', '').split(',') if l.strip()]
        primary_role = roles[0] if roles else 'Software Engineer'
        primary_loc = locations[0] if locations else ''
        
        try:
            progress['sources_searched'] += 1
            filters = {
                'country': profile.get('country', 'India'),
                'is_remote': any('remote' in m.lower() for m in profile.get('work_modes', []))
            }
            board_jobs = await jobspy_provider.search(
                query=primary_role,
                location=primary_loc,
                filters=filters,
                limit=15
            )
            all_discovered.extend(board_jobs)
            progress['listings_discovered'] += len(board_jobs)
        except Exception as e:
            logger.warning(f"JobSpy provider search error: {e}")
            progress['failed_sources'] += 1

        # 3. Internshala Live Discovery
        try:
            from .internshala_provider import InternshalaProvider
            is_provider = InternshalaProvider()
            is_jobs = await is_provider.search(
                query=primary_role,
                location=primary_loc,
                filters=filters,
                limit=15
            )
            if is_jobs:
                all_discovered.extend(is_jobs)
                progress['sources_searched'] += 1
                progress['listings_discovered'] += len(is_jobs)
        except Exception as e:
            logger.warning(f"Internshala search error: {e}")

        # 4. Naukri & Portal Integration
        try:
            from .platform_providers import NaukriProvider
            naukri_provider = NaukriProvider()
            n_jobs = await naukri_provider.search(
                query=primary_role,
                location=primary_loc,
                filters=filters,
                limit=10
            )
            if n_jobs:
                all_discovered.extend(n_jobs)
                progress['sources_searched'] += 1
                progress['listings_discovered'] += len(n_jobs)
        except Exception as e:
            logger.warning(f"Naukri search error: {e}")

        # Phase 4: URL Validation
        log_event('extracting', f"Validating {len(all_discovered)} extracted listings...", progress)
        valid_jobs: List[DiscoveredJob] = []
        for job in all_discovered:
            is_safe, _ = validate_url(job.url)
            if is_safe:
                valid_jobs.append(job)
                progress['valid_listings'] += 1

        # Phase 5: Deduplication
        log_event('deduplicating', f"Deduplicating {len(valid_jobs)} listings...", progress)
        unique_jobs, dups_removed = deduplicate_jobs(valid_jobs)
        progress['duplicates_removed'] = dups_removed

        # Phase 6: Scoring & Eligibility
        log_event('matching', f"Scoring {len(unique_jobs)} candidate listings against your profile...", progress)
        scored_jobs = []
        matching_count = 0

        for d_job in unique_jobs:
            payload = d_job.to_job_payload()
            match_res = calculate_match(profile, payload, settings)
            payload['match'] = match_res
            if match_res.get('matched'):
                matching_count += 1
            scored_jobs.append(payload)

        progress['jobs_matching'] = matching_count

        # Phase 7: Saving to Database
        log_event('saving', f"Persisting results ({len(scored_jobs)} vacancies)...", progress)
        saved_count = 0
        with Session() as db:
            for job_payload in scored_jobs:
                canonical = job_payload.get('url', '')
                existing = db.query(Job).filter_by(user_id=user_id, canonical=canonical).first()
                if not existing:
                    job_id = str(uuid.uuid4())
                    db.add(Job(
                        id=job_id,
                        user_id=user_id,
                        canonical=canonical,
                        payload={**job_payload, 'id': job_id}
                    ))
                    saved_count += 1
            db.commit()

        progress['jobs_saved'] = saved_count
        final_status = 'completed_with_warnings' if progress['failed_sources'] > 0 else 'completed'

        with Session() as db:
            run = db.get(DiscoveryRun, run_id)
            if run and run.status != 'cancelled':
                run.status = final_status
                run.phase = 'completed'
                run.results_count = len(scored_jobs)
                run.completed_at = now()
                run.progress = progress
                run.events = [*run.events, {
                    'time': datetime.now(timezone.utc).isoformat(),
                    'text': f"Discovery complete! Discovered {len(scored_jobs)} listings ({saved_count} new saved, {dups_removed} duplicates removed)."
                }]
                db.commit()

    except asyncio.CancelledError:
        with Session() as db:
            run = db.get(DiscoveryRun, run_id)
            if run:
                run.status = 'cancelled'
                run.phase = 'cancelled'
                run.completed_at = now()
                run.events = [*run.events, {'time': datetime.now(timezone.utc).isoformat(), 'text': 'Discovery cancelled by user.'}]
                db.commit()
    except Exception as e:
        logger.error(f"Discovery pipeline fatal error: {e}", exc_info=True)
        with Session() as db:
            run = db.get(DiscoveryRun, run_id)
            if run:
                run.status = 'failed'
                run.phase = 'failed'
                run.error = str(e)
                run.completed_at = now()
                run.events = [*run.events, {'time': datetime.now(timezone.utc).isoformat(), 'text': f"Error: {e}"}]
                db.commit()
    finally:
        _ACTIVE_RUNS.pop(run_id, None)

def start_discovery_run(user_id: str, profile: Dict[str, Any], settings: Dict[str, Any]) -> DiscoveryRun:
    """Validate preferences and spawn background discovery run."""
    # Check if a run is already active for this user
    with Session() as db:
        active = db.query(DiscoveryRun).filter_by(user_id=user_id, status='running').first()
        if active:
            return active

        run_id = str(uuid.uuid4())
        run = DiscoveryRun(
            id=run_id,
            user_id=user_id,
            status='running',
            phase='validating',
            search_config={
                'roles': profile.get('roles', ''),
                'skills': profile.get('skills', ''),
                'locations': profile.get('locations', ''),
                'country': profile.get('country', ''),
                'work_modes': profile.get('work_modes', []),
                'threshold': settings.get('threshold') or settings.get('effective_threshold') or 60
            },
            progress={
                'queries_executed': 0,
                'sources_searched': 0,
                'pages_inspected': 0,
                'listings_discovered': 0,
                'valid_listings': 0,
                'duplicates_removed': 0,
                'jobs_matching': 0,
                'jobs_saved': 0,
                'failed_sources': 0
            },
            events=[{
                'time': datetime.now(timezone.utc).isoformat(),
                'text': 'Started job discovery run.'
            }],
            results_count=0
        )
        db.add(run)
        db.commit()
        db.refresh(run)

    task = asyncio.create_task(run_discovery_pipeline(run_id, user_id, profile, settings))
    _ACTIVE_RUNS[run_id] = task
    return run

def cancel_active_discovery_run(user_id: str) -> bool:
    """Cancel any active running discovery task for the given user."""
    with Session() as db:
        active = db.query(DiscoveryRun).filter_by(user_id=user_id, status='running').first()
        if not active:
            return False
        active.status = 'cancelled'
        active.completed_at = now()
        db.commit()

    task = _ACTIVE_RUNS.get(active.id)
    if task and not task.done():
        task.cancel()
    return True

def get_latest_discovery_run(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve the latest discovery run status and progress for the given user."""
    with Session() as db:
        run = db.query(DiscoveryRun).filter_by(user_id=user_id).order_by(DiscoveryRun.created.desc()).first()
        if not run:
            return None
        return {
            'id': run.id,
            'status': run.status,
            'phase': run.phase,
            'progress': run.progress or {},
            'search_config': run.search_config or {},
            'events': run.events or [],
            'results_count': run.results_count or 0,
            'error': run.error,
            'warnings': run.warnings or [],
            'created': run.created.isoformat() if run.created else None,
            'completed_at': run.completed_at.isoformat() if run.completed_at else None
        }
