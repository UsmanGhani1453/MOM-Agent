import json

import pytest

from app.agent.meeting_agent import MeetingAgent, chunk_text
from tests.conftest import GOOD, FakeLLM


def test_parse_strips_fences_and_fills_defaults(settings):
    raw = "```json\n" + json.dumps(GOOD) + "\n```"
    m = MeetingAgent._parse(raw)
    assert m.action_items[0].status == "Not specified"
    assert m.participants == ["Usman", "Ali", "Sarah"]


def test_parse_tolerates_chatter():
    m = MeetingAgent._parse("Sure! Here you go: " + json.dumps(GOOD) + " Hope that helps.")
    assert m.meeting_title == "AI project sync"


def test_retries_on_bad_json_then_succeeds(settings):
    llm = FakeLLM(settings, ["not json", "{broken", json.dumps(GOOD)])
    m = MeetingAgent(llm, max_retries=2).analyze("Some transcript.", "2026-10-08")
    assert m.decisions == ["Use faster-whisper"] and llm.calls == 3


def test_gives_up_after_retries(settings):
    llm = FakeLLM(settings, ["nope"])
    with pytest.raises(ValueError, match="valid minutes"):
        MeetingAgent(llm, max_retries=1).analyze("Some transcript.")
    assert llm.calls == 2


def test_empty_transcript_rejected(settings):
    with pytest.raises(ValueError, match="empty"):
        MeetingAgent(FakeLLM(settings)).analyze("   ")


def test_chunking_and_merge(settings):
    import dataclasses
    tiny_settings = dataclasses.replace(settings, ollama_num_ctx=2048)  # force tiny chunks
    long = "Usman will build the agent. " * 600
    agent = MeetingAgent(FakeLLM(tiny_settings, [json.dumps(GOOD)]))
    chunks = chunk_text(long, agent.max_chunk_chars)
    assert len(chunks) > 1 and all(len(c) <= agent.max_chunk_chars for c in chunks)
    m = agent.analyze(long)
    # duplicates across chunks collapse
    assert len(m.action_items) == 1 and m.decisions == ["Use faster-whisper"]
    assert m.summary == "A combined summary."
