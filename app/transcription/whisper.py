from faster_whisper import WhisperModel

class Transcriber:

    def __init__(self):

        print("Loading Whisper model...")

        self.model = WhisperModel(
            "base",
            device="cpu",
            compute_type="int8"
        )

        print("Whisper model loaded.")

    def transcribe(self, audio_path: str) -> str:

        print(f"Transcribing: {audio_path}")

        segments, info = self.model.transcribe(
            audio_path,
            beam_size=5
        )

        transcript = []

        for segment in segments:
            text = segment.text.strip()

            if text:
                transcript.append(text)

        return " ".join(transcript)
