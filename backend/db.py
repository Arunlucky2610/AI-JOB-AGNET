import os
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, Column, String, Text, DateTime, JSON, Boolean, ForeignKey, UniqueConstraint, Integer, Float, Index, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()
Path('data').mkdir(exist_ok=True)
URL = os.getenv('DATABASE_URL', 'sqlite:///./data/orbit.db')
engine = create_engine(URL, connect_args={'check_same_thread': False} if URL.startswith('sqlite') else {}, pool_pre_ping=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()
def now(): return datetime.now(timezone.utc)

def migrate_sqlite_schema(target_engine=None):
    """Automatically ensures any newly added columns exist in SQLite databases."""
    if target_engine is None:
        target_engine = engine
    try:
        insp = inspect(target_engine)
        if 'question_memories' in insp.get_table_names():
            columns = {col['name'] for col in insp.get_columns('question_memories')}
            missing_cols = {
                'usage_count': 'INTEGER DEFAULT 0',
                'success_count': 'INTEGER DEFAULT 0',
                'quality_score': 'FLOAT DEFAULT 1.0',
                'feedback_score': 'INTEGER DEFAULT 0',
                'correction_count': 'INTEGER DEFAULT 0',
                'last_corrected_at': 'DATETIME',
                'scope': "VARCHAR DEFAULT 'reusable'",
                'context_markers': "JSON DEFAULT '{}'",
                'status': "VARCHAR DEFAULT 'active'",
                'expires_at': 'DATETIME',
            }
            with target_engine.connect() as conn:
                for col_name, col_type in missing_cols.items():
                    if col_name not in columns:
                        conn.execute(text(f"ALTER TABLE question_memories ADD COLUMN {col_name} {col_type}"))
                conn.commit()

        if 'discovery_runs' in insp.get_table_names():
            columns = {col['name'] for col in insp.get_columns('discovery_runs')}
            missing_run_cols = {
                'phase': "VARCHAR DEFAULT 'ready'",
                'progress': "JSON DEFAULT '{}'",
                'search_config': "JSON DEFAULT '{}'",
                'events': "JSON DEFAULT '[]'",
                'results_count': "INTEGER DEFAULT 0",
                'error': "TEXT",
                'warnings': "JSON DEFAULT '[]'",
                'completed_at': "DATETIME",
            }
            with target_engine.connect() as conn:
                for col_name, col_type in missing_run_cols.items():
                    if col_name not in columns:
                        conn.execute(text(f"ALTER TABLE discovery_runs ADD COLUMN {col_name} {col_type}"))
                conn.commit()
    except Exception:
        pass

class User(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password = Column(Text, nullable=False)
    profile = Column(JSON, default=dict)
    settings = Column(JSON, default=dict)
    demo = Column(String, default='false')

class Login(Base):
    __tablename__ = 'sessions'
    token = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    expires = Column(DateTime(timezone=True), nullable=False)

class Job(Base):
    __tablename__ = 'jobs'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    canonical = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    created = Column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint('user_id', 'canonical'),)

class Application(Base):
    __tablename__ = 'applications'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    job_id = Column(String, ForeignKey('jobs.id'), nullable=False)
    status = Column(String, default='prepared')
    package = Column(JSON, default=dict)
    approved_hash = Column(String, nullable=True)
    events = Column(JSON, default=list)
    browser = Column(JSON, default=dict)
    created = Column(DateTime(timezone=True), default=now)
    updated = Column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint('user_id', 'job_id'),)

class AgentRun(Base):
    __tablename__ = 'agent_runs'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    status = Column(String, default='running')
    phase = Column(String, default='searching')
    events = Column(JSON, default=list)
    browser = Column(JSON, default=dict)
    state = Column(JSON, default=dict)
    created = Column(DateTime(timezone=True), default=now)
    updated = Column(DateTime(timezone=True), default=now)

class BrowserContext(Base):
    """A user's saved Browserbase browser profile: keeps LinkedIn logins across sessions."""
    __tablename__ = 'browser_contexts'
    user_id = Column(String, ForeignKey('users.id'), primary_key=True)
    context_id = Column(String, nullable=False)
    created = Column(DateTime(timezone=True), default=now)

class PlatformConnection(Base):
    """Whether the user has confirmed signing in to a job platform (LinkedIn) in their saved
    Browserbase profile, set by /api/connections/<platform>/check (or by a run seeing them past its own
    sign-in wall). A run's own sign-in check at start is still the final authority if a saved session later
    expires; this table only gates the "Start agent" prompt so the person is not asked to sign in twice."""
    __tablename__ = 'platform_connections'
    user_id = Column(String, ForeignKey('users.id'), primary_key=True)
    platform = Column(String, primary_key=True)
    connected = Column(Boolean, default=False)
    checked = Column(DateTime(timezone=True), default=now)

class SkippedJob(Base):
    """A posting the agent opened and rejected without a model review (too senior, wrong title, no Easy Apply...), so later runs do not open it again."""
    __tablename__ = 'skipped_jobs'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    canonical = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    profile_hash = Column(String)   # set when the verdict depends on the profile; the memory is ignored once the profile changes
    created = Column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint('user_id', 'canonical'),)

class Outcome(Base):
    """What happened after an application was submitted: the employer's response and the person's own verdict on
    the fit. This is how Orbit measures whether its picks were good (shortlist conversion), not just how many it sent."""
    __tablename__ = 'outcomes'
    application_id = Column(String, ForeignKey('applications.id'), primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    stage = Column(String, default='waiting')   # waiting, shortlisted, assessment, interview, offer, rejected, no_response
    fit_feedback = Column(String, nullable=True)   # 'up' or 'down'
    note = Column(Text, default='')
    updated = Column(DateTime(timezone=True), default=now)

class QuestionMemory(Base):
    """Persistent question-and-answer memory for job applications.
    Stores verified, researched, and approved answers with semantic search,
    scoping (profile, reusable, company, job_specific, sensitive), and tenant isolation.
    """
    __tablename__ = 'question_memories'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    question_id = Column(String, nullable=False, index=True)     # Normalized key/hash for deduplication
    question_text = Column(Text, nullable=False)                 # Normalized question text
    original_question = Column(Text, nullable=False)             # Exact encountered wording
    embedding = Column(JSON, default=list)                       # Dense vector / semantic token representation
    answer_text = Column(Text, nullable=False)                   # The answer content
    category = Column(String, nullable=False)                    # A_personal_info | B_experience | C_company_research | D_technical | E_sensitive
    source = Column(String, nullable=False)                      # user_profile | resume | user_approved | company_memory | web_research | llm_generated
    source_urls = Column(JSON, default=list)                     # Citations / reference URLs
    confidence = Column(Float, default=1.0)                      # 0.0 to 1.0 confidence score
    approval_status = Column(String, default='unapproved')       # approved | unapproved | pending | rejected
    company = Column(String, nullable=True, index=True)          # Associated employer name
    job_title = Column(String, nullable=True)                    # Associated vacancy title
    job_id = Column(String, nullable=True)                       # Specific Job record ID
    scope = Column(String, default='reusable')                   # profile | reusable | company | job_specific | sensitive
    context_markers = Column(JSON, default=dict)                 # Context dependencies (role, location, salary)
    usage_count = Column(Integer, default=0)                     # How many times this answer was reused
    success_count = Column(Integer, default=0)                   # How many times this answer led to a successful application
    quality_score = Column(Float, default=1.0)                   # Quality and confidence rating boosted by approvals and feedback
    feedback_score = Column(Integer, default=0)                  # Net user feedback score (+1 for approved/accepted, -1 for rejected)
    correction_count = Column(Integer, default=0)                # How many times the user explicitly edited/corrected this answer
    last_corrected_at = Column(DateTime(timezone=True), nullable=True) # When the user last edited this answer
    created = Column(DateTime(timezone=True), default=now)
    updated = Column(DateTime(timezone=True), default=now)
    last_used = Column(DateTime(timezone=True), default=now)
    status = Column(String, default='active')                     # active | stale | expired
    expires_at = Column(DateTime(timezone=True), nullable=True)  # TTL / staleness limit
    __table_args__ = (
        Index('ix_qm_user_cat', 'user_id', 'category'),
        Index('ix_qm_user_comp', 'user_id', 'company'),
        Index('ix_qm_user_scope', 'user_id', 'scope'),
    )

class Resume(Base):
    """Uploaded user resumes with physical file reference and extraction state."""
    __tablename__ = 'resumes'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, default=0)
    file_hash = Column(String, nullable=False)
    extracted_text = Column(Text, nullable=False)
    structured_data = Column(JSON, default=dict)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created = Column(DateTime(timezone=True), default=now)

class ResumeVersion(Base):
    """Audit and version history for candidate resumes."""
    __tablename__ = 'resume_versions'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    resume_id = Column(String, ForeignKey('resumes.id'), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    extracted_text = Column(Text, nullable=False)
    structured_data = Column(JSON, default=dict)
    changes_summary = Column(Text, default='')
    created = Column(DateTime(timezone=True), default=now)

class JobSource(Base):
    """Configured job discovery sources and their adapter statuses."""
    __tablename__ = 'job_sources'
    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=False)
    adapter_type = Column(String, default='browser') # 'api' | 'feed' | 'browser' | 'jobspy'
    enabled = Column(Boolean, default=True)
    auth_required = Column(Boolean, default=False)
    capabilities = Column(JSON, default=list) # ['search', 'apply', 'remote_filter']
    config = Column(JSON, default=dict)
    last_sync = Column(DateTime(timezone=True), nullable=True)

class JobMatchEvaluation(Base):
    """Deep AI job compatibility evaluation and scoring breakdown."""
    __tablename__ = 'job_match_evaluations'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    job_id = Column(String, ForeignKey('jobs.id'), nullable=False, index=True)
    match_score = Column(Float, nullable=False)
    matching_skills = Column(JSON, default=list)
    missing_required_skills = Column(JSON, default=list)
    missing_preferred_skills = Column(JSON, default=list)
    experience_alignment = Column(Text, default='')
    location_alignment = Column(Text, default='')
    salary_alignment = Column(Text, default='')
    eligibility_concerns = Column(JSON, default=list)
    recommendation = Column(String, default='')
    explanation = Column(Text, default='')
    raw_model_response = Column(JSON, default=dict)
    created = Column(DateTime(timezone=True), default=now)

class ApplicationMaterial(Base):
    """Generated tailored documents for job applications."""
    __tablename__ = 'application_materials'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    application_id = Column(String, ForeignKey('applications.id'), nullable=True, index=True)
    job_id = Column(String, ForeignKey('jobs.id'), nullable=False, index=True)
    material_type = Column(String, nullable=False) # 'tailored_resume' | 'cover_letter' | 'recruiter_message'
    content = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    diff_summary = Column(Text, default='')
    user_approved = Column(Boolean, default=False)
    created = Column(DateTime(timezone=True), default=now)
    updated = Column(DateTime(timezone=True), default=now)

class AuditEvent(Base):
    """Tamper-evident audit trails for all sensitive agent and user operations."""
    __tablename__ = 'audit_events'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    event_type = Column(String, nullable=False) # 'AUTH' | 'PROFILE' | 'RESUME' | 'DISCOVERY' | 'SUBMISSION'
    details = Column(JSON, default=dict)
    ip_address = Column(String, nullable=True)
    created = Column(DateTime(timezone=True), default=now)

class IntegrationCredential(Base):
    """Status and configuration for external services (OpenRouter, Browserbase)."""
    __tablename__ = 'integration_credentials'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    provider = Column(String, nullable=False) # 'openrouter' | 'browserbase' | 'linkedin' | 'indeed' | 'naukri'
    status = Column(String, default='disconnected') # 'connected' | 'disconnected' | 'invalid'
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSON, default=dict)
    created = Column(DateTime(timezone=True), default=now)
    updated = Column(DateTime(timezone=True), default=now)

class UserApproval(Base):
    """Explicit recorded user approvals for application submission packages."""
    __tablename__ = 'user_approvals'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    application_id = Column(String, ForeignKey('applications.id'), nullable=False, index=True)
    package_hash = Column(String, nullable=False)
    mode = Column(String, default='each') # 'each' | 'batch' | 'automatic'
    approved_at = Column(DateTime(timezone=True), default=now)
    scope = Column(String, default='single')
    status = Column(String, default='valid') # 'valid' | 'invalidated' | 'used'

class DiscoveryRun(Base):
    """Tracks asynchronous job discovery execution, live stages, and telemetry."""
    __tablename__ = 'discovery_runs'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    status = Column(String, default='idle') # 'idle' | 'running' | 'completed' | 'completed_with_warnings' | 'failed' | 'cancelled'
    phase = Column(String, default='ready') # 'validating' | 'generating_queries' | 'searching' | 'extracting' | 'deduplicating' | 'matching' | 'saving' | 'completed'
    progress = Column(JSON, default=dict)
    search_config = Column(JSON, default=dict)
    events = Column(JSON, default=list)
    results_count = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    warnings = Column(JSON, default=list)
    created = Column(DateTime(timezone=True), default=now)
    completed_at = Column(DateTime(timezone=True), nullable=True)


def init():
    Base.metadata.create_all(engine)
    migrate_sqlite_schema(engine)
    with Session() as db:
        for a in db.query(Application).filter(Application.status.in_(['running','submitting'])):
            a.status = 'needs_verification' if a.status == 'submitting' else 'needs_input'
            a.events = [*a.events, {'time': now().isoformat(), 'text': 'Worker restarted. Review the application before continuing.'}]
        db.commit()

        for run in db.query(AgentRun).filter_by(status='running'):
            run.status='paused'
            run.events=[*run.events,{'time':now().isoformat(),'text':'Server restarted. Resume the agent to continue.'}]
        db.commit()
