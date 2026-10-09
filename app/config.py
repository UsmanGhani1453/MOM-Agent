"""Central settings. Everything can be overridden with MOM_* environment
variables or a .env file in the project root.

NOTE: the standard OLLAMA_HOST variable is deliberately NOT used. A value of
0.0.0.0 (valid for the server) breaks Python clients on Windows.
"""
import dataclasses
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = BASE_DIR / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def normalize_host(host: str) -> str:
    """Turn '0.0.0.0:11434', 'localhost', '::' etc. into a connectable URL."""
    host = (host or "").strip()
    if "://" not in host:
        host = "http://" + host
    u = urlparse(host)
    name = u.hostname
    if name in (None, "", "0.0.0.0", "::", "localhost"):
        name = "127.0.0.1"
    return f"{u.scheme}://{name}:{u.port or 11434}"


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    base_dir: Path = BASE_DIR
    upload_dir: Path = BASE_DIR / "uploads"
    output_dir: Path = BASE_DIR / "outputs"
    db_path: Path = BASE_DIR / "data" / "meetings.db"

    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma2:2b"
    ollama_num_ctx: int = 8192
    ollama_timeout: int = 600

    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str | None = None  # None = auto-detect

    max_upload_mb: int = 500
    delete_audio_after: bool = True
    allowed_extensions: tuple = (".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac")

    @classmethod
    def load(cls) -> "Settings":
        """Read env / .env overrides and return an immutable Settings instance.

        Field defaults are read from the dataclass definition via dataclasses.fields()
        so the env-var fallback values are always in sync with the class defaults.
        """
        _load_dotenv()
        e = os.environ.get
        # Build a lookup of field-name -> default so we never repeat the default values.
        D = {f.name: f.default for f in dataclasses.fields(cls)}

        # Resolve path overrides before mkdir so custom directories are created.
        upload_dir = Path(e("MOM_UPLOAD_DIR", D["upload_dir"]))
        output_dir = Path(e("MOM_OUTPUT_DIR", D["output_dir"]))
        db_path = Path(e("MOM_DB_PATH", D["db_path"]))

        # Ensure directories exist before the immutable instance is created.
        for d in (upload_dir, output_dir, db_path.parent):
            d.mkdir(parents=True, exist_ok=True)

        return cls(
            upload_dir=upload_dir,
            output_dir=output_dir,
            db_path=db_path,
            ollama_host=normalize_host(e("MOM_OLLAMA_HOST", D["ollama_host"])),
            ollama_model=e("MOM_OLLAMA_MODEL", D["ollama_model"]),
            ollama_num_ctx=int(e("MOM_OLLAMA_NUM_CTX", D["ollama_num_ctx"])),
            ollama_timeout=int(e("MOM_OLLAMA_TIMEOUT", D["ollama_timeout"])),
            whisper_model=e("MOM_WHISPER_MODEL", D["whisper_model"]),
            whisper_device=e("MOM_WHISPER_DEVICE", D["whisper_device"]),
            whisper_compute_type=e("MOM_WHISPER_COMPUTE_TYPE", D["whisper_compute_type"]),
            whisper_language=e("MOM_WHISPER_LANGUAGE") or None,
            max_upload_mb=int(e("MOM_MAX_UPLOAD_MB", D["max_upload_mb"])),
            delete_audio_after=_bool(e("MOM_DELETE_AUDIO_AFTER", str(D["delete_audio_after"]))),
        )

