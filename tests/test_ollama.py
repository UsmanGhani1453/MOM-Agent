"""Manual integration test: requires a running Ollama instance.

Run with: pytest -m integration
"""
import pytest


@pytest.mark.integration
def test_ollama_generate():
    """Send a simple prompt to the live Ollama instance."""
    from app.config import Settings
    from app.llm.ollama import OllamaClient

    settings = Settings.load()
    llm = OllamaClient(settings)

    response = llm.generate(
        "Explain what a meeting minutes document is in two sentences."
    )

    print("\n--- OLLAMA RESPONSE ---\n")
    print(response)

    assert response, "Expected a non-empty response from Ollama"
