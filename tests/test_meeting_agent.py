"""Manual integration test: requires a running Ollama instance with the configured model.

Run with: pytest -m integration
"""
import pytest

TRANSCRIPT = """
The project team met on September 29, 2026.

Participants were Usman, Ali, and Sarah.

The team discussed the progress of the meeting minutes AI project.
They agreed to use faster-whisper for local transcription and Ollama
with Gemma 2 for meeting analysis.

Usman will implement the meeting analysis agent.
Ali will test the transcription system.
Sarah will prepare the user interface.

The team will test the complete system next week.
"""


@pytest.mark.integration
def test_meeting_agent_live():
    """End-to-end agent test against a live Ollama instance."""
    from app.agent.meeting_agent import MeetingAgent
    from app.config import Settings
    from app.llm.ollama import OllamaClient

    settings = Settings.load()
    llm = OllamaClient(settings)
    agent = MeetingAgent(llm)

    result = agent.analyze(TRANSCRIPT)

    print("\n--- MEETING ANALYSIS ---\n")
    for key, value in result.model_dump().items():
        print(f"{key}:")
        print(value)
        print()

    assert result.summary, "Expected a non-empty summary"
    assert result.participants, "Expected participants to be extracted"