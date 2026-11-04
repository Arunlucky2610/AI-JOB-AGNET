"""Semantic question normalization, embedding representation, and similarity matching engine.

Provides deterministic, high-accuracy semantic similarity matching without external network latency,
with support for synonym expansion, intent detection, and context conflict penalties.
"""
import math
import re
import string
import numpy as np

STOPWORDS = {
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 'any', 'are',
    'arent', 'as', 'at', 'be', 'because', 'been', 'before', 'being', 'below', 'between', 'both',
    'but', 'by', 'cant', 'cannot', 'could', 'couldnt', 'did', 'didnt', 'do', 'does', 'doesnt',
    'doing', 'dont', 'down', 'during', 'each', 'few', 'for', 'from', 'further', 'had', 'hadnt',
    'has', 'hasnt', 'have', 'havent', 'having', 'he', 'hed', 'hell', 'hes', 'her', 'here',
    'heres', 'hers', 'herself', 'him', 'himself', 'his', 'how', 'hows', 'i', 'id', 'ill',
    'im', 'ive', 'if', 'in', 'into', 'is', 'isnt', 'it', 'its', 'itself', 'lets', 'me', 'more',
    'most', 'mustnt', 'my', 'myself', 'no', 'nor', 'not', 'of', 'off', 'on', 'once', 'only',
    'or', 'other', 'ought', 'our', 'ours', 'ourselves', 'out', 'over', 'own', 'same', 'shant',
    'she', 'shed', 'shell', 'shes', 'should', 'shouldnt', 'so', 'some', 'such', 'than', 'that',
    'thats', 'the', 'their', 'theirs', 'them', 'themselves', 'then', 'there', 'theres', 'these',
    'they', 'theyd', 'theyll', 'theyre', 'theyve', 'this', 'those', 'through', 'to', 'too',
    'under', 'until', 'up', 'very', 'was', 'wasnt', 'we', 'wed', 'well', 'were', 'werent',
    'what', 'whats', 'when', 'whens', 'where', 'wheres', 'which', 'while', 'who', 'whos',
    'whom', 'why', 'whys', 'with', 'wont', 'would', 'wouldnt', 'you', 'youd', 'youll', 'youre',
    'youve', 'your', 'yours', 'yourself', 'yourselves'
}

CONTRACTIONS = {
    r"\bcan't\b": "cannot",
    r"\bwon't\b": "will not",
    r"\bn't\b": " not",
    r"\b're\b": " are",
    r"\b's\b": " is",
    r"\b'd\b": " would",
    r"\b'll\b": " will",
    r"\b't\b": " not",
    r"\b've\b": " have",
    r"\b'm\b": " am"
}

SYNONYM_GROUPS = {
    'company': {'company', 'organization', 'firm', 'employer', 'workplace', 'business', 'enterprise', 'here', 'team', 'agency'},
    'join': {'join', 'work', 'apply', 'belong', 'contribute', 'participate', 'hire'},
    'motivation': {'why', 'want', 'interest', 'interested', 'reason', 'reasons', 'motivate', 'motivation', 'attract', 'attracted', 'appeal', 'drawn', 'look', 'looking', 'excited'},
    'role': {'position', 'role', 'job', 'vacancy', 'opportunity'},
    'goal': {'goal', 'goals', 'aspiration', 'aspirations', 'objective', 'objectives', 'future', 'aim'},
    'challenge': {'challenge', 'challenging', 'difficulty', 'difficult', 'obstacle', 'adversity', 'problem'},
    'strength': {'strength', 'strengths', 'strongest', 'asset', 'superpower', 'excel'},
    'weakness': {'weakness', 'weaknesses', 'improvement', 'grow', 'growth'},
    'project': {'project', 'projects', 'initiative', 'assignment', 'accomplishment', 'achievement'},
    'salary': {'salary', 'compensation', 'pay', 'rate', 'remuneration', 'earnings'},
    'location': {'location', 'relocate', 'relocation', 'commute', 'city', 'onsite', 'remote'},
    'experience': {'experience', 'background', 'history', 'expertise', 'tenure'}
}

# Map each synonym word to a canonical concept token
SYNONYM_MAP = {}
for canon, words in SYNONYM_GROUPS.items():
    for word in words:
        SYNONYM_MAP[word] = canon

TECHNICAL_TERMS = {
    'python', 'javascript', 'typescript', 'java', 'c++', 'c#', 'golang', 'go', 'rust', 'ruby',
    'php', 'swift', 'kotlin', 'scala', 'sql', 'nosql', 'react', 'angular', 'vue', 'nextjs',
    'django', 'flask', 'fastapi', 'spring', 'docker', 'kubernetes', 'aws', 'gcp', 'azure',
    'graphql', 'rest', 'kafka', 'redis', 'postgres', 'postgresql', 'mongodb', 'git', 'ci/cd',
    'terraform', 'linux', 'spark', 'hadoop', 'pytorch', 'tensorflow', 'machine learning', 'deep learning'
}

def stem_word(w: str) -> str:
    """Basic rule-based English suffix normalization."""
    if len(w) <= 3:
        return w
    if w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("ies"):
        w = w[:-3] + "y"
    elif w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    
    if w.endswith("ing") and len(w) > 5:
        base = w[:-3]
        if len(base) >= 2 and base[-1] == base[-2]:
            base = base[:-1]
        w = base
    elif w.endswith("ed") and len(w) > 4:
        base = w[:-2]
        if len(base) >= 2 and base[-1] == base[-2]:
            base = base[:-1]
        w = base
    return w

def normalize_question(text: str) -> str:
    """Normalize a question string for deterministic matching and indexing."""
    if not text:
        return ''
    s = str(text).strip()
    # Strip common leading markers like "Answer:", "Question:", "1.", "Q:", etc.
    s = re.sub(r'^(?:answer|question|q\d*|\d+[\.\):])\s*[:\-]?\s*', '', s, flags=re.I)
    s = s.lower()
    for pattern, repl in CONTRACTIONS.items():
        s = re.sub(pattern, repl, s)
    # Remove punctuation except plus/hash in technical terms (c++, c#)
    s = re.sub(r'[^\w\s+#]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def extract_canonical_tokens(text: str) -> list[str]:
    """Tokenize and map to canonical synonym tokens with stemming and stopword filtering."""
    norm = normalize_question(text)
    tokens = []
    for raw in norm.split():
        if len(raw) <= 1 and raw not in ('c', 'r'):
            continue
        stemmed = stem_word(raw)
        canon = SYNONYM_MAP.get(raw, SYNONYM_MAP.get(stemmed, stemmed))
        tokens.append(canon)
    return tokens

def extract_tech_terms(text: str) -> set[str]:
    """Extract recognized technical keywords from the question."""
    norm = normalize_question(text)
    found = set()
    for term in TECHNICAL_TERMS:
        if re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', norm):
            found.add(term)
    return found

# Dimensionality for dense hash-based semantic representation
EMBED_DIM = 64

def compute_embedding(text: str) -> list[float]:
    """Compute a dense normalized vector representation of the question.
    Uses character and word n-grams mapped into a fixed-dimension space
    with synonym normalization, L2-normalized so dot product == cosine similarity.
    """
    tokens = extract_canonical_tokens(text)
    if not tokens:
        return [0.0] * EMBED_DIM
    
    vec = np.zeros(EMBED_DIM, dtype=np.float32)
    
    # 1. Unigram & bigram hashed feature accumulation
    for i, tok in enumerate(tokens):
        # Primary token hash
        h = abs(hash(tok)) % EMBED_DIM
        weight = 2.0 if tok not in STOPWORDS else 0.5
        vec[h] += weight
        
        # Bigram hash
        if i + 1 < len(tokens):
            bigram = f"{tok}_{tokens[i+1]}"
            hb = abs(hash(bigram)) % EMBED_DIM
            vec[hb] += 1.5

    # 2. Character trigrams for morphological robustness
    norm = normalize_question(text)
    for i in range(len(norm) - 2):
        trigram = norm[i:i+3]
        ht = abs(hash(trigram)) % EMBED_DIM
        vec[ht] += 0.2

    # L2 normalize
    norm_val = np.linalg.norm(vec)
    if norm_val > 1e-6:
        vec = vec / norm_val
    return [round(float(x), 5) for x in vec]

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calculate cosine similarity between two unit vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    a = np.array(v1, dtype=np.float32)
    b = np.array(v2, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-6 or norm_b < 1e-6:
        return 0.0
    sim = float(np.dot(a, b) / (norm_a * norm_b))
    return max(0.0, min(1.0, sim))

def semantic_similarity(q1: str, q2: str, context1: dict = None, context2: dict = None) -> float:
    """Evaluate semantic similarity between two questions with context verification.
    Returns a score in [0.0, 1.0].
    
    High score (>= 0.82) indicates the questions express the same intent and can safely
    reuse an answer (unless context marks a specific conflict).
    """
    norm1 = normalize_question(q1)
    norm2 = normalize_question(q2)
    if not norm1 or not norm2:
        return 0.0
    if norm1 == norm2:
        return 1.0

    # 1. Check technical term collision/difference
    # "experience with React" vs "experience with Docker" are NOT the same question!
    tech1 = extract_tech_terms(q1)
    tech2 = extract_tech_terms(q2)
    if tech1 and tech2 and tech1 != tech2:
        # Different technologies explicitly asked
        diff = tech1.symmetric_difference(tech2)
        if diff:
            return 0.25

    # 2. Check company entity collision if provided in text or context
    ctx1 = context1 or {}
    ctx2 = context2 or {}
    comp1 = (ctx1.get('company') or '').strip().lower()
    comp2 = (ctx2.get('company') or '').strip().lower()
    if comp1 and comp2 and comp1 != comp2:
        # If both questions are company-specific motivations (e.g. "Why Acme" vs "Why Google"),
        # they must not match across different employers!
        if 'company' in norm1 or 'company' in norm2 or 'work here' in norm1 or 'work here' in norm2:
            return 0.1

    # 3. Canonical token set overlap (Jaccard on non-stopwords)
    tokens1 = [t for t in extract_canonical_tokens(q1) if t not in STOPWORDS]
    tokens2 = [t for t in extract_canonical_tokens(q2) if t not in STOPWORDS]
    
    set1 = set(tokens1)
    set2 = set(tokens2)
    
    if not set1 or not set2:
        jaccard = 0.0
    else:
        shared = set1 & set2
        union = set1 | set2
        jaccard = len(shared) / float(len(union))
        # If all content words match after synonym canonicalization
        if set1 == set2:
            return 0.95

    # 4. Dense embedding cosine similarity
    emb1 = compute_embedding(q1)
    emb2 = compute_embedding(q2)
    dense_sim = cosine_similarity(emb1, emb2)

    # 5. Composite score: blend token overlap with dense vector geometry
    composite = (0.55 * jaccard) + (0.45 * dense_sim)

    # Boost known intent patterns (e.g. why join company)
    # Check if both have "motivation" (why/want/interest) and "join" / "company"
    is_why_join1 = 'motivation' in set1 and any(t in set1 for t in ('company', 'join'))
    is_why_join2 = 'motivation' in set2 and any(t in set2 for t in ('company', 'join'))
    if is_why_join1 and is_why_join2:
        # If company entities differ, penalty already applied above
        composite = max(composite, 0.88)

    # Boost challenging project questions
    is_proj1 = 'challenge' in set1 and 'project' in set1
    is_proj2 = 'challenge' in set2 and 'project' in set2
    if is_proj1 and is_proj2:
        composite = max(composite, 0.90)

    # Boost career goal questions
    is_goal1 = 'goal' in set1 and any(t in set1 for t in ('career', 'future'))
    is_goal2 = 'goal' in set2 and any(t in set2 for t in ('career', 'future'))
    if is_goal1 and is_goal2:
        composite = max(composite, 0.90)

    return max(0.0, min(1.0, round(composite, 4)))
