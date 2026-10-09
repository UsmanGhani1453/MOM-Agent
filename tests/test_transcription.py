"""Manual integration test: requires faster-whisper and uploads/meeting.mp3.

Run with: pytest -m integration
"""
from pathlib import Path

import pytest

AUDIO = Path("uploads/meeting.mp3")


@pytest.mark.integration
@pytest.mark.skipif(not AUDIO.exists(), reason="uploads/meeting.mp3 missing")
def test_transcription_live():
    """Transcribe a real audio file using the Whisper model."""
    from app.config import Settings
    from app.transcription.whisper import Transcriber

    settings = Settings.load()
    transcriber = Transcriber(
        settings.whisper_model,
        settings.whisper_device,
        settings.whisper_compute_type,
        settings.whisper_language,
    )

    print("Transcribing...")
    text = transcriber.transcribe(str(AUDIO))

    print("\n--- TRANSCRIPT ---\n")
    print(text)

    assert text, "Expected non-empty transcription"