"""Plain-text understanding for the brief: what is the topic, which committee, which date, ...

Rule based on purpose: fast, free, deterministic and easy to test. A language-model extractor can replace
these functions later without changing the agent's contract.
"""
from __future__ import annotations

import re
from datetime import date

from ..schemas import BriefFile

MONTHS_EN = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
MONTHS_DE = ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "dezember"]

# Committees the agent knows. Canonical English name; patterns cover German and English wording.
COMMITTEES = {
    "fakom": ("FAKOM", r"fakom"),
    "tsc": ("Technical Steering Committee", r"technical steering|technische[nr]? lenkungsausschuss"),
    "ic": ("Investment Committee", r"investment committee|investitionsausschuss"),
}

_STOP = r"(?:[.,;]|$)"


def _next_date(day: int, month: int, today: date) -> str | None:
    """dd.mm.yyyy for the next occurrence of day/month (this year, or next year if already past)."""
    for year in (today.year, today.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d >= today:
            return d.strftime("%d.%m.%Y")
    return None


def parse_date(text: str, today: date) -> str | None:
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", text)
    if m:
        return f"{int(m[1]):02d}.{int(m[2]):02d}.{m[3]}"
    m = re.search(r"\b(\d{1,2})\.?\s+(" + "|".join(MONTHS_DE) + r")\b", text, re.I)
    if m:
        return _next_date(int(m[1]), MONTHS_DE.index(m[2].lower()) + 1, today)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + "|".join(MONTHS_EN) + r")\b", text, re.I)
    if m:
        return _next_date(int(m[1]), MONTHS_EN.index(m[2].lower()) + 1, today)
    m = re.search(r"\b(" + "|".join(MONTHS_EN) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b", text, re.I)
    if m:
        return _next_date(int(m[2]), MONTHS_EN.index(m[1].lower()) + 1, today)
    return None


def infer_topic(text: str) -> str | None:
    m = re.search(r"\bon (?:our |the |my )?([^.,;]{12,90}?)" + _STOP, text, re.I) or re.search(
        r"\b(?:zu|zur|zum|über)\s+(?:unserer |unserem |der |dem |die |das )?([^.,;]{12,90}?)(?:\s+(?:vorbereiten|besprechen|präsentieren)|" + _STOP + ")",
        text,
        re.I,
    )
    if m:
        return _cap(m[1].strip())
    first = re.split(r"[.!?]", text)[0].strip()
    return _cap(first[:80]) if len(first) >= 12 else None


def detect_committee(text: str, preset_id: str | None) -> str | None:
    for _id, (name, pattern) in COMMITTEES.items():
        if re.search(pattern, text, re.I):
            return name
    if preset_id and preset_id in COMMITTEES:
        return COMMITTEES[preset_id][0]
    return None


# ---- hints about what the text already says -------------------------------------------------

_DECISION = [
    ("postpone", r"postpone|verschieb"),
    ("info", r"for information|zur information|informieren|zur kenntnis|inform the committee"),
    ("budget", r"release (?:the )?budget|budget (?:release|freigeben)|budgetfreigabe|budget freigeb"),
    ("approve", r"approv|approval|decid|decision|genehmig|beschluss|entscheid|freigabe"),
]


def infer_decision(text: str) -> str | None:
    """Which kind of ask the user already named ('approve', 'budget', ...), or None."""
    for option_id, pattern in _DECISION:
        if re.search(pattern, text, re.I):
            return option_id
    return None


def states_favourite(text: str) -> bool:
    return bool(
        re.search(
            r"\bi (?:think|favou?r|prefer|recommend|believe)\b|my recommendation|we should\b"
            r"|\bich (?:halte|bevorzuge|empfehle|favorisiere|würde)\b|meine empfehlung|wir sollten",
            text,
            re.I,
        )
    )


def mentions_precedent(text: str) -> bool:
    return bool(
        re.search(
            r"last time|last year|previous (?:report|meeting|decision)|earlier (?:report|meeting|decision)"
            r"|letztes mal|beim letzten mal|letztes jahr|vorherig|früher(?:e|en|er)? (?:bericht|sitzung|beschluss)",
            text,
            re.I,
        )
    )


def find_precedent_file(files: list[BriefFile]) -> str | None:
    """A previous report among the uploads: 'report/bericht/minutes' plus a year, quarter or committee name."""
    for f in files:
        n = f.name
        if re.search(r"report|bericht|protokoll|minutes", n, re.I) and re.search(r"20\d\d|q[1-4]|fakom|committee|gremium", n, re.I):
            return n
    return None


def word_count(text: str) -> int:
    return len([w for w in text.split() if w])


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]
