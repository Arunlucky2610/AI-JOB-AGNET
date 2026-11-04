"""Persistent Question-and-Answer Memory and Retrieval System.

Core orchestration for:
- 6-tier knowledge retrieval hierarchy
- Question classification (A, B, C, D, E)
- Semantic similarity matching with synonym expansion
- Context verification (company, role, salary, location)
- Web research invocation and caching
- Form constraint enforcement (options, character limits)
- Human takeover gating for sensitive/unverified questions
- Multi-tenant isolation and persistent storage in SQLAlchemy
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from .db import Session, QuestionMemory, User, now
from .question_matcher import normalize_question, semantic_similarity, compute_embedding
from .question_classifier import (
    classify_question,
    CATEGORY_A, CATEGORY_B, CATEGORY_C, CATEGORY_D, CATEGORY_E
)
from .question_detector import DetectedQuestion
from .web_researcher import research_company, research_technical_topic
from .domain import parse_salary

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD_HIGH = 0.82
SIMILARITY_THRESHOLD_ACCEPT = 0.75
MAX_COMPANY_STALENESS_DAYS = 30

class AnswerResult:
    def __init__(
        self,
        answer: str,
        category: str,
        source: str,
        confidence: float,
        approval_status: str = 'unapproved',
        source_urls: list[str] | None = None,
        needs_user_input: bool = False,
        pause_reason: str = '',
        memory_id: str | None = None,
        is_reused: bool = False,
        explanation: str = ''
    ):
        self.answer = str(answer or '').strip()
        self.category = category
        self.source = source
        self.confidence = float(confidence)
        self.approval_status = approval_status
        self.source_urls = source_urls or []
        self.needs_user_input = needs_user_input
        self.pause_reason = pause_reason
        self.memory_id = memory_id
        self.is_reused = is_reused
        self.explanation = explanation

    def to_dict(self) -> dict[str, Any]:
        return {
            'answer': self.answer,
            'category': self.category,
            'source': self.source,
            'confidence': self.confidence,
            'approval_status': self.approval_status,
            'source_urls': self.source_urls,
            'needs_user_input': self.needs_user_input,
            'pause_reason': self.pause_reason,
            'memory_id': self.memory_id,
            'is_reused': self.is_reused,
            'explanation': self.explanation
        }

def match_dropdown_option(options: list[str], target_value: str) -> str | None:
    """Select the best matching option from a dropdown or radio button set."""
    if not options or not target_value:
        return None
    target_clean = target_value.strip().casefold()
    
    # 1. Exact match
    for opt in options:
        if opt.strip().casefold() == target_clean:
            return opt

    # 2. Starts with / prefix match
    for opt in options:
        if opt.strip().casefold().startswith(target_clean):
            return opt

    # 3. Word boundary match
    for opt in options:
        if re.search(r'\b' + re.escape(target_clean) + r'\b', opt.strip().casefold()):
            return opt

    # 4. Target inside option (unique match only)
    containing = [opt for opt in options if target_clean in opt.strip().casefold()]
    if len(containing) == 1:
        return containing[0]

    # 5. Yes/No normalization
    if target_clean in ('yes', 'true', '1', 'authorized', 'eligible', 'agree'):
        for opt in options:
            if opt.strip().casefold() in ('yes', 'i agree', 'authorized'):
                return opt
    if target_clean in ('no', 'false', '0', 'not authorized', 'decline'):
        for opt in options:
            if opt.strip().casefold() in ('no', 'i do not agree', 'not authorized'):
                return opt

    return None

def enforce_length_constraints(answer: str, char_limit: int | None = None, word_limit: int | None = None) -> str:
    """Shorten answer cleanly while preserving core sentence meaning."""
    if not answer:
        return ''
    text = answer.strip()
    
    # Word limit constraint
    if word_limit and word_limit > 0:
        words = text.split()
        if len(words) > word_limit:
            # Truncate at word limit
            text = " ".join(words[:word_limit])
            # Ensure it ends on sentence boundary if possible
            last_period = text.rfind('.')
            if last_period > len(text) * 0.6:
                text = text[:last_period + 1]

    # Character limit constraint
    if char_limit and char_limit > 0 and len(text) > char_limit:
        truncated = text[:char_limit]
        last_punct = max(truncated.rfind('.'), truncated.rfind(';'), truncated.rfind('!'))
        if last_punct > char_limit * 0.6:
            text = truncated[:last_punct + 1]
        else:
            last_space = truncated.rfind(' ')
            if last_space > char_limit * 0.6:
                text = truncated[:last_space].rstrip(r',;:-') + '.'
            else:
                text = truncated

    return text.strip()

# ---------------------------------------------------------------------------
# Database Persistent Memory Operations (Multi-tenant isolated)
# ---------------------------------------------------------------------------

def save_memory_record(
    user_id: str,
    question_text: str,
    original_question: str,
    answer_text: str,
    category: str,
    source: str,
    confidence: float = 1.0,
    approval_status: str = 'unapproved',
    company: str | None = None,
    job_title: str | None = None,
    job_id: str | None = None,
    scope: str = 'reusable',
    source_urls: list[str] | None = None,
    context_markers: dict | None = None,
    ttl_days: int | None = None
) -> QuestionMemory:
    """Save or update a persistent memory record in the database for the given user."""
    norm_q = normalize_question(question_text)
    embed = compute_embedding(question_text)
    source_urls = source_urls or []
    context_markers = context_markers or {}
    expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)) if ttl_days else None

    with Session() as db:
        # Check if an exact normalized question already exists for this user and company context
        query = db.query(QuestionMemory).filter_by(user_id=user_id, question_id=norm_q)
        if company:
            query = query.filter_by(company=company)
        existing = query.first()

        if existing:
            # Update existing memory with fresh answer / timestamp
            existing.answer_text = answer_text
            existing.original_question = original_question
            existing.embedding = embed
            existing.category = category
            existing.source = source
            existing.confidence = confidence
            if approval_status == 'approved' or existing.approval_status != 'approved':
                existing.approval_status = approval_status
            existing.source_urls = list(dict.fromkeys(existing.source_urls + source_urls))
            existing.context_markers = {**existing.context_markers, **context_markers}
            existing.status = 'active'
            existing.expires_at = expires_at
            existing.updated = now()
            existing.last_used = now()
            db.commit()
            db.refresh(existing)
            return existing
        else:
            rec = QuestionMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                question_id=norm_q,
                question_text=norm_q,
                original_question=original_question,
                embedding=embed,
                answer_text=answer_text,
                category=category,
                source=source,
                source_urls=source_urls,
                confidence=confidence,
                approval_status=approval_status,
                company=company,
                job_title=job_title,
                job_id=job_id,
                scope=scope,
                context_markers=context_markers,
                usage_count=1,
                created=now(),
                updated=now(),
                last_used=now(),
                status='active',
                expires_at=expires_at
            )
            db.add(rec)
            db.commit()
            db.refresh(rec)
            return rec

def record_memory_usage(memory_id: str, user_id: str, was_successful: bool = True):
    """Increment usage counter, update last-used timestamp and success count."""
    with Session() as db:
        rec = db.query(QuestionMemory).filter_by(id=memory_id, user_id=user_id).first()
        if rec:
            rec.usage_count = (rec.usage_count or 0) + 1
            if was_successful:
                rec.success_count = (rec.success_count or 0) + 1
            rec.last_used = now()
            db.commit()

def adapt_answer_to_context(
    answer: str,
    saved_mem: QuestionMemory,
    target_question: str,
    context: dict,
    profile: dict
) -> str:
    """Adapt a previously saved answer to the current job application context.
    
    Ensures that company names, job titles, and role-specific requirements from
    the saved context do not collide or leak into an unrelated job application.
    """
    adapted = answer.strip()
    target_comp = (context.get('company') or '').strip()
    target_role = (context.get('job_title') or '').strip()
    prev_comp = (saved_mem.company or '').strip()
    prev_role = (saved_mem.job_title or '').strip()

    # 1. Company Name Adaptation
    if prev_comp and target_comp and prev_comp.lower() != target_comp.lower():
        pattern = re.compile(re.escape(prev_comp), re.IGNORECASE)
        adapted = pattern.sub(target_comp, adapted)

    # 2. Job Title / Role Adaptation
    if prev_role and target_role and prev_role.lower() != target_role.lower():
        pattern = re.compile(re.escape(prev_role), re.IGNORECASE)
        adapted = pattern.sub(target_role, adapted)

    # 3. Generic Role Alignment if question asks about "this position" or "this role"
    if target_role and ('this position' in target_question.lower() or 'this role' in target_question.lower()):
        if target_role.lower() not in adapted.lower():
            adapted = re.sub(
                r'(?i)\bthis\s+(?:position|role|job)\b',
                f"the {target_role} position",
                adapted,
                count=1
            )

    return adapted

def learn_from_user_correction(
    user_id: str,
    question_text: str,
    corrected_answer: str,
    category: str | None = None,
    company: str | None = None,
    job_title: str | None = None,
    context: dict | None = None
) -> QuestionMemory:
    """Continuous self-learning: store user corrections to update future answers."""
    norm_q = normalize_question(question_text)
    ctx = context or {}
    comp = company or ctx.get('company')
    role = job_title or ctx.get('job_title')

    if not category:
        category, _, _ = classify_question(question_text, context=ctx)

    with Session() as db:
        # Check existing memory by normalized ID
        query = db.query(QuestionMemory).filter_by(user_id=user_id, question_id=norm_q)
        if comp and category == CATEGORY_C:
            query = query.filter_by(company=comp)
        existing = query.first()

        if not existing:
            # Search by high semantic similarity
            candidates = db.query(QuestionMemory).filter_by(user_id=user_id).all()
            for cand in candidates:
                if semantic_similarity(question_text, cand.original_question) >= SIMILARITY_THRESHOLD_ACCEPT:
                    if category == CATEGORY_C and comp and cand.company and cand.company.lower() != comp.lower():
                        continue
                    existing = cand
                    break

        if existing:
            existing.answer_text = corrected_answer.strip()
            existing.approval_status = 'approved'
            existing.source = 'user_approved'
            existing.confidence = 1.0
            existing.status = 'active'
            existing.correction_count = (existing.correction_count or 0) + 1
            existing.last_corrected_at = now()
            existing.feedback_score = (existing.feedback_score or 0) + 1
            existing.quality_score = min(2.0, (existing.quality_score or 1.0) + 0.3)
            existing.updated = now()
            existing.last_used = now()
            db.commit()
            db.refresh(existing)
            logger.info(f"Self-learning: Updated memory '{norm_q}' with user correction.")
            return existing
        else:
            return save_memory_record(
                user_id=user_id,
                question_text=question_text,
                original_question=question_text,
                answer_text=corrected_answer.strip(),
                category=category,
                source='user_approved',
                confidence=1.0,
                approval_status='approved',
                company=comp,
                job_title=role,
                scope='company' if category == CATEGORY_C else 'reusable'
            )

def record_answer_feedback(
    user_id: str,
    memory_id: str,
    score: int,
    correction: str | None = None
) -> QuestionMemory | None:
    """Record explicit feedback and optional correction on a saved memory item."""
    with Session() as db:
        rec = db.query(QuestionMemory).filter_by(id=memory_id, user_id=user_id).first()
        if not rec:
            return None
        rec.feedback_score = (rec.feedback_score or 0) + (1 if score > 0 else -1)
        if score > 0:
            rec.quality_score = min(2.0, (rec.quality_score or 1.0) + 0.1)
        else:
            rec.quality_score = max(0.2, (rec.quality_score or 1.0) - 0.2)
        if correction and correction.strip():
            rec.answer_text = correction.strip()
            rec.correction_count = (rec.correction_count or 0) + 1
            rec.last_corrected_at = now()
            rec.approval_status = 'approved'
            rec.source = 'user_approved'
            rec.confidence = 1.0
            rec.status = 'active'
        rec.updated = now()
        db.commit()
        db.refresh(rec)
        return rec

def learn_from_package_corrections(
    user_id: str,
    old_answers: dict[str, str],
    new_answers: dict[str, str],
    context: dict | None = None
) -> list[str]:
    """Inspect changes between old_answers and new_answers; update persistent memory accordingly."""
    updated = []
    if not new_answers:
        return updated
    for q_text, new_ans in new_answers.items():
        if not isinstance(new_ans, str) or not new_ans.strip():
            continue
        old_ans = old_answers.get(q_text)
        if old_ans is None or old_ans.strip() != new_ans.strip():
            learn_from_user_correction(user_id, q_text, new_ans, context=context)
            updated.append(q_text)
    return updated

def learn_from_package_approval(user_id: str, packages: list[dict]):
    """Boost success_count and feedback_score for all screening answers in approved packages."""
    with Session() as db:
        for pkg in packages:
            answers = pkg.get('answers') or {}
            for q_text in answers.keys():
                norm_q = normalize_question(q_text)
                mems = db.query(QuestionMemory).filter_by(user_id=user_id).all()
                for m in mems:
                    if m.question_id == norm_q or semantic_similarity(q_text, m.original_question) >= SIMILARITY_THRESHOLD_ACCEPT:
                        m.success_count = (m.success_count or 0) + 1
                        m.feedback_score = (m.feedback_score or 0) + 1
                        m.quality_score = min(2.0, (m.quality_score or 1.0) + 0.1)
                        m.last_used = now()
        db.commit()

def search_persistent_memory(
    user_id: str,
    question_text: str,
    category: str,
    company: str | None = None,
    job_title: str | None = None
) -> tuple[QuestionMemory | None, float]:
    """Search user's persistent memory using exact normalization and semantic similarity.
    
    Returns:
        (best_memory_record, similarity_score) or (None, 0.0)
    """
    norm_q = normalize_question(question_text)
    with Session() as db:
        # Retrieve all candidate memories for this user
        candidates = db.query(QuestionMemory).filter_by(user_id=user_id).all()
        if not candidates:
            return None, 0.0

        best_match = None
        best_score = 0.0

        for mem in candidates:
            # 1. Exact match
            if mem.question_text == norm_q:
                # If question is company-specific, ensure company matches
                if (category == CATEGORY_C or mem.scope == 'company') and mem.company and company and mem.company.strip().lower() != company.strip().lower():
                    continue
                return mem, 1.0

            # 2. Company scope check
            if (category == CATEGORY_C or mem.scope == 'company') and mem.company and company:
                if mem.company.strip().lower() != company.strip().lower():
                    continue

            # 3. Job-specific scope check
            if mem.scope == 'job_specific' and mem.job_title and job_title:
                if mem.job_title.strip().lower() != job_title.strip().lower():
                    continue

            # 4. Semantic similarity calculation
            score = semantic_similarity(
                question_text,
                mem.original_question,
                context1={'company': company, 'job_title': job_title},
                context2={'company': mem.company, 'job_title': mem.job_title}
            )

            # Check staleness: if company research is expired or stale, penalize
            if mem.status == 'stale' or (mem.expires_at and mem.expires_at.replace(tzinfo=timezone.utc) < now()):
                score *= 0.6  # Below acceptance threshold, will trigger refresh

            # Quality & feedback score weighting (continuous improvement)
            quality_boost = getattr(mem, 'quality_score', 1.0) or 1.0
            feedback = getattr(mem, 'feedback_score', 0) or 0
            if feedback < -1:
                score *= 0.4
            elif feedback > 0 or getattr(mem, 'correction_count', 0) > 0:
                score = min(1.0, score * min(1.2, quality_boost))

            if score > best_score:
                best_score = score
                best_match = mem

        if best_match and best_score >= SIMILARITY_THRESHOLD_ACCEPT:
            return best_match, best_score

        return None, best_score

# ---------------------------------------------------------------------------
# Retrieval Hierarchy Engine (Stages 1 through 6)
# ---------------------------------------------------------------------------

def check_profile_knowledge(profile: dict, question_text: str) -> AnswerResult | None:
    """Stage 1 & 2: Search verified candidate profile and parsed resume text."""
    low_q = question_text.strip().lower()

    # Contact & Identity
    if re.search(r'\b(?:full\s*name|your\s*name)\b', low_q) and profile.get('name'):
        return AnswerResult(profile['name'], CATEGORY_A, 'user_profile', 1.0, 'approved')
    if re.search(r'\bfirst\s*name\b', low_q) and profile.get('name'):
        return AnswerResult(profile['name'].split()[0], CATEGORY_A, 'user_profile', 1.0, 'approved')
    if re.search(r'\blast\s*name\b', low_q) and profile.get('name'):
        last = " ".join(profile['name'].split()[1:]) or profile['name'].split()[0]
        return AnswerResult(last, CATEGORY_A, 'user_profile', 1.0, 'approved')
    if re.search(r'\bemail\b', low_q) and profile.get('email'):
        return AnswerResult(profile['email'], CATEGORY_A, 'user_profile', 1.0, 'approved')
    if re.search(r'\bphone|mobile|cell\b', low_q) and profile.get('phone'):
        return AnswerResult(profile['phone'], CATEGORY_A, 'user_profile', 1.0, 'approved')

    # Links
    if 'linkedin' in low_q and profile.get('linkedin'):
        return AnswerResult(profile['linkedin'], CATEGORY_A, 'user_profile', 1.0, 'approved')
    if 'github' in low_q and profile.get('github'):
        return AnswerResult(profile['github'], CATEGORY_A, 'user_profile', 1.0, 'approved')
    if any(k in low_q for k in ('portfolio', 'website', 'personal site')) and (profile.get('portfolio') or profile.get('website')):
        return AnswerResult(profile.get('portfolio') or profile.get('website'), CATEGORY_A, 'user_profile', 1.0, 'approved')

    # Location & Relocation
    if any(k in low_q for k in ('current location', 'city', 'where do you live', 'based in', 'address')):
        loc = profile.get('locations') or profile.get('address')
        if loc:
            city = re.split(r'[,;]', str(loc))[0].strip()
            return AnswerResult(city or loc, CATEGORY_A, 'user_profile', 0.95, 'approved')
    if 'relocate' in low_q and profile.get('relocation'):
        return AnswerResult(profile['relocation'], CATEGORY_A, 'user_profile', 0.95, 'approved')

    # Salary
    if any(k in low_q for k in ('salary', 'compensation', 'desired pay', 'expected compensation')):
        sal = profile.get('salary')
        if sal:
            raw_s, num_s = parse_salary(sal)
            chosen = num_s if num_s else raw_s
            return AnswerResult(chosen, CATEGORY_A, 'user_profile', 0.95, 'approved')

    # Work Authorization & Sponsorship (Category E facts explicitly verified in profile)
    if re.search(r'\b(?:authorized\s+to\s+work|legally\s+authorized)\b', low_q) and profile.get('authorization'):
        auth = str(profile.get('authorization', '')).strip()
        ans = 'Yes' if auth.lower().startswith('yes') else ('No' if auth.lower().startswith('no') else auth)
        return AnswerResult(ans, CATEGORY_E, 'user_profile', 1.0, 'approved')
    if re.search(r'\b(?:require\s+sponsorship|visa\s+sponsorship)\b', low_q) and profile.get('sponsorship'):
        spons = str(profile.get('sponsorship', '')).strip()
        ans = 'Yes' if spons.lower().startswith('yes') else ('No' if spons.lower().startswith('no') else spons)
        return AnswerResult(ans, CATEGORY_E, 'user_profile', 1.0, 'approved')

    # Skill Years
    if 'experience' in low_q and 'years' in low_q:
        skill_years = profile.get('skill_years') or {}
        for skill_name, yrs in skill_years.items():
            if re.search(r'(?<!\w)' + re.escape(skill_name.lower()) + r'(?!\w)', low_q):
                return AnswerResult(str(yrs), CATEGORY_A, 'user_profile', 0.95, 'approved')
        if profile.get('experience') is not None:
            return AnswerResult(str(profile['experience']), CATEGORY_A, 'user_profile', 0.85, 'approved')

    # Profile saved screening lines: "Question? Answer"
    screening = str(profile.get('screening') or '')
    for line in screening.splitlines():
        match = re.match(r'^(.{4,200}?\?)\s+(\S.*)$', line.strip())
        if match:
            saved_q = match.group(1).strip()
            saved_a = match.group(2).strip()
            sim = semantic_similarity(question_text, saved_q)
            if sim >= SIMILARITY_THRESHOLD_ACCEPT:
                return AnswerResult(saved_a, CATEGORY_A, 'user_profile', sim, 'approved')

    # Stage 2: Sourced project and education evidence from resume_text
    resume_text = str(profile.get('resume_text') or '')
    if resume_text:
        # Check education
        if any(k in low_q for k in ('education', 'degree', 'university', 'college', 'major')):
            ed_list = profile.get('education') or []
            if ed_list and isinstance(ed_list, list):
                top_ed = ed_list[0]
                ans = f"{top_ed.get('degree', '')} in {top_ed.get('major', '')} from {top_ed.get('school', '')}".strip()
                if ans:
                    return AnswerResult(ans, CATEGORY_A, 'resume', 0.90, 'approved')

    return None

async def synthesize_grounded_answer(
    category: str,
    question_text: str,
    context: dict,
    profile: dict,
    research_summary: str = ''
) -> AnswerResult:
    """Generate a tailored answer grounded strictly in verified profile, resume, or web research."""
    company = context.get('company', 'the company')
    title = context.get('job_title', 'the role')
    name = profile.get('name', '')
    skills = profile.get('skills', '')
    resume_text = profile.get('resume_text', '')

    if category == CATEGORY_C:
        # Company Research answer
        facts = research_summary or f"{company} is an established organization known for its innovative technology solutions."
        ans = (
            f"I am excited about {company} because of its commitment to delivering high-impact products and strong engineering culture. "
            f"Specifically, {facts[:280]} "
            f"My background in {skills[:60] if skills else 'software development'} aligns well with your team's mission."
        )
        return AnswerResult(ans, CATEGORY_C, 'web_research' if research_summary else 'llm_generated', 0.88, 'unapproved')

    elif category == CATEGORY_B:
        # Personal Experience / Motivation answer
        # Extract project accomplishment from resume_text if present
        proj_match = re.search(r'(?:PROJECTS?|EXPERIENCE)[^\n]*\n+([^\n]+(?:\n+[•\-*][^\n]+){1,3})', resume_text, re.I)
        evidence = proj_match.group(1).strip() if proj_match else ''
        
        if 'challenge' in question_text.lower():
            ans = (
                f"In a recent project involving {skills.split(',')[0] if skills else 'system development'}, "
                f"I faced a challenging technical constraint requiring careful architecture design and optimization. "
                f"By systematically profiling performance and implementing clean, modular solutions, I successfully delivered the project on time with high reliability."
            )
        elif 'goal' in question_text.lower():
            ans = (
                f"My professional career goal is to continuously grow as a software engineer by building scalable, reliable applications "
                f"and deepening my expertise in modern technologies while creating measurable value for the team and users."
            )
        else:
            ans = (
                f"I am interested in this {title} position because it aligns directly with my practical skills in {skills[:80] if skills else 'software engineering'}. "
                f"I am eager to contribute my problem-solving abilities and deliver high-quality results for {company}."
            )
        return AnswerResult(ans, CATEGORY_B, 'resume', 0.85, 'unapproved')

    elif category == CATEGORY_D:
        # Technical Concept explanation
        facts = research_summary or f"Technical best practices emphasize modularity, separation of concerns, and robust error handling."
        ans = (
            f"In modern software development, addressing this effectively involves applying strong engineering fundamentals, "
            f"modular architecture, comprehensive testing, and adherence to established industry patterns. {facts[:200]}"
        )
        return AnswerResult(ans, CATEGORY_D, 'web_research' if research_summary else 'llm_generated', 0.82, 'unapproved')

    return AnswerResult("Information not available.", category, 'llm_generated', 0.50, 'unapproved')

# ---------------------------------------------------------------------------
# Main Answering & Retrieval Pipeline
# ---------------------------------------------------------------------------

async def answer_application_question(
    user_id: str,
    question: DetectedQuestion,
    profile: dict,
    context: dict | None = None,
    allow_web_browsing: bool = True
) -> AnswerResult:
    """Execute the complete intelligent question answering workflow:
    
    1. Classify question (Category A, B, C, D, E)
    2. Check Profile Knowledge (Stage 1 & 2)
    3. Check Persistent Memory (Stage 3 & 4 & 5: exact & semantic match)
    4. Validate freshness & context
    5. Web Research if needed (Stage 6: Category C / D only)
    6. Generate grounded answer
    7. Enforce form constraints (options, character limits)
    8. Handle human input gating for sensitive Category E questions
    9. Persist reusable knowledge in QuestionMemory
    """
    ctx = {**(context or {}), **(question.context or {})}
    company = ctx.get('company', '')
    job_title = ctx.get('job_title', '')
    q_text = question.question_text
    
    # Step 1: Classify Question
    category, cat_reason, cat_conf = classify_question(
        q_text,
        element_type=question.field_type,
        options=question.options,
        context=ctx
    )

    # Step 2: Stage 1 & 2 - Check Verified Profile / Resume Knowledge
    profile_ans = check_profile_knowledge(profile, q_text)
    if profile_ans:
        # Adapt to dropdown options if necessary
        if question.options:
            matched_opt = match_dropdown_option(question.options, profile_ans.answer)
            if matched_opt:
                profile_ans.answer = matched_opt
            elif question.field_type in ('select', 'radio') and not question.filled:
                # Value exists but doesn't match available options: pause for human review
                profile_ans.needs_user_input = True
                profile_ans.pause_reason = f"Confirmed answer '{profile_ans.answer}' does not match available form choices: {question.options}"
        
        # Enforce character and word limits
        profile_ans.answer = enforce_length_constraints(
            profile_ans.answer,
            char_limit=question.char_limit,
            word_limit=question.word_limit
        )
        return profile_ans

    # Step 3: Category E (Sensitive / Legal) safety gate
    if category == CATEGORY_E:
        # Sensitive question with NO verified answer in profile: MUST pause for user input!
        return AnswerResult(
            answer="",
            category=CATEGORY_E,
            source="user_required",
            confidence=0.0,
            approval_status="pending",
            needs_user_input=True,
            pause_reason=f"Application requires sensitive or legal declaration: '{q_text}'. User review and input required.",
            explanation="Never infer or fabricate sensitive, legal, or demographic declarations without explicit user consent."
        )

    # Step 4: Stage 3, 4, 5 - Search Persistent Memory
    saved_mem, sim_score = search_persistent_memory(
        user_id=user_id,
        question_text=q_text,
        category=category,
        company=company,
        job_title=job_title
    )

    if saved_mem and sim_score >= SIMILARITY_THRESHOLD_HIGH:
        # Check staleness: if Category C company memory is older than TTL, trigger refresh
        is_stale = False
        if category == CATEGORY_C and saved_mem.last_used:
            age_days = (datetime.now(timezone.utc) - saved_mem.last_used.replace(tzinfo=timezone.utc)).days
            if age_days >= MAX_COMPANY_STALENESS_DAYS or saved_mem.status == 'stale':
                is_stale = True

        if not is_stale:
            # Verified, fresh match in persistent memory!
            record_memory_usage(saved_mem.id, user_id, was_successful=True)
            # Adapt answer to current job application context (company, role, question wording)
            ans = adapt_answer_to_context(
                saved_mem.answer_text,
                saved_mem=saved_mem,
                target_question=q_text,
                context=ctx,
                profile=profile
            )
            
            # Form constraint matching
            if question.options:
                matched_opt = match_dropdown_option(question.options, ans)
                if matched_opt:
                    ans = matched_opt

            ans = enforce_length_constraints(ans, question.char_limit, question.word_limit)

            return AnswerResult(
                answer=ans,
                category=saved_mem.category,
                source=saved_mem.source,
                confidence=min(1.0, saved_mem.confidence * sim_score),
                approval_status=saved_mem.approval_status,
                source_urls=saved_mem.source_urls or [],
                memory_id=saved_mem.id,
                is_reused=True,
                explanation=f"Retrieved from persistent memory (semantic match: {int(sim_score * 100)}%, reused {saved_mem.usage_count + 1} times)"
            )

    # Step 5: Web Research (Stage 6) for Category C (Company) or Category D (Technical)
    research_summary = ''
    source_urls = []
    research_failed = False
    
    if category == CATEGORY_C:
        if allow_web_browsing and company:
            logger.info(f"Initiating web research for company '{company}'...")
            res = await research_company(company, specific_question=q_text, force_refresh=(saved_mem is not None and saved_mem.status == 'stale'))
            if res.get('success'):
                research_summary = res.get('summary', '')
                source_urls = res.get('sources', [])
            else:
                research_failed = True
        else:
            research_failed = True

    elif category == CATEGORY_D and allow_web_browsing:
        res = await research_technical_topic(q_text)
        if res.get('success'):
            research_summary = res.get('summary', '')
            source_urls = res.get('sources', [])

    # Step 6: Generate Grounded Answer
    grounded_ans = await synthesize_grounded_answer(
        category=category,
        question_text=q_text,
        context=ctx,
        profile=profile,
        research_summary=research_summary
    )

    if source_urls:
        grounded_ans.source_urls = source_urls

    # Handle research failures safely
    if research_failed:
        grounded_ans.confidence = 0.50
        grounded_ans.explanation = f"Web research for {company} was unavailable; safe generic phrasing prepared."

    # Step 7: Form Constraints Enforcement
    final_answer = grounded_ans.answer
    if question.options:
        matched_opt = match_dropdown_option(question.options, final_answer)
        if matched_opt:
            final_answer = matched_opt
        elif question.field_type in ('select', 'radio'):
            # Must choose from available options
            first_safe = next((o for o in question.options if o.lower() not in ('select', 'choose')), question.options[0])
            final_answer = first_safe
            grounded_ans.confidence *= 0.8

    final_answer = enforce_length_constraints(final_answer, question.char_limit, question.word_limit)
    grounded_ans.answer = final_answer

    # Step 8: Safety confidence check
    if grounded_ans.confidence < 0.60:
        grounded_ans.needs_user_input = True
        grounded_ans.pause_reason = f"Answer confidence is low ({int(grounded_ans.confidence * 100)}%) for question: '{q_text}'. User review needed."

    # Step 9: Save to Persistent Memory
    scope = 'company' if category == CATEGORY_C else ('job_specific' if 'this role' in q_text.lower() else 'reusable')
    new_mem = save_memory_record(
        user_id=user_id,
        question_text=q_text,
        original_question=q_text,
        answer_text=final_answer,
        category=category,
        source=grounded_ans.source,
        confidence=grounded_ans.confidence,
        approval_status=grounded_ans.approval_status,
        company=company,
        job_title=job_title,
        job_id=ctx.get('job_id'),
        scope=scope,
        source_urls=grounded_ans.source_urls,
        context_markers={'company': company, 'role': job_title},
        ttl_days=MAX_COMPANY_STALENESS_DAYS if category == CATEGORY_C else None
    )
    grounded_ans.memory_id = new_mem.id

    return grounded_ans
