"""Intelligent question classifier.

Categorizes detected application questions into:
- Category A: Personal Information (Profile/Resume)
- Category B: Personal Preferences and Experience (Resume projects/career goals)
- Category C: Company and Job Research (Web research/company memory)
- Category D: Technical and General Knowledge (Domain/technical concepts)
- Category E: Sensitive, Legal, or High-Impact Questions (Authorizations, disclosures, background checks)
"""
import re

CATEGORY_A = 'A_personal_info'
CATEGORY_B = 'B_experience'
CATEGORY_C = 'C_company_research'
CATEGORY_D = 'D_technical'
CATEGORY_E = 'E_sensitive'

# Patterns for Category E: Sensitive, Legal, or High-Impact
SENSITIVE_PATTERNS = [
    r'\b(?:legally\s+authorized|work\s+authorization|authorized\s+to\s+work|eligible\s+to\s+work)\b',
    r'\b(?:visa\s+sponsorship|require\s+sponsorship|sponsor\s+(?:a\s+)?visa|future\s+sponsorship)\b',
    r'\b(?:criminal\s+history|convicted|felony|misdemeanor|plead\s+guilty|crime)\b',
    r'\b(?:disability\s+status|disability|accommodations?|impairment)\b',
    r'\b(?:veteran\s+status|military\s+service|protected\s+veteran)\b',
    r'\b(?:gender\s+identity|race|ethnicity|demographic|sexual\s+orientation)\b',
    r'\b(?:background\s+check|drug\s+(?:screen|test)|security\s+clearance)\b',
    r'\b(?:certify\s+that|legally\s+binding|under\s+penalty\s+of\s+perjury|attest|declaration)\b',
    r'\b(?:consent\s+to|terms\s+and\s+conditions|privacy\s+policy|fcra)\b',
]

# Patterns for Category A: Personal Information
PERSONAL_INFO_PATTERNS = [
    r'\b(?:first\s*name|last\s*name|full\s*name|surname|given\s*name)\b',
    r'\b(?:email\s*(?:address)?|phone\s*(?:number)?|mobile|cell)\b',
    r'\b(?:current\s*(?:location|city|address)|where\s*(?:do\s*you|are\s*you)\s*(?:currently\s*)?(?:live|located|based)|postal\s*code|zip\s*code)\b',
    r'\b(?:linkedin\s*(?:url|profile)?|github\s*(?:url|profile)?|portfolio\s*(?:url|link)?|website\s*url|personal\s*site)\b',
    r'\b(?:highest\s*(?:level\s*of\s*)?education|degree|gpa|university|college|school|graduation\s*year|major)\b',
    r'\b(?:years\s*of\s*experience|total\s*(?:years\s*of\s*)?experience|how\s*many\s*years)\b',
    r'\b(?:notice\s*period|how\s*soon\s*can\s*you\s*start|earliest\s*start\s*date|availability)\b',
    r'\b(?:expected\s*(?:annual\s*)?salary|salary\s*expectation|desired\s*salary|compensation|hourly\s*rate)\b',
    r'\b(?:willing\s*to\s*relocate|relocation|commute\s*to)\b',
]

# Patterns for Category C: Company & Employer Research
COMPANY_RESEARCH_PATTERNS = [
    r'\b(?:why\s*(?:do\s*you\s*want\s*to|would\s*you\s*like\s*to)\s*(?:join|work\s*(?:at|for)|be\s*part\s*of)\s*(?:our\s*company|this\s*company|us|the\s*team)?)\b',
    r'\b(?:what\s*(?:interests\s*you|attracts\s*you)\s*(?:about|in)\s*(?:working\s*(?:here|with\s*us|at|for)|our\s*company|our\s*mission|our\s*products?))\b',
    r'\b(?:what\s*do\s*you\s*know\s*about\s*(?:our\s*company|our\s*organization|us|our\s*mission|our\s*products?))\b',
    r'\b(?:how\s*did\s*you\s*hear\s*about\s*us|why\s*are\s*you\s*interested\s*in\s*(?:this\s*company|joining\s*us))\b',
    r'\b(?:familiar\s*with\s*our\s*product|used\s*our\s*product|thoughts\s*on\s*our\s*platform)\b',
]

# Patterns for Category B: Personal Preferences and Experience
EXPERIENCE_PATTERNS = [
    r'\b(?:why\s*are\s*you\s*interested\s*in\s*this\s*(?:role|position|job))\b',
    r'\b(?:why\s*(?:do\s*you\s*want|are\s*you\s*applying\s*for)\s*this\s*(?:role|position|job))\b',
    r'\b(?:what\s*makes\s*you\s*(?:a\s*good|the\s*best|qualified|an\s*ideal)\s*candidate)\b',
    r'\b(?:describe\s*(?:a|your)\s*(?:challenging|difficult|complex)\s*(?:project|problem|situation|experience))\b',
    r'\b(?:what\s*are\s*your\s*(?:career\s*)?goals|where\s*do\s*you\s*see\s*yourself\s*in\s*\d+\s*years)\b',
    r'\b(?:greatest\s*(?:professional\s*)?(?:achievement|accomplishment|strength))\b',
    r'\b(?:describe\s*(?:a\s*time|an\s*example)\s*when\s*you)\b',
    r'\b(?:tell\s*(?:us|me)\s*about\s*yourself|walk\s*me\s*through\s*your\s*resume)\b',
    r'\b(?:leadership\s*style|conflict\s*resolution|teamwork\s*experience)\b',
]

# Patterns for Category D: Technical & General Knowledge
TECHNICAL_PATTERNS = [
    r'\b(?:explain\s*(?:the\s*difference\s*between|how|what\s*is|the\s*concept\s*of))\b',
    r'\b(?:how\s*(?:would\s*you|do\s*you)\s*(?:design|implement|debug|architect|scale|optimize))\b',
    r'\b(?:what\s*is\s*(?:your\s*approach|your\s*strategy)\s*to\s*(?:testing|refactoring|security|performance))\b',
    r'\b(?:difference\s*between\s*[\w\s+#]+and\s*[\w\s+#]+)\b',
    r'\b(?:technical\s*challenge|coding\s*standards|system\s*design|algorithm|data\s*structure)\b',
]

def classify_question(question_text: str, element_type: str = '', options: list = None, context: dict = None) -> tuple[str, str, float]:
    """Classify a question into Category A, B, C, D, or E.
    
    Returns:
        (category, reason, confidence)
    """
    text = (question_text or '').strip()
    low = text.lower()
    
    # Check Category E first: Safety and legal protections outrank all others
    for pat in SENSITIVE_PATTERNS:
        if re.search(pat, low):
            return CATEGORY_E, "Sensitive, legal, or high-impact disclosure requiring verified consent or explicit user input", 0.98

    # Check company specific name in text if context contains company
    company_name = ((context or {}).get('company') or '').strip().lower()
    if company_name and len(company_name) >= 3:
        if re.search(r'\b(?:why|what|how)\b.*?\b' + re.escape(company_name) + r'\b', low):
            return CATEGORY_C, f"Research question regarding company ({company_name})", 0.95

    # Check Category C: Company & Employer Research
    for pat in COMPANY_RESEARCH_PATTERNS:
        if re.search(pat, low):
            return CATEGORY_C, "Company knowledge or organizational interest question", 0.92

    # Check Category A: Personal Information
    for pat in PERSONAL_INFO_PATTERNS:
        if re.search(pat, low):
            return CATEGORY_A, "Personal profile, contact, or verified qualification field", 0.95

    # Check Category B: Personal Preferences and Experience
    for pat in EXPERIENCE_PATTERNS:
        if re.search(pat, low):
            return CATEGORY_B, "Personal career motivation, project experience, or candidate background", 0.90

    # Check Category D: Technical Knowledge
    for pat in TECHNICAL_PATTERNS:
        if re.search(pat, low):
            return CATEGORY_D, "Technical or domain knowledge explanation question", 0.88

    # Contextual heuristics:
    if re.search(r'\b(?:project|code|repo|architecture|database|api|framework)\b', low):
        if re.search(r'\b(?:describe|tell|your|experience)\b', low):
            return CATEGORY_B, "Candidate technical experience question", 0.80
        return CATEGORY_D, "General technical inquiry", 0.75

    if re.search(r'\b(?:why|interest|role|position|apply)\b', low):
        return CATEGORY_B, "Candidate job motivation question", 0.75

    # Fallback default: If short input, likely personal or general
    if element_type in ('select', 'radio') and options and len(options) <= 5:
        # Many yes/no screening questions
        if any(opt.strip().lower() in ('yes', 'no') for opt in options):
            if any(w in low for w in ('authorized', 'visa', 'sponsor', 'convict', 'disability')):
                return CATEGORY_E, "Sensitive screening choice", 0.95
            return CATEGORY_A, "Standard qualification screening question", 0.70

    return CATEGORY_B, "General application question evaluated from candidate profile", 0.65
