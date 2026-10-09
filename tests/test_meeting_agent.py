from app.agent.meeting_agent import MeetingAgent


transcript = """
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


agent = MeetingAgent()

result = agent.analyze(transcript)

print("\n--- MEETING ANALYSIS ---\n")

for key, value in result.items():
    print(f"{key}:")
    print(value)
    print()