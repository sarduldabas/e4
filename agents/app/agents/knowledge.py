"""Committee-report knowledge used by the rules versions: typical sections and what each one needs from the user."""
from __future__ import annotations

from .util import tokens

# key, words that identify the section in a template title, (de, en) title, (de, en) purpose, [(de, en) required input]
TOPICS = [
    ("summary", ["summary", "zusammenfassung", "management", "executive", "kurzfassung"],
     ("Management Summary", "Management summary"),
     ("Entscheidung und Empfehlung auf einer Seite", "The decision and the recommendation on one page"),
     [("Die gewünschte Entscheidung des Gremiums", "The decision requested from the committee"),
      ("Ihre Empfehlung in einem Satz", "Your recommendation in one sentence")]),
    ("background", ["background", "hintergrund", "scope", "umfang", "ausgangslage", "context", "kontext", "situation"],
     ("Hintergrund und Umfang", "Background and scope"),
     ("Warum das Thema jetzt ansteht und was dazugehört", "Why the topic is on the table now and what it covers"),
     [("Die aktuelle Situation", "The current situation"), ("Der Anlass: warum jetzt", "The trigger: why now"), ("Der Umfang der Betrachtung", "The scope of the review")]),
    ("supplier", ["supplier", "lieferant", "vendor", "landscape", "markt", "market"],
     ("Lieferantenlandschaft", "Supplier landscape"),
     ("Wer liefert heute und wer käme in Frage", "Who supplies today and who could"),
     [("Aktuelle Lieferanten und ihre Anteile", "Current suppliers and their shares"), ("Was jeder Lieferant leisten kann", "What each supplier can deliver")]),
    ("options", ["option", "cost", "kosten", "budget", "alternativ", "comparison", "vergleich", "business case"],
     ("Optionen und Kosten", "Options and cost"),
     ("Die Optionen im Vergleich mit Kosten", "The options compared, with cost"),
     [("Die Optionen, die verglichen werden", "The options being compared"), ("Die Kosten je Option", "The cost of each option")]),
    ("risks", ["risk", "risiko", "risiken", "mitigation", "gegenmaß", "chance"],
     ("Risiken und Gegenmaßnahmen", "Risks and mitigations"),
     ("Die wichtigsten Risiken und was dagegen getan wird", "The main risks and what is done about them"),
     [("Die wichtigsten Risiken", "The main risks"), ("Die Gegenmaßnahmen", "The countermeasures")]),
    ("timeline", ["timeline", "zeitplan", "meilenstein", "milestone", "roadmap", "termin", "schedule"],
     ("Zeitplan und Meilensteine", "Timeline and milestones"),
     ("Wann was passiert", "What happens when"),
     [("Die Meilensteine mit Terminen", "The milestones with dates")]),
    ("recommendation", ["recommendation", "empfehlung", "next step", "nächste", "decision", "beschluss", "ausblick"],
     ("Empfehlung und nächste Schritte", "Recommendation and next steps"),
     ("Was empfohlen wird und wie es weitergeht", "What is recommended and what comes next"),
     [("Die empfohlene Option", "The recommended option"), ("Nächste Schritte mit Verantwortlichen", "Next steps with owners")]),
]

DEFAULT_OUTLINE = ["summary", "background", "supplier", "options", "risks", "timeline", "recommendation"]


def topic_by_key(key: str):
    return next((t for t in TOPICS if t[0] == key), None)


def classify(title: str):
    """The topic a template title belongs to, or None."""
    low = (title or "").lower()
    for t in TOPICS:
        if any(w in low for w in t[1]):
            return t
    return None


def i(lang: str, pair: tuple[str, str]) -> str:
    return pair[0] if lang == "de" else pair[1]


# Questions a committee typically asks, by topic (used by the red-team rules version).
COMMITTEE_QUESTIONS = {
    "options": (("Was kostet die Empfehlung insgesamt, und wie empfindlich ist das Ergebnis bei Änderungen der Annahmen?",
                 "What does the recommendation cost in total, and how sensitive is the result to changed assumptions?")),
    "risks": (("Was passiert, wenn das größte Risiko eintritt, und wer ist verantwortlich?",
               "What happens if the biggest risk occurs, and who owns it?")),
    "timeline": (("Ist der Zeitplan mit den heutigen Ressourcen realistisch, und was verschiebt sich bei Verzug?",
                  "Is the timeline realistic with today's resources, and what slips if it is late?")),
    "supplier": (("Wie abhängig sind wir heute von einem einzelnen Lieferanten?",
                  "How dependent are we today on a single supplier?")),
    "recommendation": (("Warum diese Option und nicht die günstigste?", "Why this option and not the cheapest one?")),
    "summary": (("Was genau soll das Gremium heute entscheiden?", "What exactly should the committee decide today?")),
    "background": (("Was passiert, wenn wir nichts tun?", "What happens if we do nothing?")),
}


def topic_tokens(section_title: str, purpose: str = "", inputs: list[str] | None = None) -> set[str]:
    return tokens(" ".join([section_title, purpose, *(inputs or [])]))
