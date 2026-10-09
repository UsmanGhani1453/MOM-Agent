import logging
import threading

log = logging.getLogger("mom")


class Transcriber:
    """Loads the Whisper model once, on first use, and reuses it."""

    def __init__(self, model: str = "base", device: str = "cpu",
                 compute_type: str = "int8", language: str | None = None,
                 names_hint: str = ""):
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.names_hint = names_hint  # councillor names, so Whisper spells them consistently
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel  # heavy import, keep lazy

                log.info("Loading Whisper model '%s' on %s...", self.model_name, self.device)
                self._model = WhisperModel(
                    self.model_name, device=self.device, compute_type=self.compute_type
                )
                log.info("Whisper model loaded.")
        return self._model

    def transcribe(self, audio_path: str) -> str:
        model = self._load()
        log.info("Transcribing %s", audio_path)
        kwargs = {}
        if self.names_hint:
            kwargs["initial_prompt"] = f"Meeting participants: {self.names_hint}."
        segments, info = model.transcribe(
            audio_path, beam_size=5, vad_filter=True, language=self.language, **kwargs
        )
        parts = [s.text.strip() for s in segments if s.text.strip()]
        return " ".join(parts)
