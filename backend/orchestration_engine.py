"""Central Application Orchestration Engine.
Implements the 11-state Human-in-the-Loop lifecycle and the JobApplicationProvider interface.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

class ApplicationState(str, Enum):
    READY = "READY"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    OTP_REQUIRED = "OTP_REQUIRED"
    CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
    USER_REVIEW_REQUIRED = "USER_REVIEW_REQUIRED"
    SUBMISSION_READY = "SUBMISSION_READY"
    SUBMISSION_PENDING = "SUBMISSION_PENDING"
    SUBMITTED = "SUBMITTED"
    SUBMISSION_UNCERTAIN = "SUBMISSION_UNCERTAIN"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

@dataclass
class ApplicationSession:
    session_id: str
    user_id: str
    job_id: str
    job_payload: Dict[str, Any]
    current_state: ApplicationState = ApplicationState.READY
    browser_session_id: Optional[str] = None
    live_url: Optional[str] = None
    form_fields: List[Dict[str, Any]] = field(default_factory=list)
    mapped_data: Dict[str, Any] = field(default_factory=dict)
    materials: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Tuple_Result:
    confirmed: bool
    state: ApplicationState
    confirmation_id: Optional[str] = None
    receipt_text: Optional[str] = None
    evidence_path: Optional[str] = None

class JobApplicationProvider(ABC):
    @property
    @abstractmethod
    def platform_name(self) -> str:
        pass

    @abstractmethod
    def supports(self, job: Dict[str, Any]) -> bool:
        """Return True if this provider can handle applying to this job."""
        pass

    @abstractmethod
    def get_application_method(self, job: Dict[str, Any]) -> str:
        """Return method: e.g. 'Easy Apply', 'Indeed Apply', 'Naukri Apply', 'External'."""
        pass

    @abstractmethod
    async def initialize_session(self, job: Dict[str, Any], user: Dict[str, Any]) -> ApplicationSession:
        """Create session and establish browser or API context."""
        pass

    @abstractmethod
    async def inspect_form(self, session: ApplicationSession) -> List[Dict[str, Any]]:
        """Discover form inputs, question labels, and file upload slots."""
        pass

    @abstractmethod
    async def map_profile_to_fields(self, form_fields: List[Dict[str, Any]], profile: Dict[str, Any]) -> Dict[str, Any]:
        """Map candidate profile facts to detected form elements."""
        pass

    @abstractmethod
    async def fill_form(self, session: ApplicationSession, mapped_data: Dict[str, Any]) -> ApplicationSession:
        """Populate form fields in browser."""
        pass

    @abstractmethod
    async def validate_form(self, session: ApplicationSession) -> bool:
        """Verify field values, mandatory inputs, and form completeness."""
        pass

    @abstractmethod
    async def request_user_review(self, session: ApplicationSession) -> ApplicationSession:
        """Transition into USER_REVIEW_REQUIRED and pause execution for human verification."""
        pass

    @abstractmethod
    async def submit_application(self, session: ApplicationSession, approval: Dict[str, Any]) -> ApplicationSession:
        """Execute submission only when explicit authorized approval is provided."""
        pass

    @abstractmethod
    async def verify_submission(self, session: ApplicationSession) -> Tuple_Result:
        """Determine whether submission succeeded: confirmed, uncertain, or failed."""
        pass

    @abstractmethod
    async def close_session(self, session: ApplicationSession) -> None:
        """Safely clean up browser session resources."""
        pass

@dataclass
class Tuple_Result:
    confirmed: bool
    state: ApplicationState
    confirmation_id: Optional[str] = None
    receipt_text: Optional[str] = None
    evidence_path: Optional[str] = None
