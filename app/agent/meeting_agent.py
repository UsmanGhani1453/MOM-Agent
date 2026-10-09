import json
import logging

from pydantic import ValidationError

from app.agent.cleanup import clean_item, clean_items, clean_text, has_chatter
from app.llm.ollama import OllamaClient
from app.roster import Roster, clean_participants
from app.schemas import MeetingMinutes

log = logging.getLogger("mom")

# Rough budget: ~4 chars per token. Leave room for prompt + JSON output.
CHARS_PER_TOKEN = 4

PROMPT = """You are a professional meeting secretary. Turn the recording transcript below into clear, formal MEETING MINUTES. The transcript can come from ANY kind of meeting or recording (team call, board or council meeting, interview, class, webinar, phone call). First work out from the content what kind of meeting it is, then write minutes that suit it.

Output ONLY one valid JSON object that matches the schema. No text before or after it. No commentary.

STYLE RULES
1. Formal, neutral, third person, past tense. Example: "The team agreed to move the launch to March."
2. NEVER comment on the meeting or on your own output. Do not write phrases such as "This is a great summary", "Key Takeaways", "Possible Questions", "Overall", or "Let me know".
3. Use only facts stated in the transcript. Never invent names, amounts, motions, dates, times or tasks. If something is not stated, leave the field as "" or [] (never write "None", "N/A" or "Not specified" inside lists).
4. Keep numbers, amounts, dates and names exactly as spoken.
5. Write in the same language as the transcript. Plain text only: no asterisks, no bold, no emoji.
6. The transcript was produced by speech-to-text, so a name may be misspelled or inconsistent. Use one consistent spelling per person.

FIELD RULES
- "meeting_title": a short, specific title based on the content (e.g. "Q3 Marketing Planning Meeting", "Regular Council Meeting", "Candidate Interview"). Do not use a generic title like "Meeting" if the topic is clear.
- "date": the date stated in the transcript, otherwise "{meeting_date}". "location", "start_time", "end_time": only if stated, otherwise "".
- "participants": people who took part, ONE entry per person, with their role only if it is stated (e.g. "Sarah Khan, Project Manager"). Only list people who are named or clearly identified in the transcript. Never list a bare role such as "Chair" or "Speaker". Never list the same person twice. If nobody is named, return []. "absent": people stated to be absent.
{roster_hint}- "summary": the full chronological minutes as plain paragraphs under numbered headings that start with "### ", for example "### 1. Opening", "### 2. Budget Review", "### 3. Closing". Choose headings that match what was actually discussed; include a formal opening/closing only if one occurred. Cover every topic, in order. If a person made a statement, proposal or commitment, say who (when named).
- "discussion_points": short factual sentences, one per topic discussed.
- "motions": ONLY for formal motions or votes (who moved, who seconded, result "Carried", "Carried unanimously" or "Defeated"). Otherwise [].
- "decisions": one clear sentence per decision actually made, each different from the others, with exact figures where stated. Do not write vague lines; say what was decided.
- "action_items": ONLY tasks explicitly assigned or volunteered for. "task", "responsible_person" (as named, or "Not specified"), "status" (include a due date if one was stated, otherwise "Open"). If nothing was assigned, return [].
- "important_topics": 2 to 6 short topic labels. "next_steps": only follow-up steps explicitly stated, otherwise [].

EXPECTED JSON SCHEMA:
{{
  "meeting_title": "string",
  "date": "string",
  "location": "string",
  "start_time": "string",
  "end_time": "string",
  "participants": ["string"],
  "absent": ["string"],
  "summary": "string",
  "discussion_points": ["string"],
  "motions": [{{"text": "string", "moved_by": "string", "seconded_by": "string", "result": "string"}}],
  "decisions": ["string"],
  "action_items": [{{"task": "string", "responsible_person": "string", "status": "string"}}],
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
    def __init__(self, llm: OllamaClient, max_retries: int = 2, roster: Roster | None = None):
        self.llm = llm
        self.max_retries = max_retries
        self.roster = roster or Roster()

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
        result = parts[0] if len(parts) == 1 else self._merge(parts)
        return self._finalize(result, meeting_date)

    def _finalize(self, m: MeetingMinutes, meeting_date: str = "") -> MeetingMinutes:
        """Last line of defence: no chatter, no duplicate people, no placeholder rows."""
        m.meeting_title = clean_item(m.meeting_title)
        m.date = m.date.strip() or meeting_date
        m.location = " ".join(m.location.split())
        m.start_time = " ".join(m.start_time.split())
        m.end_time = " ".join(m.end_time.split())
        m.summary = clean_text(m.summary)
        m.participants = clean_participants(m.participants, self.roster)
        absent = clean_participants(m.absent, self.roster)
        m.absent = [a for a in absent if a not in m.participants]
        m.discussion_points = clean_items(m.discussion_points)
        m.decisions = clean_items(m.decisions)
        m.important_topics = clean_items(m.important_topics)
        m.next_steps = clean_items(m.next_steps)
        if not m.summary:
            m.summary = self._fallback_summary(m)

        motions, seen = [], set()
        for mo in m.motions:
            mo.text = clean_item(mo.text)
            if not mo.text:
                continue
            for f in ("moved_by", "seconded_by"):
                person = self.roster.match(getattr(mo, f)) if getattr(mo, f) else None
                setattr(mo, f, person.display() if person else " ".join(getattr(mo, f).split()))
            mo.result = " ".join(mo.result.split())
            key = " ".join(mo.text.lower().split())
            if key not in seen:
                seen.add(key)
                motions.append(mo)
        m.motions = motions

        items, seen = [], set()
        for a in m.action_items:
            a.task = clean_item(a.task)
            if not a.task:
                continue
            key = " ".join(a.task.lower().split())
            if key not in seen:
                seen.add(key)
                items.append(a)
        m.action_items = items
        return m

    # ------------------------------------------------------------------
    def _extract(self, chunk: str, meeting_date: str, idx: int, total: int) -> MeetingMinutes:
        note = ""
        if total > 1:
            note = f"\nThis is part {idx} of {total} of a longer meeting. Extract only what is in this part.\n"
        prompt = PROMPT.format(meeting_date=meeting_date, part_note=note, transcript=chunk,
                               roster_hint=self.roster.hint_for_prompt())
        schema = MeetingMinutes.model_json_schema()
        last_error: Exception | None = None
        fallback: MeetingMinutes | None = None
        for attempt in range(self.max_retries + 1):
            raw = self.llm.generate(prompt, schema=schema)
            try:
                parsed = self._parse(raw)
            except (ValueError, ValidationError) as e:
                last_error = e
                log.warning("Bad model output (attempt %d): %s", attempt + 1, e)
                continue
            if has_chatter(parsed.summary):
                # Valid JSON, but the model chatted inside the minutes. Ask again;
                # keep this one so _finalize can strip it if every retry does the same.
                fallback = fallback or parsed
                last_error = ValueError("summary contained assistant commentary")
                log.warning("Chatter in summary (attempt %d); retrying", attempt + 1)
                continue
            return parsed
        if fallback is not None:
            return fallback
        raise ValueError(f"The model did not return valid minutes after retries: {last_error}")

    @staticmethod
    def _fallback_summary(m: MeetingMinutes) -> str:
        """If the model's narrative was unusable, build a factual record from the extracted
        fields rather than printing an empty Minutes section."""
        parts = []
        if m.discussion_points:
            parts.append("### Topics Discussed\n" + "\n".join(f"- {x}" for x in m.discussion_points))
        # Decisions are printed in their own section, so they are not repeated here.
        if m.end_time:
            parts.append(f"### Adjournment\nThe meeting adjourned at {m.end_time}.")
        return "\n\n".join(parts)

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
        merged.location = next((p.location for p in parts if p.location), "")
        merged.start_time = next((p.start_time for p in parts if p.start_time), "")
        merged.end_time = next((p.end_time for p in reversed(parts) if p.end_time), "")
        merged.participants = _dedupe([x for p in parts for x in p.participants])
        merged.absent = _dedupe([x for p in parts for x in p.absent])
        merged.motions = [mo for p in parts for mo in p.motions]
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
            "You are a professional meeting secretary. Below are chronological segments "
            "of meeting minutes extracted from different parts of a long recording.\n\n"
            "Merge these segments into a single, cohesive, formal chronological document. "
            "Keep the numbered headings that start with '### ' (e.g. '### 1. Opening'), "
            "renumber them in order, and merge duplicate headings. Do NOT shorten or omit any "
            "topics, decisions, motions or figures. Plain text only, no asterisks. Reply with the "
            "minutes text ONLY: no introduction, no commentary, no questions, no closing remarks.\n\n"
            f"{joined}"
        )
        try:
            merged = clean_text(self.llm.generate(prompt))
            if not merged:
                raise ValueError("empty consolidation")
            return merged
        except Exception:
            log.exception("Summary consolidation failed; falling back to concatenation")
            return "\n\n".join(clean_text(x) for x in summaries)