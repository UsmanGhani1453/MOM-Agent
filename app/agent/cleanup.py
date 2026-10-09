"""Post-processing that keeps model chatter and formatting noise out of official minutes."""
import re

# Lines that open with assistant-style commentary.
_INTRO = re.compile(
    r"^\s*(?:\*\*)?\s*(?:sure|certainly|okay|ok|absolutely|of course|here(?:'s| is| are)|"
    r"this is (?:a|an|the)\b[^\n]{0,60}\b(?:summary|overview|breakdown|analysis|record)|"
    r"below is|i(?:'ve| have) (?:summari[sz]ed|prepared|written)|great|excellent)\b",
    re.I)

# Everything from one of these markers to the end is commentary, not minutes.
_TAIL = re.compile(
    r"^\s*(?:[#>*\-\s]*)(?:\*\*)?\s*(?:possible questions|questions to consider|"
    r"key takeaways|overall\b|in summary\b|note:|let me know|i hope this|"
    r"this summary (?:provides|highlights|captures)|please let me know|"
    r"disclaimer)",
    re.I)

_BOLD = re.compile(r"\*\*(.+?)\*\*")


def strip_chatter(text: str) -> str:
    """Drop assistant commentary before/after the real minutes."""
    if not text:
        return ""
    lines = text.replace("\r\n", "\n").split("\n")
    # leading chatter (only the opening lines, so real content is never touched)
    while lines and (not lines[0].strip() or _INTRO.match(lines[0])):
        lines.pop(0)
    # trailing commentary
    for i, line in enumerate(lines):
        if _TAIL.match(line):
            lines = lines[:i]
            break
    return "\n".join(lines).strip()


def has_chatter(text: str) -> bool:
    if not text:
        return False
    lines = [ln for ln in text.replace("\r\n", "\n").split("\n")]
    first = next((ln for ln in lines if ln.strip()), "")
    return bool(_INTRO.match(first)) or any(_TAIL.match(ln) for ln in lines)


def fix_glued_markdown(text: str) -> str:
    """'adjourn.**Possible' -> put markers/headers on their own line."""
    text = re.sub(r"([.!?])(\*\*[A-Z])", r"\1\n\n\2", text)
    text = re.sub(r"([^\n#])(#{2,4}\s)", r"\1\n\n\2", text)
    return text


def clean_text(text: str) -> str:
    text = fix_glued_markdown(text or "")
    text = strip_chatter(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_PLACEHOLDERS = {"none", "n/a", "na", "not specified", "none recorded", "nil", "-"}


def clean_item(text: str) -> str:
    """Single bullet/decision: no markdown, no stray asterisks, placeholders become ''."""
    text = _BOLD.sub(r"\1", text or "")
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"^\s*[-*\u2022]\s+", "", text)
    text = " ".join(text.split()).strip()
    return "" if text.lower().rstrip(".") in _PLACEHOLDERS else text


def clean_items(items: list[str]) -> list[str]:
    seen, out = set(), []
    for it in items or []:
        v = clean_item(strip_chatter(it))
        key = v.lower().rstrip(".")
        if v and key not in seen:
            seen.add(key)
            out.append(v)
    return out
