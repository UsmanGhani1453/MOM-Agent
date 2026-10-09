import io
import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

MINUTES = {"meeting_title": "Weekly Sync", "date": "", "participants": ["Ali"], "summary": "S",
           "discussion_points": [], "decisions": ["Go"], "action_items": [], "important_topics": [],
           "next_steps": []}


class FakeTranscriber:
    def __init__(self, text="hello world"):
        self.text = text

    def transcribe(self, path):
        return self.text


class FakeAgent:
    def analyze(self, transcript, meeting_date=""):
        return {**MINUTES, "date": meeting_date}


@pytest.fixture
def client(tmp_path):
    settings = Settings(upload_dir=tmp_path / "up", output_dir=tmp_path / "out",
                        db_path=tmp_path / "db.sqlite", max_upload_mb=1)
    app = create_app(settings, FakeTranscriber(), FakeAgent(), run_inline=True)
    with TestClient(app) as c:
        c.settings = settings
        yield c


def upload(client, name="m.mp3", data=b"x", date="2026-09-29"):
    return client.post("/upload", files={"file": (name, io.BytesIO(data))}, data={"meeting_date": date})


def test_full_flow_and_docx(client):
    r = upload(client)
    assert r.status_code == 200 and "Weekly Sync" in r.text          # redirect followed
    meeting_id = r.url.path.rsplit("/", 1)[-1]
    assert client.get(f"/meetings/{meeting_id}/status").json()["status"] == "done"
    doc = client.get(f"/meetings/{meeting_id}/download")
    assert doc.status_code == 200 and doc.content[:2] == b"PK"        # valid zip/docx
    assert not list(client.settings.upload_dir.iterdir())             # audio cleaned up
    assert "m.mp3" in client.get("/").text
    assert client.post(f"/meetings/{meeting_id}/delete").status_code == 200
    assert client.get(f"/meetings/{meeting_id}").status_code == 404


def test_bad_extension_is_400(client):
    assert upload(client, "notes.txt").status_code == 400


def test_bad_date_is_400(client):
    assert upload(client, date="29/09/2026").status_code == 400


def test_too_large_is_413(client):
    assert upload(client, data=b"x" * (2 * 1024 * 1024)).status_code == 413
    assert not list(client.settings.upload_dir.iterdir())


def test_silent_audio_reports_error(tmp_path):
    settings = Settings(upload_dir=tmp_path / "up", output_dir=tmp_path / "out", db_path=tmp_path / "d.db")
    app = create_app(settings, FakeTranscriber(""), FakeAgent(), run_inline=True)
    with TestClient(app) as c:
        r = upload(c)
        assert "No speech was detected" in r.text
