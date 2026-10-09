"""Run:  python scripts/check_setup.py   - verifies everything the app needs."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings  # noqa: E402
from app.llm.ollama import OllamaClient, OllamaError  # noqa: E402

ok = True


def report(name, good, detail=""):
    global ok
    ok &= good
    print(f"[{'OK' if good else 'FAIL'}] {name} {detail}")


s = Settings.load()
try:
    OllamaClient(s).check()
    report("Ollama", True, f"({s.ollama_host}, model {s.ollama_model})")
except OllamaError as e:
    report("Ollama", False, f"- {e}")

try:
    import faster_whisper  # noqa: F401
    report("faster-whisper", True)
except ImportError:
    report("faster-whisper", False, "- pip install -r requirements.txt")

report("ffmpeg (optional)", True, "found" if shutil.which("ffmpeg") else
       "not found - fine, faster-whisper bundles its own decoder")
sys.exit(0 if ok else 1)
