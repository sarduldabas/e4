"""Small text helpers shared by the rules versions of the agents (tokens, sentences, numbers, wording)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

STOP = set("""the and for with that this from are was were has have had not but you your our their they them his her its into over under
about after before than then also can will would should could may might must shall per via any all one two out off use used using
der die das und oder aber nicht ein eine einen einem einer eines mit von für auf ist sind war waren wird werden wurde wurden hat haben hatte
den dem des zum zur bei nach aus wie als auch noch nur sich wir ich sie ihr uns ihre ihrem ihren unsere unserer unserem unseren
""".split())


def tokens(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[^\W_]+", (text or "").lower()):
        if len(w) < 3 or w in STOP or w.isdigit():
            continue
        if len(w) > 5:
            w = re.sub(r"(ungen|ung|ing|ed|es|en|er|e|s)$", "", w)[:6]
            if len(w) == 6 and w.endswith(("o", "i")):
                w = w[:5]
        out.add(w)
    return out


def overlap(a: set[str], b: set[str]) -> float:
    """Share of `a` that also appears in `b` (0..1)."""
    return len(a & b) / len(a) if a else 0.0


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "")).strip()


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [norm(p) for p in parts if len(norm(p)) >= 8]


def slug(text: str) -> str:
    t = text.lower().replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    s = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "section"


def clip(text: str, n: int) -> str:
    t = norm(text)
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


# ------------------------------------------------------------------ numbers
@dataclass
class Num:
    value: float
    unit: str | None
    start: int
    end: int
    raw: str


_DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b|\b\d{1,2}\.\s?(?:jan|feb|mär|mar|apr|mai|may|jun|jul|aug|sep|okt|oct|nov|dez|dec)\w*", re.I)
_NUM = re.compile(
    r"(?P<pre>[€$£]|EUR\b|USD\b)?\s?(?P<num>\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"(?:\s?(?P<mag>mio\.?|mrd\.?|million(?:s|en)?|billion|bn|tsd\.?|k|m)(?![a-zäöü]))?"
    r"(?:\s?(?P<unit>%|€|eur\b|usd\b|\$|months?\b|monat(?:e|en)?\b|weeks?\b|wochen?\b|days?\b|tag(?:e|en)?\b|years?\b|jahr(?:e|en)?\b|pcs\b|pieces\b|stück\b|units\b|gwh\b|mwh\b|kwh\b|kg\b|mm\b))?",
    re.I,
)
_UNIT_NORM = {"month": "months", "monat": "months", "monate": "months", "monaten": "months", "week": "weeks", "woche": "weeks", "wochen": "weeks",
              "day": "days", "tag": "days", "tage": "days", "tagen": "days", "year": "years", "jahr": "years", "jahre": "years", "jahren": "years",
              "pieces": "pcs", "stück": "pcs", "eur": "€", "$": "USD", "usd": "USD"}
_MAG = {"mio": "M", "mio.": "M", "million": "M", "millions": "M", "millionen": "M", "m": "M", "mrd": "bn", "mrd.": "bn", "billion": "bn", "bn": "bn", "k": "k", "tsd": "k", "tsd.": "k"}


def parse_number(raw: str) -> float | None:
    s = raw.strip()
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if re.fullmatch(r"\d+,\d{1,2}", s) else s.replace(",", "")
    elif "." in s and re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def find_numbers(text: str) -> list[Num]:
    """Numbers with their unit. Dates and bare years are skipped."""
    blocked = [m.span() for m in _DATE.finditer(text)]
    out: list[Num] = []
    for m in _NUM.finditer(text):
        if any(a <= m.start("num") < b for a, b in blocked):
            continue
        value = parse_number(m["num"])
        if value is None:
            continue
        mag = _MAG.get((m["mag"] or "").lower())
        cur = (m["pre"] or "").upper().replace("$", "USD").replace("EUR", "€") or None
        unit = (m["unit"] or "").lower()
        unit = _UNIT_NORM.get(unit, unit) or None
        if unit in ("€", "USD") or cur:
            unit = f"{mag or ''}{cur or unit}"
        elif mag and not unit:
            unit = mag
        if unit is None and float(value).is_integer() and 1900 <= value <= 2100:
            continue  # a year
        out.append(Num(value, unit, m.start(), m.end(), m.group(0).strip()))
    return out


def number_in(text: str, value: float, tol: float = 1e-6) -> bool:
    return any(abs(n.value - value) <= tol * max(1.0, abs(value)) for n in find_numbers(text))


# ------------------------------------------------------------------ wording (rules versions only)
def pick(lang: str, de: str, en: str) -> str:
    return de if lang == "de" else en


def quote_in(quote: str, text: str) -> bool:
    """True when `quote` occurs word for word in `text` (whitespace and case ignored)."""
    q = norm(quote).lower().strip(" \"'“”„‚‘’…")
    return bool(q) and q in norm(text).lower()


def best_sentence(text: str, query_tokens: set[str]) -> str | None:
    best, score = None, 0.0
    for s in sentences(text):
        sc = overlap(query_tokens, tokens(s))
        if sc > score:
            best, score = s, sc
    return best
