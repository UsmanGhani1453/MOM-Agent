"""Manual end-to-end check: RUN with `pytest -m integration` (needs Ollama, Whisper, uploads/meeting.mp3)."""
from pathlib import Path

import pytest

AUDIO = Path("uploads/meeting.mp3")


@pytest.mark.integration
@pytest.mark.skipif(not AUDIO.exists(), reason="uploads/meeting.mp3 missing")
def test_full_pipeline():
    from app.agent.meeting_agent import MeetingAgent
    from app.transcription.whisper import Transcriber

    from app.config import Settings
    from app.llm.ollama import OllamaClient

    settings = Settings.load()
    transcript = Transcriber(
        settings.whisper_model,
        settings.whisper_device,
        settings.whisper_compute_type,
        settings.whisper_language,
    ).transcribe(str(AUDIO))
    assert transcript
    assert MeetingAgent(OllamaClient(settings)).analyze(transcript).summary
