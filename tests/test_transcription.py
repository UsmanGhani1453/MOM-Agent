from app.transcription.whisper import Transcriber


audio_file = "uploads/meeting.mp3"

transcriber = Transcriber()

print("Transcribing...")

text = transcriber.transcribe(audio_file)

print("\n--- TRANSCRIPT ---\n")
print(text)