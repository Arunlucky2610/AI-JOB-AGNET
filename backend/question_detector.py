"""Intelligent Question Detection Engine.

Extracts structured question objects from page snapshots:
- Question text, options, field type, required status, character/word limits, surrounding instructions.
- Filters out non-question elements (navigation, cookies, submit buttons, search bars, file inputs).
- Handles radio groups and dynamically revealed fields.
"""
import re
from typing import Any

NON_QUESTION_PATTERNS = re.compile(
    r'\b(?:search|filter|find|cookie|banner|dismiss|cancel|close|login|sign\s*in|'
    r'password|otp|verification\s*code|skip\s*to\s*main|subscribe|newsletter|'
    r'terms\s*of\s*service|privacy\s*policy|all\s*rights\s*reserved)\b',
    re.I
)

CHAR_LIMIT_PATTERN = re.compile(r'\b(?:max(?:imum)?|up\s*to|at\s*most|limit)\s*(\d{2,5})\s*(?:char|character)s?\b', re.I)
WORD_LIMIT_PATTERN = re.compile(r'\b(?:max(?:imum)?|up\s*to|at\s*most|limit)\s*(\d{1,4})\s*words?\b', re.I)

class DetectedQuestion:
    def __init__(
        self,
        element_id: int | None,
        question_text: str,
        field_type: str,
        tag: str,
        required: bool = False,
        options: list[str] | None = None,
        char_limit: int | None = None,
        word_limit: int | None = None,
        instructions: str = '',
        filled: bool = False,
        current_value: str = '',
        group: str = '',
        raw_element: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None
    ):
        self.element_id = element_id
        self.question_text = question_text.strip()
        self.field_type = field_type
        self.tag = tag
        self.required = required
        self.options = options or []
        self.char_limit = char_limit
        self.word_limit = word_limit
        self.instructions = instructions.strip()
        self.filled = filled
        self.current_value = current_value
        self.group = group
        self.raw_element = raw_element or {}
        self.context = context or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            'element_id': self.element_id,
            'question_text': self.question_text,
            'field_type': self.field_type,
            'tag': self.tag,
            'required': self.required,
            'options': self.options,
            'char_limit': self.char_limit,
            'word_limit': self.word_limit,
            'instructions': self.instructions,
            'filled': self.filled,
            'current_value': self.current_value,
            'group': self.group,
            'context': self.context
        }

def extract_limits(text: str) -> tuple[int | None, int | None]:
    """Extract character and word limits from instructions or labels."""
    char_limit = None
    word_limit = None
    if not text:
        return char_limit, word_limit
    
    cm = CHAR_LIMIT_PATTERN.search(text)
    if cm:
        try:
            char_limit = int(cm.group(1))
        except ValueError:
            pass

    wm = WORD_LIMIT_PATTERN.search(text)
    if wm:
        try:
            word_limit = int(wm.group(1))
        except ValueError:
            pass

    return char_limit, word_limit

def detect_questions(snapshot: dict[str, Any], context: dict[str, Any] = None) -> list[DetectedQuestion]:
    """Inspect snapshot elements and extract distinct application questions.
    
    Ignores non-question controls like navigation buttons, links, document upload triggers,
    and handles radio button groups as a single question entity.
    """
    elements = snapshot.get('elements', [])
    page_text = snapshot.get('text', '')
    questions: list[DetectedQuestion] = []
    
    # Track radio groups so multiple radio buttons for the same question are grouped
    radio_groups: dict[str, list[dict[str, Any]]] = {}

    for el in elements:
        tag = (el.get('tag') or '').upper()
        kind = (el.get('type') or '').lower()
        
        # 1. Skip document uploads, buttons, links, hidden elements
        if kind in ('file', 'submit', 'button', 'reset', 'hidden') or tag in ('BUTTON', 'A'):
            continue
        
        # 2. Skip controls that are not form inputs
        if tag not in ('INPUT', 'SELECT', 'TEXTAREA'):
            continue

        label = (el.get('label') or '').strip()
        text = (el.get('text') or '').strip()
        group_name = (el.get('group') or '').strip()
        full_caption = f"{label} {text}".strip()

        # 3. Filter out non-question elements (search bars, cookie banners, login tokens)
        if NON_QUESTION_PATTERNS.search(full_caption):
            continue

        # 4. Handle radio buttons: group them by their question/fieldset
        if kind == 'radio':
            q_title = group_name or label or 'Application Option'
            radio_groups.setdefault(q_title, []).append(el)
            continue

        # 5. Determine primary question text
        question_text = label or group_name or text or el.get('name') or ''
        # Clean asterisk or required markers
        is_required = bool(el.get('required')) or bool(re.search(r'[*]|required', question_text, re.I))
        clean_q = re.sub(r'[*]', '', question_text).strip()
        
        if not clean_q or len(clean_q) < 2:
            continue

        # Extract character or word limits
        char_lim, word_lim = extract_limits(page_text + ' ' + full_caption)
        max_attr = el.get('maxlength')
        if max_attr and str(max_attr).isdigit():
            char_lim = min(char_lim or 999999, int(max_attr))

        # Dropdowns/selects: extract options
        options = el.get('options') or []
        if isinstance(options, list):
            options = [str(o).strip() for o in options if str(o).strip() and not re.match(r'^(?:select|choose|please select|-+)', str(o).strip(), re.I)]

        field_type = 'select' if tag == 'SELECT' else ('textarea' if tag == 'TEXTAREA' else kind or 'text')

        dq = DetectedQuestion(
            element_id=el.get('id'),
            question_text=clean_q,
            field_type=field_type,
            tag=tag,
            required=is_required,
            options=options,
            char_limit=char_lim,
            word_limit=word_lim,
            instructions=text if text != label else '',
            filled=bool(el.get('filled')),
            current_value=str(el.get('value') or ''),
            group=group_name,
            raw_element=el,
            context=context or {}
        )
        questions.append(dq)

    # 6. Process aggregated radio button groups
    for group_title, radio_els in radio_groups.items():
        opts = []
        is_filled = False
        selected_val = ''
        is_req = False
        first_id = radio_els[0].get('id')
        
        for r in radio_els:
            opt_caption = (r.get('label') or r.get('text') or '').strip()
            if opt_caption:
                opts.append(opt_caption)
            if r.get('checked'):
                is_filled = True
                selected_val = opt_caption
            if r.get('required'):
                is_req = True

        clean_group = re.sub(r'[*]', '', group_title).strip()
        if not clean_group:
            clean_group = 'Please select an option'

        dq = DetectedQuestion(
            element_id=first_id,
            question_text=clean_group,
            field_type='radio',
            tag='INPUT',
            required=is_req or '*' in group_title,
            options=opts,
            char_limit=None,
            word_limit=None,
            instructions='',
            filled=is_filled,
            current_value=selected_val,
            group=group_title,
            raw_element=radio_els[0],
            context=context or {}
        )
        questions.append(dq)

    return questions
