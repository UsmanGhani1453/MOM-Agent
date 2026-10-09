"""Manual integration test: requires Ollama, Whisper, and uploads/meeting.mp3.

Run with: pytest -m integration
"""
from pathlib import Path

import pytest

AUDIO = Path("uploads/meeting.mp3")


@pytest.mark.integration
@pytest.mark.skipif(not AUDIO.exists(), reason="uploads/meeting.mp3 missing")
def test_full_pipeline():
    """Transcribe a real audio file and analyze it with the live LLM."""
    from app.agent.meeting_agent import MeetingAgent
    from app.config import Settings
    from app.llm.ollama import OllamaClient
    from app.transcription.whisper import Transcriber

    settings = Settings.load()

    print("Loading Whisper...")
    transcriber = Transcriber(
        settings.whisper_model,
        settings.whisper_device,
        settings.whisper_compute_type,
        settings.whisper_language,
    )

    print("Transcribing meeting...")
    transcript = transcriber.transcribe(str(AUDIO))

    print("\n--- TRANSCRIPT ---\n")
    print(transcript)

    print("\nAnalyzing meeting with Ollama...\n")
    llm = OllamaClient(settings)
    agent = MeetingAgent(llm)
    result = agent.analyze(transcript)

    print("\n--- MEETING MINUTES ---\n")
    for key, value in result.model_dump().items():
        print(f"{key}:")
        print(value)
        print()

    assert transcript, "Expected non-empty transcript"
    assert result.summary, "Expected a non-empty summary"