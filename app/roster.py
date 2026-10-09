"""Known attendees (mayor, councillors, staff) used to clean up participant names.

Speech-to-text and small LLMs produce many spellings of one person
("Terrien" / "Terian", "Kaczynski" / "Kazinsky"). The roster maps all of them
onto one canonical name and title.

Roster file (JSON, default data/roster.json, override with MOM_ROSTER_FILE):

    {"people": [
        {"name": "Patrick Terrien", "title": "Mayor"},
        {"name": "Fuel", "title": "Deputy Mayor"},
        {"name": "Kaczynski", "title": "Councillor", "aliases": ["Kazinsky"]}
    ]}
"""
import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Words that name a role, not a person. Entries made only of these are dropped.
_ROLE_WORDS = {
    "mayor", "deputy", "councillor", "councilor", "councilman", "councilwoman",
    "council", "reeve", "chair", "chairman", "chairperson", "member", "cao",
    "clerk", "secretary", "staff", "speaker", "unknown", "participant",
    "attendee", "the", "of", "and", "present", "absent",
}
_PREFIX_TITLES = {"mayor", "deputy mayor", "reeve", "deputy reeve", "councillor", "councilor",
                  "councilman", "councilwoman", "chair", "chairman", "chairperson"}
_TITLE_PREFIX = re.compile(
    r"^(deputy\s+mayor|deputy\s+reeve|mayor|reeve|councill?or|councilman|"
    r"councilwoman|coun\.?|cllr\.?|mr\.?|mrs\.?|ms\.?|dr\.?)\s+", re.I)


def _key(text: str) -> str:
    return re.sub(r"[^a-z ]", "", text.lower()).strip()


def strip_title(name: str) -> str:
    name = " ".join(name.split())
    prev = None
    while prev != name:
        prev = name
        name = _TITLE_PREFIX.sub("", name)
    return name.strip(" ,.;:-")


def is_role_only(name: str) -> bool:
    words = _key(name).split()
    return not words or all(w in _ROLE_WORDS for w in words)


@dataclass
class Person:
    name: str
    title: str = ""
    aliases: list[str] = field(default_factory=list)

    def display(self) -> str:
        if not self.title:
            return self.name
        if self.title.lower() in _PREFIX_TITLES:  # "Mayor Patrick Terrien"
            return f"{self.title} {self.name}"
        return f"{self.name}, {self.title}"  # "Humphrey Brinoss, Chief Administrative Officer"

    def keys(self) -> list[str]:
        out = []
        for n in [self.name, *self.aliases]:
            k = _key(n)
            if k:
                out.append(k)
                out.append(k.split()[-1])  # surname alone
        return out


class Roster:
    def __init__(self, people: list[Person] | None = None):
        self.people = people or []

    def __bool__(self) -> bool:
        return bool(self.people)

    @classmethod
    def load(cls, path: Path | None) -> "Roster":
        if not path or not Path(path).exists():
            return cls()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([Person(p["name"], p.get("title", ""), p.get("aliases", []))
                    for p in data.get("people", []) if p.get("name")])

    # ------------------------------------------------------------------
    def match(self, raw: str, cutoff: float = 0.78) -> Person | None:
        stripped = _key(strip_title(raw))
        if not stripped:
            return None
        lookup: dict[str, Person] = {}
        for p in self.people:
            for k in p.keys():
                lookup.setdefault(k, p)
        for candidate in (stripped, stripped.split()[-1]):
            if candidate in lookup:
                return lookup[candidate]
            close = difflib.get_close_matches(candidate, list(lookup), n=1, cutoff=cutoff)
            if close:
                return lookup[close[0]]
        return None

    def hint_for_prompt(self) -> str:
        if not self.people:
            return ""
        lines = "\n".join(f"- {p.display()}" for p in self.people)
        return ("KNOWN ATTENDEE NAMES (the transcript may misspell them; always use these exact "
                "spellings and titles when you recognise a person):\n" + lines + "\n")

    def whisper_prompt(self) -> str:
        """Names fed to Whisper so it spells them correctly in the first place."""
        return ", ".join(p.name for p in self.people)


def clean_participants(raw: list[str], roster: Roster | None = None) -> list[str]:
    """Remove role-only entries, collapse spelling variants, return each person once."""
    roster = roster or Roster()
    out: list[str] = []
    seen: set[str] = set()
    pending_unmatched: list[str] = []

    for item in raw:
        item = " ".join((item or "").split())
        if not item or is_role_only(item):
            continue
        person = roster.match(item)
        if person:
            label = person.display()
            if label.lower() not in seen:
                seen.add(label.lower())
                out.append(label)
        else:
            pending_unmatched.append(item)

    # No roster match: still collapse near-duplicates ("Kazinsky" / "Kaczynski").
    kept: list[str] = []
    for item in pending_unmatched:
        base = _key(strip_title(item))
        dup = False
        for i, other in enumerate(kept):
            ob = _key(strip_title(other))
            sur_a, sur_b = base.split()[-1], ob.split()[-1]
            sur_ratio = difflib.SequenceMatcher(None, sur_a, sur_b).ratio()
            one_is_surname_only = len(base.split()) == 1 or len(ob.split()) == 1
            # Two different people can share a surname ("John Smith"/"Jane Smith"), so a
            # surname-only match is trusted only when one entry has no first name.
            same = (base == ob
                    or (one_is_surname_only and sur_a[:1] == sur_b[:1] and sur_ratio >= 0.70)
                    or difflib.SequenceMatcher(None, base, ob).ratio() >= 0.85)
            if same:
                dup = True
                if len(item) > len(other):  # prefer the fuller form (has title / full name)
                    kept[i] = item
                break
        if not dup:
            kept.append(item)
    for item in kept:
        if item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out
