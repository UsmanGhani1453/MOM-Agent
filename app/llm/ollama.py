import logging

from ollama import Client

from app.config import Settings

log = logging.getLogger("mom")


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        # Host is passed explicitly so a stray OLLAMA_HOST env var can't break us.
        self.client = Client(host=settings.ollama_host, timeout=settings.ollama_timeout)

    def check(self) -> None:
        """Raise OllamaError with an actionable message if Ollama/model is unavailable."""
        try:
            models = [m.model for m in self.client.list().models]
        except Exception as e:
            raise OllamaError(
                f"Cannot reach Ollama at {self.settings.ollama_host}. "
                "Start it (Start menu app or `ollama serve`)."
            ) from e
        wanted = self.settings.ollama_model
        if not any(m == wanted or m == wanted + ":latest" or m.split(":")[0] == wanted
                   for m in models):
            raise OllamaError(
                f"Model '{wanted}' is not installed. Run: ollama pull {wanted}"
            )

    def generate(self, prompt: str, schema: dict | None = None) -> str:
        try:
            response = self.client.chat(
                model=self.settings.ollama_model,
                messages=[{"role": "user", "content": prompt}],
                format="json" if schema else None,
                options={"num_ctx": self.settings.ollama_num_ctx, "temperature": 0},
            )
        except OllamaError:
            raise
        except Exception as e:
            # The SDK raises httpx.ConnectError, httpx.TimeoutException, etc.
            # Wrap everything into OllamaError so callers get a consistent, friendly message.
            raise OllamaError(
                f"Ollama request failed ({type(e).__name__}): {e}"
            ) from e
        return response.message.content
