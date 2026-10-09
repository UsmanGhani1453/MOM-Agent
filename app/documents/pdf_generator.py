from pathlib import Path
from fpdf import FPDF

from app.schemas import MeetingMinutes


def _add_bullets(pdf: FPDF, items: list[str]) -> None:
    if not items:
        pdf.set_font("helvetica", "I", 11)
        pdf.multi_cell(0, 7, "None recorded.")
        pdf.set_font("helvetica", "", 11)
        pdf.ln(2)
        return

    for item in items:
        pdf.set_font("helvetica", "", 11)
        # using a simple dash instead of a complex bullet character for compatibility
        pdf.multi_cell(0, 7, f"- {item}")
    pdf.ln(2)


def generate_pdf(minutes: MeetingMinutes, out_path: Path, fallback_title: str = "Meeting") -> Path:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Title
    pdf.set_font("helvetica", "B", 16)
    title = minutes.meeting_title or fallback_title
    pdf.multi_cell(0, 10, title)

    # Subtitle
    pdf.set_font("helvetica", "I", 11)
    pdf.set_text_color(89, 89, 89)
    sub = "Minutes of Meeting" + (f"  |  {minutes.date}" if minutes.date else "")
    pdf.multi_cell(0, 8, sub)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)

    # Participants
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "Participants", new_x="LMARGIN", new_y="NEXT")
    _add_bullets(pdf, minutes.participants)

    # Summary
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 11)
    pdf.multi_cell(0, 7, minutes.summary or "No summary available.")
    pdf.ln(5)

    # Discussion Points
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "Discussion Points", new_x="LMARGIN", new_y="NEXT")
    _add_bullets(pdf, minutes.discussion_points)

    # Decisions
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "Decisions", new_x="LMARGIN", new_y="NEXT")
    _add_bullets(pdf, minutes.decisions)

    # Action Items
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "Action Items", new_x="LMARGIN", new_y="NEXT")
    if minutes.action_items:
        # Table headers
        pdf.set_font("helvetica", "B", 11)
        
        # Calculate widths (total 190mm on A4)
        col1, col2, col3 = 90, 50, 50
        
        pdf.cell(col1, 10, "Task", border=1)
        pdf.cell(col2, 10, "Responsible", border=1)
        pdf.cell(col3, 10, "Status", border=1, new_x="LMARGIN", new_y="NEXT")

        # Table rows
        pdf.set_font("helvetica", "", 11)
        for a in minutes.action_items:
            # For simplicity, using standard cells. For multiline, we'd need multi_cell or a table extension,
            # but standard cell with truncation or large fixed height is usually sufficient for simple items.
            task = a.task[:45] + "..." if len(a.task) > 48 else a.task
            resp = a.responsible_person[:20] + "..." if len(a.responsible_person) > 23 else a.responsible_person
            stat = a.status[:20] + "..." if len(a.status) > 23 else a.status
            
            pdf.cell(col1, 10, task, border=1)
            pdf.cell(col2, 10, resp, border=1)
            pdf.cell(col3, 10, stat, border=1, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
    else:
        pdf.set_font("helvetica", "I", 11)
        pdf.multi_cell(0, 7, "None recorded.")
        pdf.ln(5)

    # Important Topics
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "Important Topics", new_x="LMARGIN", new_y="NEXT")
    _add_bullets(pdf, minutes.important_topics)

    # Next Steps
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "Next Steps", new_x="LMARGIN", new_y="NEXT")
    _add_bullets(pdf, minutes.next_steps)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    return out_path
