"""Official-minutes PDF layout (fpdf2, built-in fonts only so it works everywhere)."""
import re
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import Align, TableCellFillMode, XPos, YPos
from fpdf.fonts import FontFace

from app.agent.cleanup import clean_text
from app.schemas import MeetingMinutes

INK = (30, 30, 30)
ACCENT = (31, 56, 100)      # dark navy for headings and rules
MUTED = (100, 100, 100)
BAND = (240, 243, 248)      # light table header / zebra fill

_REPLACEMENTS = {
    "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
    "\u2014": " - ", "\u2013": "-", "\u2026": "...", "\u2022": "-",
    "\u00a0": " ", "\u2212": "-", "\u2192": "->",
}


def _sanitize(text: str) -> str:
    """Built-in PDF fonts only cover Latin-1; map the common extras, never crash."""
    if not text:
        return ""
    for k, v in _REPLACEMENTS.items():
        text = text.replace(k, v)
    text = re.sub(r"[-=_*]{10,}", "---", text)
    # fpdf2 cannot wrap a single unbroken run wider than the page.
    text = re.sub(r"(\S{60})(?=\S)", r"\1 ", text)
    return text.encode("latin-1", "replace").decode("latin-1")


def _plain(text: str) -> str:
    """Strip markdown emphasis so no raw asterisks ever reach the page."""
    return _sanitize(text.replace("**", "").replace("__", "").replace("`", ""))


class MinutesPDF(FPDF):
    def __init__(self, footer_label: str):
        super().__init__(format="A4")
        self.footer_label = footer_label
        self.set_margins(22, 20, 22)
        self.set_auto_page_break(auto=True, margin=22)
        self.set_title(footer_label)
        self.alias_nb_pages()

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_font("helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(self.epw / 2, 8, self.footer_label, align="L")
        self.cell(self.epw / 2, 8, f"Page {self.page_no()} of {{nb}}", align="R")
        self.set_text_color(*INK)


# ------------------------------------------------------------------ building blocks
def _heading(pdf: FPDF, text: str) -> None:
    pdf.ln(4)
    if pdf.get_y() > pdf.h - 45:  # never strand a heading at the bottom of a page
        pdf.add_page()
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 7, _sanitize(text.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.set_text_color(*INK)
    pdf.ln(3)


def _para(pdf: FPDF, text: str, style: str = "", size: float = 10.5, indent: float = 0,
          after: float = 2) -> None:
    pdf.set_font("times", style, size + 0.5)
    pdf.set_x(pdf.l_margin + indent)
    pdf.multi_cell(pdf.epw - indent, 5.6, _plain(text), align=Align.J if not indent else Align.L,
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(after)


def _numbered(pdf: FPDF, items: list[str]) -> None:
    pdf.set_font("times", "", 11)
    for i, item in enumerate(items, 1):
        pdf.set_x(pdf.l_margin)
        pdf.cell(9, 5.6, f"{i}.")
        pdf.multi_cell(pdf.epw - 9, 5.6, _plain(item), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1.5)


def _bullets(pdf: FPDF, items: list[str]) -> None:
    pdf.set_font("times", "", 11)
    for item in items:
        pdf.set_x(pdf.l_margin + 3)
        pdf.cell(5, 5.6, "-")
        pdf.multi_cell(pdf.epw - 8, 5.6, _plain(item), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)


def _render_markdown(pdf: FPDF, text: str) -> None:
    """Render the model's minutes text: '### n. Heading', bullets, paragraphs."""
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            m = re.match(r"^#{1,6}\s*(.+)$", line)
            b = re.match(r"^[-*\u2022]\s+(.+)$", line)
            if m:
                pdf.ln(2)
                if pdf.get_y() > pdf.h - 40:
                    pdf.add_page()
                pdf.set_font("helvetica", "B", 10.5)
                pdf.set_text_color(*ACCENT)
                pdf.multi_cell(0, 6, _plain(m.group(1)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_text_color(*INK)
                pdf.ln(0.5)
                i += 1
            elif b:
                _bullets(pdf, [b.group(1)])
                i += 1
            else:
                para = [line]
                i += 1
                while i < len(lines) and not re.match(r"^(#{1,6}\s|[-*\u2022]\s)", lines[i].strip()):
                    para.append(lines[i].strip())
                    i += 1
                _para(pdf, " ".join(para), size=10.5, after=2.5)


def _table(pdf: FPDF, headers: list[str], rows: list[list[str]], widths: tuple) -> None:
    pdf.set_font("helvetica", "", 9.5)
    pdf.set_draw_color(190, 190, 190)
    with pdf.table(
        col_widths=widths,
        text_align=Align.L,
        line_height=5.4,
        padding=2,
        cell_fill_color=BAND,
        cell_fill_mode=TableCellFillMode.NONE,
        headings_style=FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=ACCENT),
        borders_layout="HORIZONTAL_LINES",
    ) as table:
        head = table.row()
        for h in headers:
            head.cell(_sanitize(h))
        for r in rows:
            row = table.row()
            for c in r:
                row.cell(_plain(c) or "-")
    pdf.ln(2)


def _details(pdf: FPDF, pairs: list[tuple[str, str]]) -> None:
    label_w = 32
    for label, value in pairs:
        if not value:
            continue
        pdf.set_font("helvetica", "B", 9.5)
        pdf.set_text_color(*MUTED)
        pdf.cell(label_w, 5.6, _sanitize(label))
        pdf.set_font("times", "", 11)
        pdf.set_text_color(*INK)
        pdf.multi_cell(pdf.epw - label_w, 5.6, _plain(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(0.8)


def _signature_block(pdf: FPDF, signatories: tuple) -> None:
    height = 18 + 20
    if pdf.get_y() + height > pdf.h - 25:
        pdf.add_page()
    pdf.ln(12)
    col_w = pdf.epw / max(1, len(signatories)) - 6
    y = pdf.get_y() + 14
    pdf.set_draw_color(*INK)
    for i, title in enumerate(signatories):
        x = pdf.l_margin + i * (col_w + 12)
        pdf.line(x, y, x + col_w, y)
        pdf.set_xy(x, y + 1)
        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(col_w, 5, _sanitize(title))
    pdf.set_xy(pdf.l_margin, y + 10)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, "Approved on: ______________________")
    pdf.set_text_color(*INK)


# ------------------------------------------------------------------ public API
def generate_pdf(minutes: MeetingMinutes, out_path: Path, fallback_title: str = "Meeting",
                 org_name: str = "", signatories: tuple = ()) -> Path:
    title = _plain(minutes.meeting_title or Path(fallback_title).stem or "Meeting")
    footer_label = _sanitize(f"{title}  |  {minutes.date}" if minutes.date else title)
    pdf = MinutesPDF(footer_label)
    pdf.add_page()

    # Letterhead
    if org_name:
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 6, _sanitize(org_name.upper()), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("times", "B", 21)
    pdf.set_text_color(*ACCENT)
    pdf.multi_cell(0, 9.5, title, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 7, "Minutes of Meeting", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, pdf.get_y() + 2, pdf.w - pdf.r_margin, pdf.get_y() + 2)
    pdf.set_line_width(0.2)
    pdf.set_text_color(*INK)
    pdf.ln(8)

    # Meeting details
    when = minutes.start_time + (f" - {minutes.end_time}" if minutes.start_time and minutes.end_time else "")
    if not minutes.start_time and minutes.end_time:
        when = f"Adjourned at {minutes.end_time}"
    _details(pdf, [
        ("Date", minutes.date),
        ("Time", when),
        ("Location", minutes.location),
    ])

    # Attendance
    if minutes.participants or minutes.absent:
        _heading(pdf, "Participants")
        if minutes.participants:
            _details(pdf, [("Present", "; ".join(minutes.participants))])
        if minutes.absent:
            _details(pdf, [("Absent", "; ".join(minutes.absent))])

    # Minutes narrative
    _heading(pdf, "Minutes")
    summary = clean_text(minutes.summary)
    if summary:
        _render_markdown(pdf, summary)
    else:
        _para(pdf, "No narrative record was produced for this meeting.", style="I")

    # Motions
    if minutes.motions:
        _heading(pdf, "Motions")
        _table(pdf, ["Motion", "Moved", "Seconded", "Result"],
               [[m.text, m.moved_by, m.seconded_by, m.result] for m in minutes.motions],
               widths=(80, 30, 30, 28))

    # Decisions
    if minutes.decisions:
        _heading(pdf, "Decisions")
        _numbered(pdf, minutes.decisions)

    # Action items
    _heading(pdf, "Action Items")
    if minutes.action_items:
        _table(pdf, ["Task", "Responsible", "Status"],
               [[a.task, a.responsible_person, a.status] for a in minutes.action_items],
               widths=(88, 45, 35))
    else:
        _para(pdf, "No action items were assigned at this meeting.", style="I")

    if minutes.next_steps:
        _heading(pdf, "Next Steps")
        _bullets(pdf, minutes.next_steps)

    if signatories:
        _signature_block(pdf, signatories)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    return out_path
