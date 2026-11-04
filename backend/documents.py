"""Consistent single-column application documents for preview downloads/uploads."""
import io, re
from docx import Document
from docx.shared import Inches, Pt, RGBColor

def document_bytes(text, kind='resume'):
    doc=Document()
    section=doc.sections[0]
    section.top_margin=section.bottom_margin=Inches(.65)
    section.left_margin=section.right_margin=Inches(.75)
    normal=doc.styles['Normal']
    normal.font.name='Calibri'; normal.font.size=Pt(10.5)
    normal.paragraph_format.space_after=Pt(5)
    normal.paragraph_format.line_spacing=1.08
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    for i,raw in enumerate(lines):
        line=re.sub(r'^#{1,6}\s*', '', raw).replace('**','')
        heading=kind=='resume' and len(line)<85 and (line.isupper() or raw.startswith('#'))
        bullet=bool(re.match(r'^[-•*]\s+',line))
        if i==0 and kind=='resume':
            p=doc.add_paragraph();p.paragraph_format.space_after=Pt(7)
            r=p.add_run(line);r.bold=True;r.font.size=Pt(21);r.font.color.rgb=RGBColor.from_string('183142')
        elif heading:
            p=doc.add_paragraph();p.paragraph_format.space_before=Pt(11);p.paragraph_format.keep_with_next=True
            r=p.add_run(line);r.bold=True;r.font.size=Pt(11);r.font.color.rgb=RGBColor.from_string('183142')
        elif bullet:
            doc.add_paragraph(re.sub(r'^[-•*]\s+','',line),style='List Bullet')
        else:
            doc.add_paragraph(line)
    buf=io.BytesIO();doc.save(buf);return buf.getvalue()
