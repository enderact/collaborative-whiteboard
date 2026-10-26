"""Small helpers over python-pptx for building the review deck.

The deck is 16:9 and dark, so text colour and placement are set explicitly
rather than relying on a template theme that is not shipped with the project.
"""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

W, H = Inches(13.333), Inches(7.5)

INK = RGBColor(0x0E, 0x14, 0x22)        # slide background
CARD = RGBColor(0x18, 0x22, 0x36)       # panel fill
EDGE = RGBColor(0x2A, 0x3A, 0x55)       # panel border
TEXT = RGBColor(0xEC, 0xF1, 0xF8)
MUTED = RGBColor(0x93, 0xA4, 0xBD)
ACCENT = RGBColor(0x4F, 0x9B, 0xF5)     # MongoDB-ish blue for headings
GOOD = RGBColor(0x3D, 0xD5, 0x98)       # measured wins
WARN = RGBColor(0xF5, 0xA5, 0x24)

FONT = "Calibri"
MONO = "Consolas"


def new_deck() -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    return prs


def _blank(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _fill(shape, colour: RGBColor | None, line: RGBColor | None = None,
          line_w: float = 1.0) -> None:
    if colour is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = colour
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(line_w)


def textbox(slide, left, top, width, height, *, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tf


def write(tf, text: str, *, size: float = 16, bold: bool = False, colour: RGBColor = TEXT,
          align=PP_ALIGN.LEFT, font: str = FONT, space_after: float = 4,
          first: bool = False, level: int = 0, line: float | None = None):
    """Append a paragraph. `first` reuses the empty paragraph a text frame starts with."""
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.level = level
    p.space_after = Pt(space_after)
    if line:
        p.line_spacing = line
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = colour
    run.font.name = font
    return p


def slide(prs: Presentation, title: str, kicker: str | None = None):
    """A slide with the standard dark background, title and accent rule."""
    s = _blank(prs)
    bg = s.shapes.add_shape(1, 0, 0, W, H)
    _fill(bg, INK)

    top = 0.42
    if kicker:
        tf = textbox(s, 0.62, top, 12.1, 0.3)
        write(tf, kicker.upper(), size=11.5, bold=True, colour=ACCENT, first=True)
        top += 0.34

    tf = textbox(s, 0.62, top, 12.1, 0.62)
    write(tf, title, size=29, bold=True, first=True)

    rule = s.shapes.add_shape(1, Inches(0.62), Inches(top + 0.72), Inches(1.5), Pt(3))
    _fill(rule, ACCENT)
    return s


def card(slide, left, top, width, height, *, fill=CARD, edge=EDGE):
    shape = slide.shapes.add_shape(5, Inches(left), Inches(top), Inches(width), Inches(height))
    shape.adjustments[0] = 0.04
    _fill(shape, fill, edge)
    shape.shadow.inherit = False
    return shape


def stat_card(slide, left, top, width, value: str, label: str, *, colour=GOOD,
              height: float = 1.18) -> None:
    """A big measured number with its caption. Used for the evidence slides."""
    card(slide, left, top, width, height)
    tf = textbox(slide, left + 0.2, top + 0.14, width - 0.4, 0.55)
    write(tf, value, size=27, bold=True, colour=colour, first=True)
    tf2 = textbox(slide, left + 0.2, top + 0.68, width - 0.4, height - 0.78)
    write(tf2, label, size=11.5, colour=MUTED, first=True, line=1.05)


def bullet_list(slide, left, top, width, items: list[tuple[str, str]], *,
                size: float = 15, gap: float = 0.1) -> float:
    """Items are (lead, rest); the lead is bolded so a claim reads before its detail."""
    y = top
    for lead, rest in items:
        tf = textbox(slide, left, y, width, 0.3)
        p = tf.paragraphs[0]
        p.line_spacing = 1.04
        for text, bold, colour in ((f"{lead} ", True, TEXT), (rest, False, MUTED)):
            if not text.strip():
                continue
            run = p.add_run()
            run.text = text
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = colour
            run.font.name = FONT
        lines = max(1, int(len(f"{lead} {rest}") / (width * 7.4)) + 1)
        y += 0.26 * lines + gap
    return y


def code_card(slide, left, top, width, height, text: str, *, size: float = 10.5,
              title: str | None = None) -> None:
    card(slide, left, top, width, height, fill=RGBColor(0x10, 0x18, 0x28))
    y = top + 0.13
    if title:
        tf = textbox(slide, left + 0.2, y, width - 0.4, 0.26)
        write(tf, title, size=11.5, bold=True, colour=ACCENT, first=True)
        y += 0.32
    tf = textbox(slide, left + 0.2, y, width - 0.4, height - (y - top) - 0.15)
    for i, row in enumerate(text.strip().split("\n")):
        write(tf, row, size=size, colour=TEXT, font=MONO, first=(i == 0), space_after=0,
              line=1.02)


def table(slide, left, top, width, headers: list[str], rows: list[list[str]], *,
          col_widths: list[float] | None = None, size: float = 11.5,
          row_h: float = 0.3, highlight: RGBColor | None = None) -> None:
    shape = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(left), Inches(top),
                                   Inches(width), Inches(row_h * (len(rows) + 1)))
    t = shape.table
    if col_widths:
        for i, w in enumerate(col_widths):
            t.columns[i].width = Inches(w)

    for i, head in enumerate(headers):
        cell = t.cell(0, i)
        cell.text = ""
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(0x22, 0x31, 0x4A)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = cell.margin_right = Inches(0.07)
        write(cell.text_frame, head, size=size, bold=True, colour=ACCENT, first=True)

    for r, row in enumerate(rows, start=1):
        for c, value in enumerate(row):
            cell = t.cell(r, c)
            cell.text = ""
            cell.fill.solid()
            cell.fill.fore_color.rgb = CARD if r % 2 else RGBColor(0x14, 0x1E, 0x30)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Inches(0.07)
            colour = highlight if (highlight and c == len(row) - 1) else TEXT
            write(cell.text_frame, str(value), size=size, colour=colour, first=True,
                  bold=bool(highlight and c == len(row) - 1))


def picture(slide, path: Path, left, top, width, *, caption: str | None = None) -> None:
    if not path.exists():
        tf = textbox(slide, left, top, width, 0.3)
        write(tf, f"[missing {path.name}]", size=12, colour=WARN, first=True)
        return
    pic = slide.shapes.add_picture(str(path), Inches(left), Inches(top), width=Inches(width))
    pic.line.color.rgb = EDGE
    pic.line.width = Pt(1)
    if caption:
        tf = textbox(slide, left, top + Emu(pic.height).inches + 0.07, width, 0.3)
        write(tf, caption, size=10.5, colour=MUTED, first=True, line=1.05)


def footer(slide, text: str) -> None:
    tf = textbox(slide, 0.62, 6.95, 12.1, 0.3)
    write(tf, text, size=10.5, colour=MUTED, first=True)
