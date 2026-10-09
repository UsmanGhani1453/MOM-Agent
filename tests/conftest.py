import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent.meeting_agent import MeetingAgent
from app.config import Settings
from app.main import create_app

GOOD = {
    "meeting_title": "AI project sync",
    "date": "2026-09-29",
    "participants": ["Usman", "Ali", "Sarah"],
    "summary": "The team agreed on the stack.",
    "discussion_points": ["Local transcription"],
    "decisions": ["Use faster-whisper"],
    "action_items": [{"task": "Build the agent", "responsible_person": "Usman", "status": ""}],
    "important_topics": [],
    "next_steps": ["Test next week"],
}


class FakeLLM:
    """Stands in for OllamaClient. `outputs` is consumed one reply per call."""

    def __init__(self, settings, outputs=None):
        self.settings = settings
        self.outputs = list(outputs or [json.dumps(GOOD)])
        self.calls = 0

    def check(self):
        pass

    def generate(self, prompt, schema=None):
        self.calls += 1
        if schema is None:  # summary-consolidation call
            return "A combined summary."
        return self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]


class FakeTranscriber:
    def __init__(self, text="Usman will build the agent."):
        self.text, self.calls = text, 0

    def transcribe(self, path):
        self.calls += 1
        return self.text


@pytest.fixture
def settings(tmp_path):
    upload_dir = tmp_path / "up"
    output_dir = tmp_path / "out"
    db_path = tmp_path / "db" / "m.db"
    for d in (upload_dir, output_dir, db_path.parent):
        d.mkdir(parents=True)
    import dataclasses
    return dataclasses.replace(
        Settings(),
        upload_dir=upload_dir,
        output_dir=output_dir,
        db_path=db_path,
    )


@pytest.fixture
def make_client(settings):
    def _make(outputs=None, transcriber=None, settings_override=None):
        s = settings_override or settings
        llm = FakeLLM(s, outputs)
        tr = transcriber or FakeTranscriber()
        app = create_app(s, transcriber=tr, agent=MeetingAgent(llm, max_retries=2))
        return TestClient(app), llm, tr
    return _make


def wait_done(client, meeting_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        s = client.get(f"/meetings/{meeting_id}/status").json()
        if s["status"] in ("done", "failed"):
            return s
        time.sleep(0.05)
    raise TimeoutError
