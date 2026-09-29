import json

from app.llm.ollama import OllamaClient


class MeetingAgent:

    def __init__(self):
        self.llm = OllamaClient()

    def analyze(self, transcript: str) -> dict:

        prompt = f"""
You are a professional meeting-minutes extraction agent.

Analyze the meeting transcript below and return ONLY valid JSON.

Do not use Markdown.
Do not add explanations before or after the JSON.

Use exactly this structure:

{{
    "meeting_title": "",
    "date": "",
    "participants": [],
    "summary": "",
    "discussion_points": [],
    "decisions": [],
    "action_items": [
        {{
            "task": "",
            "responsible_person": "",
            "status": ""
        }}
    ],
    "important_topics": [],
    "next_steps": []
}}

Rules:

1. Only use information explicitly present in the transcript.
2. Never invent participants, dates, decisions, or responsibilities.
3. If information is unavailable, use an empty string or empty list.
4. Keep the summary concise but informative.
5. Extract concrete action items when they are mentioned.
6. Use "Not specified" for an action item's responsible person if the task exists but no person is identified.
7. Use "Not specified" for an action item's status if no status is given.

MEETING TRANSCRIPT:

{transcript}
"""

        response = self.llm.generate(prompt)

        return self._parse_json(response)

    def _parse_json(self, response: str) -> dict:

        response = response.strip()

        if response.startswith("```"):
            lines = response.splitlines()

            if lines and lines[0].startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            response = "\n".join(lines).strip()

        try:
            return json.loads(response)

        except json.JSONDecodeError as error:
            raise ValueError(
                f"Ollama returned invalid JSON:\n{response}"
            ) from error