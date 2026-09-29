from ollama import Client


class OllamaClient:

    def __init__(self):
        self.client = Client(
            host="http://127.0.0.1:11434"
        )

        self.model = "gemma2:2b"

    def generate(self, prompt: str) -> str:

        response = self.client.chat(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response.message.content