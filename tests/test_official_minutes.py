"""Regression tests for the problems seen in the first generated council PDF."""
import json
from pathlib import Path

import fitz  # pymupdf; only used to read the generated PDF back
import pytest

from app.agent.cleanup import clean_text, has_chatter, strip_chatter
from app.agent.meeting_agent import MeetingAgent
from app.documents.pdf_generator import generate_pdf
from app.roster import Person, Roster, clean_participants
from app.schemas import ActionItem, MeetingMinutes
from tests.conftest import GOOD, FakeLLM

ROSTER = Roster([
    Person("Patrick Terrien", "Mayor", ["Terian"]),
    Person("Fuel", "Deputy Mayor"),
    Person("Kaczynski", "Councillor", ["Kazinsky"]),
    Person("Miller", "Councillor"),
    Person("Warren", "Councillor", ["Warn"]),
    Person("Cousineau", "Councillor", ["Cousinski", "Cousincy"]),
    Person("Humphrey Brinoss", "Chief Administrative Officer", ["Humphrey"]),
])

# The participant list exactly as it appeared in the bad PDF.
GARBLED = [
    "Mayor Patrick Terrien", "Deputy Mayor Fuel", "Councillors Kaczynski", "Councillors Miller",
    "Councillors Warren", "Fuel", "Warn", "Kaczynski", "Terian", "Miller", "Cousinski",
    "Humphrey Brinoss", "Councillor Miller", "Mayor", "Humphrey", "Councillor Warren",
    "Councillor Cousincy", "Colleen", "Councilman", "Warren", "Kazinsky",
]


def test_garbled_participants_collapse_with_roster():
    out = clean_participants(GARBLED, ROSTER)
    assert out == [
        "Mayor Patrick Terrien", "Deputy Mayor Fuel", "Councillor Kaczynski",
        "Councillor Miller", "Councillor Warren", "Councillor Cousineau",
        "Humphrey Brinoss, Chief Administrative Officer", "Colleen",
    ]


def test_participants_dedupe_without_roster():
    out = clean_participants(["Councillor Kaczynski", "Kazinsky", "Mayor", "Councilman", "Miller",
                              "Councillor Miller"])
    assert "Mayor" not in out and "Councilman" not in out
    assert len(out) == 2


CHATTY = (
    "This is a great summary of a council meeting! Here's a breakdown:\n\n"
    "### 1. Call to Order\nThe meeting was called to order at 6:00 pm.\n\n"
    "### 2. Adjournment\nThe meeting adjourned at 6:55 pm.**Possible Questions:**\n"
    "* What is the project?\n**Overall:** This summary provides a clear overview."
)


def test_chatter_detected_and_stripped():
    assert has_chatter(CHATTY)
    cleaned = clean_text(CHATTY)
    assert "great summary" not in cleaned and "Possible Questions" not in cleaned
    assert "Overall" not in cleaned and "**" not in cleaned
    assert "### 1. Call to Order" in cleaned and "adjourned at 6:55 pm." in cleaned


def test_real_minutes_are_untouched():
    text = "### 1. Call to Order\nThe Mayor called the meeting to order."
    assert not has_chatter(text) and strip_chatter(text) == text


def test_agent_retries_when_summary_has_chatter(settings):
    bad = dict(GOOD, summary=CHATTY)
    llm = FakeLLM(settings, [json.dumps(bad), json.dumps(GOOD)])
    m = MeetingAgent(llm, max_retries=2).analyze("Some transcript.", "2026-10-06")
    assert m.summary == "The team agreed on the stack." and llm.calls == 2


def test_agent_strips_chatter_if_model_never_stops(settings):
    bad = dict(GOOD, summary=CHATTY)
    llm = FakeLLM(settings, [json.dumps(bad)])
    m = MeetingAgent(llm, max_retries=1).analyze("Some transcript.")
    assert "Possible Questions" not in m.summary and "great summary" not in m.summary


def test_agent_applies_roster_and_drops_placeholders(settings):
    data = dict(GOOD, participants=GARBLED, decisions=["None", "Approved the payrolls."],
                next_steps=["N/A"], action_items=[{"task": "None", "responsible_person": "None",
                                                    "status": ""}])
    llm = FakeLLM(settings, [json.dumps(data)])
    m = MeetingAgent(llm, roster=ROSTER).analyze("Some transcript.")
    assert len(m.participants) == 8
    assert m.decisions == ["Approved the payrolls."]
    assert m.next_steps == [] and m.action_items == []


def _text(pdf_path: Path) -> str:
    with fitz.open(pdf_path) as d:
        return "\n".join(p.get_text() for p in d)


def test_pdf_has_no_placeholders_or_markdown(tmp_path):
    minutes = MeetingMinutes(
        meeting_title="Regular Council Meeting", date="2026-10-06", end_time="6:55 pm",
        participants=["Mayor Patrick Terrien", "Councillor Warren"],
        summary="### 1. Call to Order\nThe **Mayor** called the meeting to order.\n\n"
                "### 2. Adjournment\nAdjourned at 6:55 pm.",
        decisions=["Approved the August and September payrolls."],
    )
    out = generate_pdf(minutes, tmp_path / "m.pdf", org_name="RM of Springfield",
                       signatories=("Mayor", "CAO"))
    text = _text(out)
    assert "RM OF SPRINGFIELD" in text and "Regular Council Meeting" in text
    assert "None" not in text and "**" not in text and "###" not in text
    assert "No action items were assigned" in text
    assert "Mayor" in text and "Approved on" in text
    assert "NEXT STEPS" not in text and "IMPORTANT TOPICS" not in text  # empty sections omitted


def test_pdf_survives_long_text_and_unicode(tmp_path):
    minutes = MeetingMinutes(
        summary="x" * 500 + "\n\nCaf\u00e9 \u201cquoted\u201d \u2014 \u2713 emoji \U0001F600",
        action_items=[ActionItem(task="Do a very long task " * 20, responsible_person="A" * 90)],
    )
    out = generate_pdf(minutes, tmp_path / "m.pdf")
    assert out.exists() and out.stat().st_size > 1000


def test_roster_file_loading(tmp_path):
    f = tmp_path / "r.json"
    f.write_text(json.dumps({"people": [{"name": "Warren", "title": "Councillor"}]}))
    r = Roster.load(f)
    assert r.match("Councillors Warren").display() == "Councillor Warren"
    assert not Roster.load(tmp_path / "missing.json")


def test_all_chatter_summary_falls_back_to_structured_record(settings):
    data = dict(GOOD, summary="This is a great summary!\n**Key Takeaways:**\n* stuff\n**Overall:** nice")
    llm = FakeLLM(settings, [json.dumps(data)])
    m = MeetingAgent(llm, max_retries=1).analyze("Some transcript.")
    assert "great summary" not in m.summary and "Takeaways" not in m.summary
    assert "Local transcription" in m.summary  # rebuilt from discussion points


def test_generic_meeting_without_roster_org_or_signatures(tmp_path):
    minutes = MeetingMinutes(
        meeting_title="Q3 Marketing Planning Meeting", date="2026-10-09",
        participants=["Sarah Khan, Project Manager", "Ali"],
        summary="### 1. Campaign Budget\nSarah proposed a budget of $12,000.",
        decisions=["The team approved a budget of $12,000."],
        action_items=[ActionItem(task="Draft the launch plan", responsible_person="Ali", status="Due Friday")],
    )
    out = generate_pdf(minutes, tmp_path / "g.pdf")  # no org name, no signatories
    text = _text(out)
    assert "Q3 Marketing Planning Meeting" in text and "Draft the launch plan" in text
    assert "Approved on" not in text and "Council" not in text
