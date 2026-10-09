import json
import logging

from pydantic import ValidationError

from app.llm.ollama import OllamaClient
from app.schemas import MeetingMinutes

log = logging.getLogger("mom")

# Rough budget: ~4 chars per token. Leave room for prompt + JSON output.
CHARS_PER_TOKEN = 4

PROMPT = """You are a professional municipal clerk and meeting-minutes agent. Analyze the meeting transcript below and return ONLY valid JSON matching the schema.

Rules:
1. Only use information explicitly present in the transcript. 
2. Never invent participants, dates, decisions, or responsibilities.
3. CRITICAL: In the "summary" field, write a comprehensive, formal, and chronological record of the meeting. Use standard municipal markdown headers (e.g., "### 1. Call to Order", "### 2. Approval of the Agenda", "### 3. New Business") to capture the narrative flow. Do NOT write a brief summary; write the full chronological minutes here.
4. Extract specific action items, decisions, and participants into their respective arrays for quick reference.
5. If a meeting date is not stated in the transcript, use: "{meeting_date}".

EXPECTED JSON SCHEMA:
{{
  "meeting_title": "string",
  "date": "string",
  "participants": ["string"],
  "summary": "string",
  "discussion_points": ["string"],
  "decisions": ["string"],
  "action_items": [
    {{
      "task": "string",
      "responsible_person": "string",
      "status": "string"
    }}
  ],
  "important_topics": ["string"],
  "next_steps": ["string"]
}}

{part_note}
MEETING TRANSCRIPT:
{transcript}
"""

def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split on sentence-ish boundaries so each chunk is <= max_chars."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    chunks, current = [], ""
    for sentence in text.replace("? ", "?\n").replace(". ", ".\n").replace("! ", "!\n").split("\n"):
        if not sentence.strip():  # skip blank lines produced by double spaces / trailing punctuation
            continue
        while len(sentence) > max_chars:  # pathological: no punctuation at all
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if len(current) + len(sentence) + 1 > max_chars and current:
            chunks.append(current.strip())
            current = ""
        current += sentence + " "
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for item in items:
        key = " ".join(item.lower().split())
        if key and key not in seen:
            seen.add(key)
            value = item.strip()
            # Normalise ALL-CAPS items to Title Case so "ALICE JOHNSON" from one
            # chunk and "Alice Johnson" from another don't both appear in output.
            if value == value.upper() and any(c.isalpha() for c in value):
                value = value.title()
            out.append(value)
    return out


class MeetingAgent:
    def __init__(self, llm: OllamaClient, max_retries: int = 2):
        self.llm = llm
        self.max_retries = max_retries

    @property
    def max_chunk_chars(self) -> int:
        ctx = self.llm.settings.ollama_num_ctx
        # Reserve ~1500 tokens for the system prompt + JSON schema overhead,
        # then use 60% of the remaining budget as chars (4 chars/token) to leave
        # headroom for the model's JSON output within the same context window.
        return max(2000, int((ctx - 1500) * CHARS_PER_TOKEN * 0.4))

    def analyze(self, transcript: str, meeting_date: str = "") -> MeetingMinutes:
        if not transcript.strip():
            raise ValueError("The transcript is empty - no speech was detected in the recording.")
        chunks = chunk_text(transcript, self.max_chunk_chars)
        log.info("Analyzing transcript in %d chunk(s)", len(chunks))
        parts = [self._extract(c, meeting_date, i + 1, len(chunks)) for i, c in enumerate(chunks)]
        return parts[0] if len(parts) == 1 else self._merge(parts)

    # ------------------------------------------------------------------
    def _extract(self, chunk: str, meeting_date: str, idx: int, total: int) -> MeetingMinutes:
        note = ""
        if total > 1:
            note = f"\nThis is part {idx} of {total} of a longer meeting. Extract only what is in this part.\n"
        prompt = PROMPT.format(meeting_date=meeting_date, part_note=note, transcript=chunk)
        schema = MeetingMinutes.model_json_schema()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            raw = self.llm.generate(prompt, schema=schema)
            try:
                return self._parse(raw)
            except (ValueError, ValidationError) as e:
                last_error = e
                log.warning("Bad model output (attempt %d): %s", attempt + 1, e)
        raise ValueError(f"The model did not return valid minutes after retries: {last_error}")

    @staticmethod
    def _parse(raw: str) -> MeetingMinutes:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        if not raw.startswith("{"):  # tolerate chatter around the JSON
            start, end = raw.find("{"), raw.rfind("}")
            if start == -1 or end == -1:
                raise ValueError("no JSON object found")
            raw = raw[start:end + 1]
        import json_repair
        data = json_repair.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Parsed JSON is not a dictionary")
        for item in data.get("action_items", []) or []:
            if isinstance(item, dict):
                for k in ("responsible_person", "status"):
                    if not item.get(k):
                        item[k] = "Not specified"
        return MeetingMinutes.model_validate(data)

    def _merge(self, parts: list[MeetingMinutes]) -> MeetingMinutes:
        merged = MeetingMinutes()
        merged.meeting_title = next((p.meeting_title for p in parts if p.meeting_title), "")
        merged.date = next((p.date for p in parts if p.date), "")
        merged.participants = _dedupe([x for p in parts for x in p.participants])
        merged.discussion_points = _dedupe([x for p in parts for x in p.discussion_points])
        merged.decisions = _dedupe([x for p in parts for x in p.decisions])
        merged.important_topics = _dedupe([x for p in parts for x in p.important_topics])
        merged.next_steps = _dedupe([x for p in parts for x in p.next_steps])
        seen = set()
        for p in parts:
            for a in p.action_items:
                key = (" ".join(a.task.lower().split()), a.responsible_person.lower())
                if a.task and key not in seen:
                    seen.add(key)
                    merged.action_items.append(a)
        summaries = [p.summary for p in parts if p.summary]
        merged.summary = self._consolidate_summary(summaries)
        return merged

    def _consolidate_summary(self, summaries: list[str]) -> str:
        joined = "\n\n---\n\n".join(summaries)
        prompt = (
            "You are a professional municipal clerk. Below are chronological segments "
            "of meeting minutes extracted from different parts of a long recording.\n\n"
            "Merge these segments into a single, cohesive, and formal chronological document. "
            "Preserve standard municipal headers (e.g., '1. Call to Order', 'New Business') "
            "and ensure the narrative flows logically from start to finish. Do NOT shorten "
            "or omit any agenda items or discussions. Reply with the formatted markdown text only.\n\n"
            f"{joined}"
        )
        try:
            return self.llm.generate(prompt).strip()
        except Exception:
            log.exception("Summary consolidation failed; falling back to concatenation")
            return "\n\n".join(summaries)