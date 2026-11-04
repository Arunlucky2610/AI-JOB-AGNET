"""Job-Specific Application Material Generation Engine.
Synthesizes tailored resumes, cover letters, and recruiter outreach messages strictly from verified evidence.
Computes text differences and provides multi-format export (PDF, DOCX, TXT).
"""
import difflib
import io
import json
import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from docx import Document as DocxDocument
from .db import Session, ApplicationMaterial, AuditEvent, now
from .ai_engine import matcher, OpenRouterProvider, DeterministicFallbackProvider

logger = logging.getLogger(__name__)

def compute_diff(original: str, tailored: str) -> str:
    """Compute line-by-line unified diff between original resume and tailored version."""
    orig_lines = original.splitlines(keepends=True)
    tailored_lines = tailored.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines,
        tailored_lines,
        fromfile='original_resume.txt',
        tofile='tailored_resume.txt',
        n=2
    )
    return ''.join(diff)

def export_docx(title: str, text: str) -> bytes:
    """Generate Word DOCX document."""
    doc = DocxDocument()
    doc.add_heading(title, level=0)
    for paragraph in text.split('\n\n'):
        if paragraph.strip():
            doc.add_paragraph(paragraph.strip())
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()

def export_pdf_reportlab(title: str, text: str) -> bytes:
    """Generate clean PDF using ReportLab (fallback when headless browser engine is unavailable)."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT

        out = io.BytesIO()
        pdf = SimpleDocTemplate(out, pagesize=letter, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontSize=16,
            leading=20,
            alignment=TA_CENTER,
            spaceAfter=14
        )
        body_style = ParagraphStyle(
            'DocBody',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            alignment=TA_LEFT,
            spaceAfter=8
        )

        elements = [Paragraph(f"<b>{title}</b>", title_style), Spacer(1, 10)]
        for p in text.split('\n\n'):
            clean_p = p.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            if clean_p:
                elements.append(Paragraph(clean_p.replace('\n', '<br/>'), body_style))
                elements.append(Spacer(1, 4))

        pdf.build(elements)
        return out.getvalue()
    except Exception as e:
        logger.error(f"ReportLab PDF generation error: {e}")
        # As emergency fallback, return text bytes
        return text.encode('utf-8')

class MaterialGenerationEngine:
    async def generate_all_materials(
        self,
        user_id: str,
        profile: Dict[str, Any],
        job: Dict[str, Any],
        application_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Synthesize tailored resume, cover letter, recruiter message, and diffs."""
        provider = matcher.provider

        system_prompt = (
            "You are RapidSkill Professional Application Material Tailor. "
            "Synthesize job-specific application documents using strictly verified facts from the candidate profile and resume text. "
            "CRITICAL RULES: "
            "1. NEVER invent qualifications, degrees, companies, projects, or metrics not grounded in profile evidence. "
            "2. Tailor by highlighting genuine relevant experience and prioritizing required skills. "
            "3. Return valid JSON containing: "
            "{"
            '"tailored_resume": "<plain text tailored resume with headings: SUMMARY, SKILLS, EXPERIENCE, PROJECTS, EDUCATION>",'
            '"cover_letter": "<3-paragraph compelling professional cover letter under 250 words>",'
            '"recruiter_message": "<concise 100-120 word professional outreach message for LinkedIn/email>",'
            '"key_alignments": ["<bullet 1>", "<bullet 2>", "<bullet 3>"]'
            "}"
        )

        payload = {
            'profile': {
                'name': profile.get('name'),
                'email': profile.get('email'),
                'phone': profile.get('phone'),
                'skills': profile.get('skills'),
                'experience': profile.get('experience'),
                'work_history': profile.get('work_history'),
                'education': profile.get('education'),
                'projects': profile.get('projects'),
                'certifications': profile.get('certifications'),
                'resume_text': profile.get('resume_text', '')
            },
            'job': {
                'title': job.get('title'),
                'company': job.get('company'),
                'description': job.get('description'),
                'skills': job.get('skills')
            }
        }

        try:
            raw = await provider.generate_json(system_prompt, payload)
        except Exception as e:
            logger.warning(f"Material generation fallback due to: {e}")
            name = profile.get('name', 'Candidate')
            raw = {
                'tailored_resume': f"{name}\n{profile.get('email', '')}\n\nTARGET ROLE: {job.get('title')}\n\nSUMMARY\n{profile.get('summary', 'Dedicated professional with proven skills.')}\n\nSKILLS\n{profile.get('skills')}\n\nEXPERIENCE\n{profile.get('resume_text', '')}",
                'cover_letter': f"Dear Hiring Team at {job.get('company')},\n\nI am writing to express my strong interest in the {job.get('title')} role. With my background in {profile.get('skills', 'software development')}, I am confident in my ability to contribute effectively to your team.\n\nThank you for considering my application.\n\nSincerely,\n{name}",
                'recruiter_message': f"Hi {job.get('company')} team, I came across the {job.get('title')} opening and wanted to reach out. Given my background in {profile.get('skills', '')[:60]}, I'd love to connect and discuss how I can add value to your initiatives.",
                'key_alignments': ['Verified core technical skills', 'Relevant project background']
            }

        original_resume = profile.get('resume_text', '')
        tailored_resume = raw.get('tailored_resume', '')
        diff_text = compute_diff(original_resume, tailored_resume)

        materials_result = {
            'tailored_resume': tailored_resume,
            'cover_letter': raw.get('cover_letter', ''),
            'recruiter_message': raw.get('recruiter_message', ''),
            'key_alignments': raw.get('key_alignments', []),
            'diff': diff_text
        }

        # Persist into database ApplicationMaterial if application_id provided
        if user_id and application_id:
            with Session() as db:
                for mat_type, content in [
                    ('tailored_resume', materials_result['tailored_resume']),
                    ('cover_letter', materials_result['cover_letter']),
                    ('recruiter_message', materials_result['recruiter_message'])
                ]:
                    db.add(ApplicationMaterial(
                        id=f"{application_id}_{mat_type}_{now().timestamp()}",
                        user_id=user_id,
                        application_id=application_id,
                        job_id=job.get('id', ''),
                        material_type=mat_type,
                        content=content,
                        diff_summary=diff_text if mat_type == 'tailored_resume' else '',
                        user_approved=False
                    ))
                db.commit()

        return materials_result

document_engine = MaterialGenerationEngine()
