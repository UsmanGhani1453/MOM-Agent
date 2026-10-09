from pathlib import Path

from app.transcription.whisper import Transcriber
from app.agent.meeting_agent import MeetingAgent


audio_file = Path("uploads/meeting.mp3")


print("Loading Whisper...")
transcriber = Transcriber()

print("Transcribing meeting...")
transcript = transcriber.transcribe(str(audio_file))

print("\n--- TRANSCRIPT ---\n")
print(transcript)

print("\nAnalyzing meeting with Ollama...\n")

agent = MeetingAgent()

result = agent.analyze(transcript)

print("\n--- MEETING MINUTES ---\n")

for key, value in result.items():
    print(f"{key}:")
    print(value)
    print()