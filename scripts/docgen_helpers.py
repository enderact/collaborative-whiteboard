"""Formatting helpers for the generated Word document.

Kept separate from the content so the document generator reads as prose rather
than as a wall of python-docx boilerplate.
"""

from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

BODY_FONT = "Times New Roman"
CODE_FONT = "Consolas"


def configure_styles(doc) -> None:
    """Times New Roman 12 pt throughout, as the submission guidelines require."""
    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(12)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15
    # python-docx only sets the latin font; the east-asian slot has to be set too
    # or Word substitutes a different face for some glyphs.
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)

    for name, size, bold in [
        ("Heading 1", 16, True),
        ("Heading 2", 14, True),
        ("Heading 3", 12, True),
    ]:
        style = doc.styles[name]
        style.font.name = BODY_FONT
        style.font.size = Pt(size)
        style.font.bold = bold
        style.font.color.rgb = RGBColor(0x1F, 0x2A, 0x44)
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.keep_with_next = True


def shade(cell_or_para, hex_fill: str) -> None:
    element = OxmlElement("w:shd")
    element.set(qn("w:val"), "clear")
    element.set(qn("w:fill"), hex_fill)
    target = cell_or_para._tc.get_or_add_tcPr() if hasattr(cell_or_para, "_tc") \
        else cell_or_para._p.get_or_add_pPr()
    target.append(element)


def h1(doc, text):
    return doc.add_heading(text, level=1)


def h2(doc, text):
    return doc.add_heading(text, level=2)


def h3(doc, text):
    return doc.add_heading(text, level=3)


def para(doc, text, italic=False, bold=False, align=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.italic = italic
    run.bold = bold
    if align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return p


def bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(3)
        if isinstance(item, tuple):
            head, rest = item
            r = p.add_run(head)
            r.bold = True
            p.add_run(rest)
        else:
            p.add_run(item)


def numbered(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Number")
        p.paragraph_format.space_after = Pt(3)
        p.add_run(item)


def code(doc, text, size=8.5):
    """A shaded monospace block. Long listings stay readable at 8.5 pt."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.left_indent = Inches(0.12)
    shade(p, "F2F4F8")
    run = p.add_run(text.rstrip("\n"))
    run.font.name = CODE_FONT
    run.font.size = Pt(size)
    run.element.rPr.rFonts.set(qn("w:eastAsia"), CODE_FONT)
    return p


def caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.italic = True
    run.font.size = Pt(10)
    p.paragraph_format.space_after = Pt(12)
    return p


def table(doc, headers, rows, widths=None, font_size=9.5):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER

    for i, head in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(str(head))
        run.bold = True
        run.font.size = Pt(font_size)
        run.font.name = BODY_FONT
        shade(cell, "DCE3F0")

    for row in rows:
        cells = t.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(str(value))
            run.font.size = Pt(font_size)
            mono = str(value).startswith(("db.", "$", "{", "ix_", "/api", "GET", "POST",
                                          "PATCH", "DELETE", "await", "room:"))
            run.font.name = CODE_FONT if mono else BODY_FONT

    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Inches(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def picture(doc, path, width_inches=6.1, cap=None):
    doc.add_picture(str(path), width=Inches(width_inches))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    if cap:
        caption(doc, cap)


def excerpt(path, start_marker=None, end_marker=None, max_lines=None, dedent=False):
    """Pull a real slice out of a source file so listings cannot drift from the code."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if start_marker:
        for i, line in enumerate(lines):
            if start_marker in line:
                lines = lines[i:]
                break
    if end_marker:
        for i, line in enumerate(lines):
            if end_marker in line and i > 0:
                lines = lines[:i]
                break
    if max_lines:
        lines = lines[:max_lines]
    if dedent:
        pad = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
        lines = [l[pad:] if l.strip() else l for l in lines]
    return "\n".join(lines).rstrip()
