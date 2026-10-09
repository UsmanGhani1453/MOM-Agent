"""End-to-end test without the web UI:  python scripts/pipeline_test.py path/to/audio.mp3"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.meeting_agent import MeetingAgent  # noqa: E402
from app.config import Settings  # noqa: E402
from app.documents.docx_generator import generate_docx  # noqa: E402
from app.llm.ollama import OllamaClient  # noqa: E402
from app.transcription.whisper import Transcriber  # noqa: E402

if len(sys.argv) < 2:
    sys.exit("usage: python scripts/pipeline_test.py <audio file>")

s = Settings.load()
text = Transcriber(s.whisper_model, s.whisper_device, s.whisper_compute_type).transcribe(sys.argv[1])
print("--- TRANSCRIPT ---\n", text, "\n")
minutes = MeetingAgent(OllamaClient(s)).analyze(text)
print("--- MINUTES ---\n", minutes.model_dump_json(indent=2))
out = generate_docx(minutes, s.output_dir / "pipeline_test.docx")
print("\nSaved:", out)
