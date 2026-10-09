from app.llm.ollama import OllamaClient


llm = OllamaClient()

response = llm.generate(
    "Explain what a meeting minutes document is in two sentences."
)

print("\n--- OLLAMA RESPONSE ---\n")
print(response)
